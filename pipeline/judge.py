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
from .sourcing.common import cached_json


STAGE = "judge"
OUTPUT = "selection.json"
LETTERS = "ABCDE"
TILE = (320, 180)

JUDGE_INSTRUCTIONS = """
You are the picture editor of a fast-paced economics documentary. For ONE shot you get the
narration, a description of the ideal image, and a contact sheet: each row (A, B, C) is one
candidate, shown by 3 frames of the exact fragment that would be used (a still photo is
repeated). Rank the candidates that are ACCEPTABLE for this shot, best first.

B-roll illustrates the idea being narrated; it does not have to match every detail of the
description. Accept a candidate when it clearly fits what is being said (the subject, the
place, the mood). The description is a guide, not a checklist.

Reject (leave out of the ranking) a candidate that:
- is unrelated to the narration, or shows a different named place/person/brand;
- is dominated by on-screen text, titles, lower-thirds, watermark banners, UI or screenshots;
- is a presenter/vlogger talking to camera, a reaction face, or a channel intro/outro;
- is blurry, black, frozen, a cartoon/animation (unless asked), or a slide.
Prefer real footage of the exact named entity over generic footage, and moving footage over
stills when both fit. Return an empty ranking only if none is acceptable.
"""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "ranking": {"type": "array", "items": {"type": "string", "enum": list(LETTERS)}},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["ranking", "score", "reason", "confidence"],
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
    return frames


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


def is_doubtful(scores: list[float], margin: float, min_score: float) -> bool:
    if not scores:
        return False
    return scores[0] < min_score or (len(scores) > 1 and scores[0] - scores[1] < margin)


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


def shot_brief(shot: Shot) -> str:
    broll = shot.broll
    assert broll is not None
    lines = [
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


def call_judge(ctx: RunContext, shot: Shot, sheet: np.ndarray, letters: str) -> dict[str, Any]:
    cfg = ctx.section("judge")
    model = str(cfg.get("model", "gpt-5-mini"))
    if str(cfg.get("provider", "openai")) != "openai":
        raise ValueError("judge.provider: solo 'openai' está implementado (modelo con visión).")
    ok, encoded = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("No se pudo codificar la hoja de contactos.")
    image_bytes = encoded.tobytes()
    prompt = f"{shot_brief(shot)}\nCandidates on the sheet: {', '.join(letters)}."
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
        verdict = json.loads(response.output_text)
        verdict["ranking"] = [letter for letter in dict.fromkeys(verdict.get("ranking", [])) if letter in letters]
        return verdict

    return cached_json(ctx.cache_dir / "judge" / f"{cache_key}.json", produce)


# --- stage -----------------------------------------------------------------------------


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "shots.json", ctx.work_dir / "candidates", ctx.work_dir / "scores"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("judge")
    started = time.monotonic()
    shots = [s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots if needs_footage(s)]
    candidates: dict[str, Candidate] = {}
    scores: dict[str, ShotScores] = {}
    for shot in shots:
        for c in ShotCandidates.model_validate_json((ctx.work_dir / "candidates" / f"{shot.id}.json").read_text("utf-8")).candidates:
            candidates[c.id] = c
        scores[shot.id] = ShotScores.model_validate_json((ctx.work_dir / "scores" / f"{shot.id}.json").read_text("utf-8"))

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
    for shot in shots:
        order = [(s, o) for s, o in ranked(scores[shot.id].options, bonus) if s >= min_accept]
        plans[shot.id] = [o for _, o in order]
        if is_doubtful([s for s, _ in order], margin, min_score) and len(order) >= 1:
            doubtful.append(shot)
    print(f"   {len(shots)} planos · {len(doubtful)} con duda → juez ({cfg.get('model', 'gpt-5-mini')})")

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
            verdict = call_judge(ctx, shot, sheet, LETTERS[: len(options)])
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
        chosen = next((o for o in preference if not is_repeat(o, selections, max_hamming)), None)
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
