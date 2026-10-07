"""Stage 5 — pick one fragment/image per shot; a vision model judges only the doubtful shots.

Per shot, the usable options from stage 4 are ranked by their local score plus a small
priority bonus per source (third-party footage first). A shot is *doubtful* when the top
two are closer than `judge.margin` or the best is below `judge.min_score`; only then is
the vision judge called, with one contact sheet (3 frames of each of the top options).
The judge ranks the acceptable options (or rejects them all → fallback, stage 7).

Assignment then walks the shots in order and never reuses a fragment: same source video
with overlapping timestamps, or a near-identical picture (pHash), counts as a repeat.
Judge calls run in parallel before that walk and are cached (cache/judge/), so re-runs
are free; spend is logged in costs.json.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .analysis import detectors as det
from .context import RunContext
from .costs import record_cost
from .schemas import (
    Candidate,
    JudgeVerdict,
    Option,
    Selection,
    SelectionFile,
    Shot,
    ShotCandidates,
    ShotScores,
    ShotsFile,
)
from .sourcing import needs_footage
from .sourcing.common import blocked_by_title, cached_json, tokens


STAGE = "judge"
OUTPUT = "selection.json"
LETTERS = "ABCDE"
TILE = (320, 180)

JUDGE_INSTRUCTIONS = """
You are the picture editor of a fast-paced YouTube documentary (any niche; the topic is given). For ONE shot you get the
narration, a description of the ideal image, and a contact sheet: each row (A, B, C) is one
candidate, shown by 3 frames of the exact fragment that would be used (a still photo is
repeated). Rank the candidates that are ACCEPTABLE for this shot, best first.

B-roll illustrates the idea being narrated; it does not have to match every detail of the
description. Accept a candidate when it clearly fits what is being said (the subject, the
place, the mood). The description is a guide, not a checklist. It is written by an automatic
planner and can be wrong: when it asks for something outside the video's topic (a restaurant
kitchen, an office checklist, a filing cabinet in a video about casinos), ignore it and judge
against the topic and the narration. Look carefully at what each frame really shows before
naming it.

Reject (leave out of the ranking) a candidate that:
- is unrelated to the narration, or shows a different named place/person/brand;
- is dominated by on-screen text, titles, lower-thirds, watermark banners, UI or screenshots;
- is a presenter/vlogger talking to camera, a reaction face, or a channel intro/outro (an interview
  of the very person the video is about is fine when the narration quotes or describes them);
- is blurry, black, frozen, a cartoon/animation or video-game footage (unless asked), or a slide;
- has burned-in subtitles or captions, even small ones;
- is a screen recording or tutorial of software, a spreadsheet, a form, a website or an app — UNLESS the narration
  is about that app, website or interface itself (how a service signs people up or makes it hard to cancel, an
  app's design, a platform's settings): then a clear recording of that screen IS the right footage, accept it;
- takes the viewer out of the video's topic: a comparison or metaphor illustrated literally
  (a restaurant kitchen for "it is not like opening a restaurant"), or generic office/stock
  footage for an abstract idea, when footage of the topic itself would fit.
When the video is about a specific person (VIDEO SUBJECT), the footage must belong to their
world: the same sport/discipline, and preferably the person themselves or the exact event of
the shot (EVENT). A podium, arena or crowd from another sport or another competition is
off-topic, even if "a podium" matches the words. Prefer the identifiable person/event over
generic footage of the same sport. Protagonist first: unless the narration names someone else
or a specific place, rank candidates that show the VIDEO SUBJECT above everything else; footage
of anonymous athletes, children or strangers is a last resort, and for HOOK shots of such a
video only the subject's standout moments are acceptable. Identity: the person on screen must be the one the narration is about. If the narration is about a
man, reject footage or photos whose main subject is a woman (and vice versa), unless the narration
names that other person; never show a different, identifiable athlete as if it were the subject.
Another event is off-topic too: when the narration is about one specific incident, flight, accident, case or
company, reject footage whose title or frames are clearly about a DIFFERENT specific one (another crash, another
flight number, another company's scandal) — viewers take it as the event being told. Same for TV dramatizations
and re-enactments (actors playing pilots or victims) presented as real footage.
Other creators' videos about the SAME subject as this one (another channel's «top 6 humanoids you can buy», «the
strange history of the backflip», «8 deli meat brands to avoid») are re-edits with their own voice: prefer the
original source (the manufacturer, the federation, the broadcaster, the news) whenever it is among the candidates.
The source video titles listed under the sheet are hints
(they can be clickbait or compilations): trust what the frames show first.
When the shot is marked HOOK (the first seconds of the video), be strict: accept only striking,
good-quality footage that is unmistakably about the topic; reject amateur, dull or generic shots.
Prefer real footage of the exact named entity over generic footage, and moving footage over
stills when both fit. Return an empty ranking only if none is acceptable.

First describe every candidate in "candidates": what its frames really show (a few plain
words), whether it is a screen / UI / chart / document dominated by text (false for a clear recording of the very
app or website the narration is about), and whether it belongs to the video's topic (for a video about a person: same sport/discipline, not another
athlete shown as if they were the subject). Then rank. A candidate flagged as screen or off-topic is
never used, whatever the ranking says.
Be brief (you are billed per word): "shows" is at most 10 words, "reason" one sentence of at most 20 words.
"""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "letter": {"type": "string", "enum": list(LETTERS)},
                    "shows": {"type": "string"},
                    "screenOrText": {"type": "boolean"},
                    "onTopic": {"type": "boolean"},
                },
                "required": ["letter", "shows", "screenOrText", "onTopic"],
                "additionalProperties": False,
            },
        },
        "ranking": {"type": "array", "items": {"type": "string", "enum": list(LETTERS)}},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["candidates", "ranking", "score", "reason", "confidence"],
    "additionalProperties": False,
}


# --- contact sheet ---------------------------------------------------------------------


def _video_frames(option: Option, candidate: Candidate, root: Path) -> list[np.ndarray]:
    assert option.start is not None and option.end is not None
    span = option.end - option.start
    times = [option.start + span * q for q in (0.2, 0.5, 0.8)]
    frames: list[np.ndarray] = []
    if option.analysisPath:
        path = root / option.analysisPath
        try:
            offset = float(path.stem.split("_")[1])
        except (IndexError, ValueError):
            offset = 0.0
        capture = cv2.VideoCapture(str(path))
        for t in times:
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t - offset) * 1000)
            ok, frame = capture.read()
            if ok:
                frames.append(frame)
        capture.release()
    elif candidate.storyboard is not None:  # coarse-only option: the storyboard thumbnails around it
        board = candidate.storyboard
        for t in times:
            index = min(board.frames - 1, int(t / board.interval))
            sheet_index, x, y = board.locate(index)
            sheet = cv2.imread(str(root / board.sheets[sheet_index]))
            if sheet is not None:
                frames.append(sheet[y : y + board.tileHeight, x : x + board.tileWidth])
    # The last storyboard sheet can be smaller than its grid: an out-of-range tile crops to nothing.
    return [f for f in frames if f.size > 0]


def contact_sheet(options: list[Option], candidates: dict[str, Candidate], root: Path) -> np.ndarray:
    label_width = 70
    rows = []
    for letter, option in zip(LETTERS, options):
        candidate = candidates[option.candidateId]
        if option.kind == "image":
            picture = cv2.imread(str(root / option.analysisPath)) if option.analysisPath else None
            frames = [picture] * 3 if picture is not None else []
        else:
            frames = _video_frames(option, candidate, root)
        tiles = [cv2.resize(f, TILE, interpolation=cv2.INTER_AREA) for f in frames[:3]]
        while len(tiles) < 3:
            tiles.append(np.zeros((TILE[1], TILE[0], 3), np.uint8))
        label = np.full((TILE[1], label_width, 3), 30, np.uint8)
        cv2.putText(label, letter, (14, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (255, 255, 255), 3)
        cv2.putText(label, "FOTO" if option.kind == "image" else "VIDEO", (6, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        rows.append(np.hstack([label, *tiles]))
        rows.append(np.full((4, label_width + 3 * TILE[0], 3), 90, np.uint8))
    return np.vstack(rows[:-1])


# --- policy ----------------------------------------------------------------------------


def ranked(options: list[Option], bonus: dict[str, float]) -> list[tuple[float, Option]]:
    usable = [o for o in options if o.discarded is None]
    return sorted(((o.total + float(bonus.get(o.source, 0.0)), o) for o in usable), key=lambda item: -item[0])


def overused(candidate_id: str, selections: list[Selection], limit: int) -> bool:
    """A source video already on screen `limit` times in this video: the next shot looks for another one."""

    return limit > 0 and sum(1 for s in selections if s.candidateId == candidate_id) >= limit


def is_doubtful(scores: list[float], margin: float, min_score: float) -> bool:
    if not scores:
        return False
    return scores[0] < min_score or (len(scores) > 1 and scores[0] - scores[1] < margin)


USED_REGISTRY = "used_fragments.json"   # in cache/: what every video of the channel already put on screen


def used_elsewhere(ctx: RunContext) -> dict[str, list[tuple[float | None, float | None]]]:
    """Fragments/pictures other videos already used, and those marked wrong in the studio's «Errores»:
    candidateId → [(start, end)] (None = a picture, or the whole source)."""

    from .feedback import wrong_fragments

    out: dict[str, list[tuple[float | None, float | None]]] = wrong_fragments(ctx.root)   # marked wrong in «Errores»
    path = ctx.cache_dir / USED_REGISTRY
    if not ctx.section("judge").get("avoid_other_videos", True) or not path.is_file():
        return out
    try:
        registry = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return out
    for slug, entries in registry.items():
        if slug == ctx.slug:
            continue
        for cid, start, end in entries:
            out.setdefault(cid, []).append((start, end))
    return out


def seen_elsewhere(option: Option, elsewhere: dict[str, list[tuple[float | None, float | None]]]) -> bool:
    for start, end in elsewhere.get(option.candidateId, []):
        if option.start is None or start is None:
            return True                          # the same picture, or a still of that video
        if option.start < end + 0.5 and start < option.end + 0.5:
            return True
    return False


def register_used(ctx: RunContext, rows: list[dict[str, Any]]) -> None:
    """Record this video's on-screen sources so later videos of the channel avoid them."""

    path = ctx.cache_dir / USED_REGISTRY
    try:
        registry = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        registry = {}
    registry[ctx.slug] = [[r["candidateId"], r.get("sourceStart"), r.get("sourceEnd")]
                          for r in rows if r.get("candidateId") and r.get("source") not in (None, "generated")]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def is_repeat(option: Option, used: list[Selection], max_hamming: int) -> bool:
    for previous in used:
        if previous.candidateId == option.candidateId:
            if option.kind == "image":
                return True
            if previous.start is not None and option.start is not None and option.end is not None:
                if option.start < previous.end + 0.5 and previous.start < option.end + 0.5:
                    return True
        if option.phash and previous.phash and det.hamming(option.phash, previous.phash) <= max_hamming:
            return True
    return False


# --- judge call ------------------------------------------------------------------------


def shot_brief(shot: Shot, topic: str = "", hook: bool = False, subject: str = "") -> str:
    broll = shot.broll
    assert broll is not None
    lines = [f"Video topic: {topic}"] if topic else []
    if subject:
        lines.append(f"VIDEO SUBJECT: {subject}")
    if broll.event:
        lines.append(f"EVENT of this shot: {broll.event}")
    if hook:
        lines.append("HOOK: this is one of the first seconds of the video.")
    lines += [
        f"Narration (Spanish): {shot.text}",
        f"The shot should show: {broll.visualIntent}",
    ]
    if broll.entities:
        lines.append(f"Named entities: {', '.join(broll.entities)}")
    if broll.mustContain:
        lines.append(f"Ideally visible (nice to have, not required): {', '.join(broll.mustContain)}")
    if broll.avoid:
        lines.append(f"Avoid: {', '.join(broll.avoid)}")
    return "\n".join(lines)


def call_judge(ctx: RunContext, shot: Shot, sheet: np.ndarray, letters: str, topic: str = "",
               hook: bool = False, subject: str = "", sources: str = "") -> dict[str, Any]:
    cfg = ctx.section("judge")
    model = str(cfg.get("model", "gpt-5-mini"))
    if str(cfg.get("provider", "openai")) != "openai":
        raise ValueError("judge.provider: solo 'openai' está implementado (modelo con visión).")
    ok, encoded = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("No se pudo codificar la hoja de contactos.")
    image_bytes = encoded.tobytes()
    prompt = f"{shot_brief(shot, topic, hook, subject)}\nCandidates on the sheet: {', '.join(letters)}."
    if cfg.get("note"):                      # the channel's own rule (canales/<canal>.yaml → judge.note)
        prompt += f"\nChannel rule: {' '.join(str(cfg['note']).split())}"
    if sources:
        prompt += f"\nSource of each candidate:\n{sources}"
    taught = _lessons(ctx)
    if taught:
        prompt += ("\nThe editor's past corrections on this channel (learn the standard, not the clips):\n" + taught)
    cache_key = hashlib.sha256(
        json.dumps([model, JUDGE_INSTRUCTIONS, prompt, cfg.get("reasoning_effort", "low"), cfg.get("detail", "auto")]).encode()
        + image_bytes
    ).hexdigest()[:32]

    def produce() -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=ctx.env("OPENAI_API_KEY"))
        response = client.responses.create(
            model=model,
            instructions=JUDGE_INSTRUCTIONS,
            reasoning={"effort": str(cfg.get("reasoning_effort", "low"))},
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode(),
                     "detail": str(cfg.get("detail", "auto"))},
                ],
            }],
            text={"format": {"type": "json_schema", "name": "shot_verdict", "strict": True, "schema": VERDICT_SCHEMA}},
        )
        prices = cfg.get("usd_per_mtok", {})
        usage = response.usage
        usd = (usage.input_tokens * float(prices.get("input", 0.25)) + usage.output_tokens * float(prices.get("output", 2.0))) / 1e6
        record_cost(ctx, stage=STAGE, provider="openai", operation=model, usd=usd,
                    details={"shot": shot.id, "inputTokens": usage.input_tokens, "outputTokens": usage.output_tokens})
        return json.loads(response.output_text)

    return usable(cached_json(ctx.cache_dir / "judge" / f"{cache_key}.json", produce), letters)


def _lessons(ctx: RunContext) -> str:
    """Your «Errores» corrections on this channel (pipeline/feedback.py), once per video."""

    if not ctx.section("judge").get("learn", True):
        return ""
    cached = getattr(ctx, "_judge_lessons", None)
    if cached is None:
        from . import feedback

        try:
            cached = feedback.lessons(ctx.root, ctx.channel or "", int(ctx.section("judge").get("lessons", 10)))
        except Exception:
            cached = ""
        try:
            object.__setattr__(ctx, "_judge_lessons", cached)
        except Exception:
            pass
    return cached


def source_lines(options: list[Option], candidates: dict[str, Candidate]) -> str:
    """One line per letter: where the fragment comes from (title · channel), a hint for the judge."""

    lines = []
    for letter, option in zip(LETTERS, options):
        c = candidates[option.candidateId]
        lines.append(f"{letter}: {c.source} · \"{(c.title or '')[:90]}\" · {(c.channel or '')[:40]}")
    return "\n".join(lines)


def usable(verdict: dict[str, Any], letters: str) -> dict[str, Any]:
    """The ranking without letters off the sheet, repeated, or flagged as screen/off-topic."""

    flagged = {c["letter"] for c in verdict.get("candidates", []) if c.get("screenOrText") or not c.get("onTopic", True)}
    ranking = [x for x in dict.fromkeys(verdict.get("ranking", [])) if x in letters and x not in flagged]
    return {**verdict, "ranking": ranking}


# --- stage -----------------------------------------------------------------------------


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "shots.json", ctx.work_dir / "candidates", ctx.work_dir / "scores"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("judge")
    started = time.monotonic()
    shots_file = ShotsFile.model_validate(ctx.read_json("shots.json"))
    shots = [s for s in shots_file.shots if needs_footage(s)]
    topic = shots_file.context or shots_file.title
    subject = shots_file.subject
    candidates: dict[str, Candidate] = {}
    scores: dict[str, ShotScores] = {}
    for shot in shots:
        for c in ShotCandidates.model_validate_json((ctx.work_dir / "candidates" / f"{shot.id}.json").read_text("utf-8")).candidates:
            candidates[c.id] = c
        scores[shot.id] = ShotScores.model_validate_json((ctx.work_dir / "scores" / f"{shot.id}.json").read_text("utf-8"))
    stray = 0
    for shot_id, shot_scores in scores.items():           # options of a candidate this run no longer has (two runs
        kept = [o for o in shot_scores.options if o.candidateId in candidates]    # of one video wrote different lists)
        stray += len(shot_scores.options) - len(kept)
        if len(kept) != len(shot_scores.options):
            scores[shot_id] = shot_scores.model_copy(update={"options": kept})
    if stray:
        print(f"   {stray} opciones de candidatos que ya no existen, descartadas (¿dos procesos con el mismo vídeo?)")

    bonus = cfg.get("source_bonus", {"youtube": 0.02})
    margin = float(cfg.get("margin", 0.02))
    min_score = float(cfg.get("min_score", 0.30))
    min_accept = float(cfg.get("min_accept", 0.22))
    shown = int(cfg.get("candidates", 3))
    sheets_dir = ctx.work_dir / "judge"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    # 1. Which shots need the judge (decided on the un-deduplicated ranking, so calls can run in parallel).
    plans: dict[str, list[Option]] = {}
    doubtful: list[Shot] = []
    blocklist = ctx.section("content").get("title_blocklist")
    hook_seconds = float(cfg.get("hook_seconds", 30))
    judge_all = bool(cfg.get("all", False))
    trusted = [tokens(str(t)) for t in cfg.get("trusted_channels", []) if tokens(str(t))]
    trusted_bonus = float(cfg.get("trusted_bonus", 0.03))

    def official(option: Option) -> float:
        """Whole words of a trusted name in the channel name ('Olympics' yes, 'Chris RD Gymnastics' no)."""
        channel = tokens(candidates[option.candidateId].channel or "")
        return trusted_bonus if channel and any(t <= channel for t in trusted) else 0.0

    elsewhere = used_elsewhere(ctx)
    # A story about one athlete: a confident CLIP score is not enough when the best clip's title does not name
    # them (pati2: Trusova's world records went on «Yuzuru Hanyu - Olympic record» unseen) → the judge, who
    # reads the titles and rejects another identifiable athlete.
    from .identity import ascii_upper, expected_people, surname

    protagonist = (subject or "").split("·")[0].strip()
    scope = str(ctx.section("fallback").get("identity_scope", "protagonist"))

    def unnamed(shot: Shot, option: Option) -> bool:
        if not protagonist or not cfg.get("judge_unnamed", True):
            return False
        who = expected_people(shot, [protagonist], protagonist, scope)
        c = candidates[option.candidateId]
        said = ascii_upper(f"{c.title} {c.channel}")
        return bool(who) and not any(surname(n) and surname(n) in said for n in who)

    for shot in shots:
        order = sorted((
            (s + official(o), o) for s, o in ranked(scores[shot.id].options, bonus)
            if s >= min_accept and not blocked_by_title(candidates[o.candidateId].title, candidates[o.candidateId].channel, blocklist)
            and not seen_elsewhere(o, elsewhere)
        ), key=lambda pair: -pair[0])
        plans[shot.id] = [o for _, o in order]
        if order and (judge_all or is_doubtful([s for s, _ in order], margin, min_score) or shot.start < hook_seconds
                      or unnamed(shot, order[0][1])):
            doubtful.append(shot)
    print(f"   {len(shots)} planos · {len(doubtful)} {'en total' if judge_all else 'con duda, en el gancho o sin el protagonista en el título'} → juez ({cfg.get('model', 'gpt-5-mini')})")

    verdicts: dict[str, tuple[dict[str, Any], list[Option]]] = {}

    rounds = int(cfg.get("rounds", 2))

    def judge(shot: Shot) -> None:
        """Up to `rounds` sheets: the next options are shown only if everything so far was rejected."""

        seen: list[Option] = []
        accepted: list[Option] = []
        verdict: dict[str, Any] = {}
        for round_number in range(rounds):
            options = plans[shot.id][round_number * shown : (round_number + 1) * shown]
            if not options:
                break
            sheet = contact_sheet(options, candidates, ctx.root)
            suffix = "" if round_number == 0 else f"-{round_number + 1}"
            cv2.imwrite(str(sheets_dir / f"{shot.id}{suffix}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
            verdict = call_judge(ctx, shot, sheet, LETTERS[: len(options)], topic, shot.start < hook_seconds,
                                 subject, source_lines(options, candidates))
            by_letter = dict(zip(LETTERS, options))
            seen += options
            accepted = [by_letter[letter] for letter in verdict["ranking"] if letter in by_letter]
            if accepted:
                break
        verdicts[shot.id] = ({**verdict, "round": round_number + 1}, seen, accepted)

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=int(cfg.get("parallel", 4))) as pool:
        for shot, future in [(s, pool.submit(judge, s)) for s in doubtful]:
            try:
                future.result()
            except Exception as error:  # a failed call falls back to the local ranking for that shot
                errors.append(f"{shot.id}: {str(error)[:160]}")

    # 2. Assign in shot order, never repeating a fragment.
    max_hamming = int(cfg.get("max_phash_distance", 6))
    per_source = int(cfg.get("max_per_source", 4))      # avion8: one factory tour in 11 shots, one news aerial in 8
    selections: list[Selection] = []
    for shot in shots:
        preference: list[Option] = plans[shot.id]
        judged: list[Option] = []
        verdict_info: dict[str, Any] | None = None
        if shot.id in verdicts:
            verdict_info, shown_options, judged = verdicts[shot.id]
            # Only what the judge accepted, in its order. If it rejected everything it saw, the shot
            # goes to fallback rather than to an option nobody looked at.
            preference = judged
        chosen = next((o for o in preference if not is_repeat(o, selections, max_hamming)
                       and not overused(o.candidateId, selections, per_source)), None)
        if chosen is None:
            selections.append(Selection(shotId=shot.id, status="fallback", decidedBy="fallback",
                                        judge=_verdict(verdict_info, None, cfg)))
            continue
        decided_by = "judge" if any(chosen is o for o in judged) else "score"
        candidate = candidates[chosen.candidateId]
        selections.append(Selection(
            shotId=shot.id,
            status="selected",
            decidedBy=decided_by,
            candidateId=chosen.candidateId,
            source=chosen.source,
            kind=chosen.kind,
            start=chosen.start,
            end=chosen.end,
            analysisPath=chosen.analysisPath,
            mediaUrl=candidate.mediaUrl,
            url=candidate.url,
            title=candidate.title,
            channel=candidate.channel,
            license=candidate.license,
            credit=candidate.credit,
            attribution=candidate.attribution,
            score=chosen.total,
            judge=_verdict(verdict_info, chosen, cfg),
            phash=chosen.phash,
        ))

    stats: dict[str, int | float] = {
        "shots": len(selections),
        "judgeCalls": len(verdicts),
        "judgeErrors": len(errors),
        "byJudge": sum(s.decidedBy == "judge" for s in selections),
        "byScore": sum(s.decidedBy == "score" for s in selections),
        "fallback": sum(s.status == "fallback" for s in selections),
    }
    for selection in selections:
        if selection.source:
            stats[f"source:{selection.source}"] = stats.get(f"source:{selection.source}", 0) + 1
    from . import editor

    selections = editor.apply_footage(ctx, selections)     # footage the editor swapped by hand
    result = SelectionFile(slug=ctx.slug, selections=selections, stats=stats)
    ctx.write_json(OUTPUT, result.model_dump(exclude_none=True))
    spent = sum(e["usd"] for e in (ctx.read_json("costs.json").get("entries", []) if (ctx.work_dir / "costs.json").is_file() else [])
                if e.get("stage") == STAGE)
    print(f"   Elegidos: {stats['byScore']} por puntuación, {stats['byJudge']} por el juez, {stats['fallback']} a fallback")
    print("   Fuentes: " + ", ".join(f"{k.split(':')[1]} {v}" for k, v in stats.items() if k.startswith("source:")))
    print(f"   Juez: {len(verdicts)} llamadas · gasto acumulado del juez {spent:.3f} $ · {time.monotonic() - started:.0f} s")
    for error in errors[:5]:
        print(f"   AVISO juez: {error}")


def _verdict(info: dict[str, Any] | None, chosen: Option | None, cfg: dict[str, Any]) -> JudgeVerdict | None:
    if info is None:
        return None
    return JudgeVerdict(
        choice=info["ranking"][0] if info.get("ranking") else "none",
        selectedStart=chosen.start if chosen else None,
        selectedEnd=chosen.end if chosen else None,
        score=float(info.get("score", 0)),
        reason=str(info.get("reason", ""))[:500],
        confidence=float(info.get("confidence", 0)),
        model=str(cfg.get("model", "gpt-5-mini")),
        round=int(info.get("round", 1)),
    )


def validate(ctx: RunContext) -> bool:
    SelectionFile.model_validate(ctx.read_json(OUTPUT))
    return True
