"""Optional cold open — work/<slug>/coldopen.json + coldopen/.

With `timeline.cold_open_seconds: N` (usually set per video in materiales/<slug>/config.yaml),
the video opens with N seconds of the protagonist's peak moments WITH their original sound
(crowd, commentators) before the narration starts, as sports channels do. The fragments show the
protagonist alone in action (judge-vetted), are never reused later in the video, are at most 5 s
each and carry their source credit; their audio is levelled and mixed under nothing else.

Moments (`timeline.moments: N`, default 2): the same idea in the middle of the video, like the
reference channels do at the climax. The LLM picks the sentences after which the story peaks (the
landing that wins the gold, the score appearing, the fall); the narration pauses there for
`timeline.moment_seconds` while the competition footage continues with its commentators and crowd:
the same source as the last shot of that sentence, right after the fragment already shown.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .context import RunContext
from .costs import record_cost
from .llm import complete_json
from .ingest import FPS, NORMALISE_VERSION, _frame_filter, find_lut, lut_filter, probe
from .judge import LETTERS, call_judge, contact_sheet, ranked, source_lines
from .schemas import (
    MAX_THIRD_PARTY_SECONDS,
    Candidate,
    ColdOpenClip,
    ColdOpenFile,
    FallbackFile,
    Option,
    Selection,
    SelectionFile,
    ShotCandidates,
    ShotScores,
    ShotsFile,
)
from .sourcing import youtube_source
from .sourcing.common import blocked_by_title, cached_json, key, tokens

STAGE = "coldopen"
OUTPUT = "coldopen.json"
CLIP_DIR = "coldopen"
AUDIO_FORMAT = "bv*[height<=1080][vcodec^=avc1]+ba/bv*[height<=1080]+ba/b[height<=1080]"


def plan_clips(seconds: float, count_available: int) -> list[float]:
    """Split N seconds into clips of ~3-4 s, never longer than the 5 s third-party limit."""

    if seconds <= 0 or count_available <= 0:
        return []
    count = min(count_available, max(1, math.ceil(seconds / 4.0)))
    length = min(MAX_THIRD_PARTY_SECONDS, seconds / count)
    return [round(length, 3)] * count


def normalise_with_audio(source: Path, target: Path, *, offset: float, duration: float, lut: Path | None) -> None:
    frames = max(1, round(duration * FPS))
    vf = f"{_frame_filter(source, 1920, 1080, offset)},setsar=1,fps={FPS}{lut_filter(lut)},format=yuv420p"
    tmp = target.with_name(target.stem + ".tmp.mp4")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-ss", f"{max(0.0, offset):.3f}",
         "-frames:v", str(frames), "-t", f"{frames / FPS:.3f}", "-vf", vf,
         "-af", "aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "2", "-c:a", "aac", "-b:a", "192k",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-movflags", "+faststart", str(tmp)],
        check=True, capture_output=True, text=True,
    )
    tmp.replace(target)


def pick_fragments(ctx: RunContext) -> list[Selection]:
    """Fragments of the protagonist alone in action, never already on screen, vetted by the judge.

    Candidates are all the analysed options of the hook shots (whose searches target the protagonist's
    peak) from sources naming the protagonist; any fragment used anywhere in the video is excluded,
    so the cold open never repeats a later shot. The judge then keeps only clips where the person is
    clearly identifiable on their own — performing or celebrating — not crowds or other athletes.
    """

    story = ShotsFile.model_validate(ctx.read_json("shots.json"))
    judge_cfg = ctx.section("judge")
    hook_seconds = float(judge_cfg.get("hook_seconds", 30))
    person = story.subject.split("·")[0].strip()
    name = tokens(person)                     # the full name: "Yulo" alone also matches the brother
    used: list[tuple[str, float, float]] = []
    for sel in SelectionFile.model_validate(ctx.read_json("selection.json")).selections:
        if sel.status == "selected" and sel.start is not None and sel.end is not None:
            used.append((sel.candidateId, sel.start, sel.end))
    if (ctx.work_dir / "fallback.json").is_file():
        for item in FallbackFile.model_validate(ctx.read_json("fallback.json")).items:
            if item.start is not None and item.end is not None:
                used.append((item.candidateId, item.start, item.end))

    def on_screen(option: Option) -> bool:
        return any(cid == option.candidateId and option.start < b + 1.0 and a < option.end + 1.0 for cid, a, b in used)

    options: list[Option] = []
    candidates: dict[str, Candidate] = {}
    peak: dict[str, int] = {}                 # option → overlap of its source title with the hook's event
    for shot in story.shots:
        if shot.start >= hook_seconds or not shot.broll:
            continue
        found = {c.id: c for c in ShotCandidates.model_validate_json(
            (ctx.work_dir / "candidates" / f"{shot.id}.json").read_text("utf-8")).candidates}
        scored = ShotScores.model_validate_json((ctx.work_dir / "scores" / f"{shot.id}.json").read_text("utf-8"))
        for total, option in ranked(scored.options, judge_cfg.get("source_bonus", {"youtube": 0.02})):
            c = found.get(option.candidateId)
            if (c is None or option.kind != "video" or c.source != "youtube" or on_screen(option)
                    or (name and not name <= tokens(f"{c.title or ''} {c.channel or ''}"))
                    or any(o.candidateId == option.candidateId and abs((o.start or 0) - (option.start or 0)) < 3 for o in options)):
                continue
            candidates[c.id] = c
            options.append(option)
            peak[f"{option.candidateId}@{option.start}"] = len(tokens(shot.broll.event or "") & tokens(c.title or ""))
    options.sort(key=lambda o: (-peak[f"{o.candidateId}@{o.start}"], -o.total))
    if not options:
        return []

    # One judge pass per sheet of 3 until enough clips are accepted.
    template = next(s for s in story.shots if s.broll)
    brief = template.model_copy(update={"text": "(cold open, before the narration)", "broll": template.broll.model_copy(update={
        "visualIntent": f"{person or 'the protagonist'} ALONE and clearly identifiable, performing or celebrating "
                        f"(medium or close shot): the person's own action, not the audience",
        "mustContain": [person] if person else [], "avoid": ["crowds", "audience", "other athletes", "presenters"],
        "event": None,
    })})
    accepted: list[Option] = []
    needed = len(plan_clips(float(ctx.section("timeline").get("cold_open_seconds", 0) or 0), len(options)))
    for start in range(0, min(len(options), 9), 3):
        sheet_options = options[start : start + 3]
        verdict = call_judge(ctx, brief, contact_sheet(sheet_options, candidates, ctx.root), LETTERS[: len(sheet_options)],
                             story.context or story.title, True, story.subject, source_lines(sheet_options, candidates))
        by_letter = dict(zip(LETTERS, sheet_options))
        accepted += [by_letter[x] for x in verdict["ranking"] if x in by_letter]
        if len(accepted) >= needed:
            break
    picks: list[Selection] = []
    for option in accepted:
        c = candidates[option.candidateId]
        if any(p.candidateId == c.id for p in picks):
            continue                                     # one clip per source video: more variety
        picks.append(Selection(
            shotId=template.id, status="selected", decidedBy="judge", candidateId=c.id, source=c.source,
            kind="video", start=option.start, end=option.end, url=c.url, title=c.title, channel=c.channel,
            license=c.license, credit=c.credit, attribution=c.attribution, score=option.total,
        ))
    return picks


MOMENTS_SYSTEM = """
Eres montador de documentales deportivos. Te paso la narración en frases numeradas. Elige como
máximo {count} frases DESPUÉS de las cuales la voz debe callarse unos segundos para dejar sonar el
momento original (comentaristas, público): el instante cumbre de una competición que se está
contando (el aterrizaje que da el oro, la nota en el marcador, la caída, la victoria). Solo
momentos de competición que se puedan ver, nunca en la infancia, entrevistas o reflexiones, y
repartidos por el vídeo (no en los primeros 30 s). Devuelve SOLO JSON: {{"moments": [{{"sentence": 12}}]}}
""".strip()


TALK = re.compile(r"\b(says?|said|interview|reacts?|press|speaks?|talks?|entrevista|dice|habla|rueda de prensa)\b", re.I)

CHECK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["competition", "why"],
                "properties": {"competition": {"type": "boolean"}, "why": {"type": "string"}}}


def pick_moments(ctx: RunContext, count: int, seconds: float) -> list[tuple[float, list[tuple[Selection, float]]]]:
    """For up to `count` peak sentences: (voice time to pause at, [(source, clip start), …] to try)."""

    from .shorts import sentences

    story = ShotsFile.model_validate(ctx.read_json("shots.json"))
    words = ctx.read_json("words.json")["words"]
    sents = sentences(words)
    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents)
    try:
        chosen = complete_json(ctx, stage=STAGE, section="planner", max_tokens=1000, user=listing[:60000],
                               system=MOMENTS_SYSTEM.format(count=count)).get("moments", [])
    except Exception as error:
        print(f"   Sin momentos: {str(error)[:120]}")
        return []
    selections = {s.shotId: s for s in SelectionFile.model_validate(ctx.read_json("selection.json")).selections}
    replaced = set()
    if (ctx.work_dir / "fallback.json").is_file():
        replaced = {i.shotId for i in FallbackFile.model_validate(ctx.read_json("fallback.json")).items}
    used = [(s.candidateId, s.start, s.end) for s in selections.values()
            if s.status == "selected" and s.start is not None and s.end is not None]
    name = tokens(story.subject.split("·")[0].strip())
    blocklist = ctx.section("content").get("title_blocklist")
    picks: list[tuple[float, list[tuple[Selection, float]]]] = []
    for item in chosen:
        try:
            n = int(item["sentence"])
            sent = sents[n]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if sent["end"] < 30 or any(abs(sent["end"] - p[0]) < 60 for p in picks):
            continue
        since = sents[max(0, n - 1)]["start"] - 0.05          # this sentence and the one before
        inside = [s for s in story.shots if s.start >= since and s.end <= sent["end"] + 0.6]
        options: list[tuple[Selection, float]] = []
        for shot in reversed(inside):
            sel = selections.get(shot.id)
            if (sel is None or shot.id in replaced or sel.status != "selected" or sel.source != "youtube"
                    or sel.kind != "video" or sel.end is None or TALK.search(sel.title or "")
                    or blocked_by_title(sel.title or "", sel.channel or "", blocklist)
                    or (name and not name <= tokens(f"{sel.title or ''} {sel.channel or ''}"))):
                continue
            start = float(sel.end)            # the action continues right after what was shown
            if any(cid == sel.candidateId and start < b + 0.5 and a < start + seconds + 0.5 for cid, a, b in used
                   if not (a == sel.start and b == sel.end)):
                continue
            if all(o[0].candidateId != sel.candidateId for o in options):
                options.append((sel, start))
        options += analysed_options(ctx, inside, used, name, blocklist, {o[0].candidateId for o in options})
        if options:
            picks.append((sent["end"], options[:4]))
        if len(picks) == count:
            break
    return sorted(picks, key=lambda p: p[0])


def analysed_options(ctx: RunContext, shots: list, used: list, name: set[str], blocklist: Any,
                     skip: set[str]) -> list[tuple[Selection, float]]:
    """Other analysed fragments of these shots (best first) from the protagonist's sources, not on screen."""

    found: list[tuple[float, Selection, float]] = []
    for shot in shots:
        path = ctx.work_dir / "candidates" / f"{shot.id}.json"
        scores = ctx.work_dir / "scores" / f"{shot.id}.json"
        if not path.is_file() or not scores.is_file():
            continue
        by_id = {c.id: c for c in ShotCandidates.model_validate_json(path.read_text("utf-8")).candidates}
        for total, option in ranked(ShotScores.model_validate_json(scores.read_text("utf-8")).options, {}):
            c = by_id.get(option.candidateId)
            if (c is None or option.kind != "video" or c.source != "youtube" or c.id in skip or option.start is None
                    or TALK.search(c.title or "") or blocked_by_title(c.title or "", c.channel or "", blocklist)
                    or (name and not name <= tokens(f"{c.title or ''} {c.channel or ''}"))
                    or any(cid == c.id and option.start < b + 1.0 and a < option.end + 1.0 for cid, a, b in used)):
                continue
            skip.add(c.id)
            found.append((total, Selection(
                shotId=shot.id, status="selected", decidedBy="judge", candidateId=c.id, source=c.source, kind="video",
                start=option.start, end=option.end, url=c.url, title=c.title, channel=c.channel, license=c.license,
                credit=c.credit, attribution=c.attribution, score=option.total), float(option.start)))
    return [(sel, start) for _, sel, start in sorted(found, key=lambda f: -f[0])][:3]


def is_competition(ctx: RunContext, clip: Path, person: str) -> bool:
    """Vision check on 3 frames: the athlete competing/celebrating in the arena, not an interview."""

    capture = cv2.VideoCapture(str(clip))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
    frames = []
    for at in (0.15, 0.5, 0.85):
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(total * at))
        ok, frame = capture.read()
        if ok:
            frames.append(cv2.resize(frame, (480, 270)))
    capture.release()
    if not frames:
        return False
    ok, encoded = cv2.imencode(".jpg", np.hstack(frames), [cv2.IMWRITE_JPEG_QUALITY, 85])
    image = encoded.tobytes()
    cfg = ctx.section("judge")
    model = str(cfg.get("model", "gpt-5-mini"))
    prompt = (f"Three frames of one 4-5 s clip. Is it LIVE COMPETITION footage of {person or 'the athlete'}: performing, "
              "landing, finishing or celebrating in the arena / on the podium, or the scoreboard moment? "
              "Interviews, press conferences, talking heads, news studios, training or crowds only → false.")

    def produce() -> dict[str, Any]:
        from openai import OpenAI

        response = OpenAI(api_key=ctx.env("OPENAI_API_KEY")).responses.create(
            model=model, reasoning={"effort": "low"},
            input=[{"role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(image).decode()}]}],
            text={"format": {"type": "json_schema", "name": "moment_check", "strict": True, "schema": CHECK_SCHEMA}},
        )
        prices = cfg.get("usd_per_mtok", {})
        usage = response.usage
        record_cost(ctx, stage=STAGE, provider="openai", operation=model,
                    usd=(usage.input_tokens * float(prices.get("input", 0.25)) + usage.output_tokens * float(prices.get("output", 2.0))) / 1e6)
        return json.loads(response.output_text)

    verdict = cached_json(ctx.cache_dir / "judge" / f"moment-{hashlib.sha256(prompt.encode() + image).hexdigest()[:32]}.json", produce)
    if not verdict.get("competition"):
        print(f"   {clip.name}: descartado ({verdict.get('why', '')[:90]})")
    return bool(verdict.get("competition"))


def fetch(youtube, sel: Selection, start: float, length: float, target: Path, lut: Path | None) -> ColdOpenClip | None:
    """Download [start, start+length] of a YouTube source WITH its sound, normalised; None if unusable."""

    try:
        if not target.is_file():
            source = youtube.download_range(sel.candidateId.removeprefix("yt:"), start, start + length + 0.5,
                                            fmt=AUDIO_FORMAT, prefix="hdav", audio=True)
            file_start = float(source.stem.split("_")[1])
            normalise_with_audio(source, target, offset=start - file_start, duration=length, lut=lut)
        info = probe(target)
        if not info["hasAudio"]:
            target.unlink(missing_ok=True)
            print(f"   {sel.candidateId}: sin pista de audio, se salta")
            return None
    except Exception as error:  # a failed download just means one clip fewer
        print(f"   {sel.candidateId}: {str(error)[-120:]}")
        return None
    return ColdOpenClip(
        path=target.as_posix(), candidateId=sel.candidateId, url=sel.url or "", title=sel.title, channel=sel.channel,
        start=round(start, 3), end=round(start + info["duration"], 3), durationSeconds=round(info["duration"], 3),
        width=info["width"], height=info["height"], credit=sel.credit or "", attribution=sel.attribution,
    )


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "selection.json", ctx.work_dir / "shots.json", ctx.work_dir / "fallback.json",
            ctx.work_dir / "words.json"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("timeline")
    seconds = float(cfg.get("cold_open_seconds", 0) or 0)
    moment_count = int(cfg.get("moments", 2) or 0)
    moment_seconds = min(MAX_THIRD_PARTY_SECONDS, float(cfg.get("moment_seconds", 4.5)))
    picks = pick_fragments(ctx) if seconds > 0 else []
    lengths = plan_clips(seconds, len(picks))
    moments = pick_moments(ctx, moment_count, moment_seconds) if moment_count > 0 else []
    if not lengths and not moments:
        ctx.write_json(OUTPUT, ColdOpenFile(slug=ctx.slug).model_dump())
        print("   Sin cold open ni momentos con sonido original")
        return
    lut = find_lut(ctx)
    youtube = youtube_source(ctx)
    out_dir = ctx.work_dir / CLIP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    clips: list[ColdOpenClip] = []
    pauses: list[ColdOpenClip] = []
    try:
        for sel in picks:
            if len(clips) == len(lengths):
                break
            length = lengths[len(clips)]
            start = float(sel.start)
            target = out_dir / f"c{len(clips) + 1:02d}-{key(sel.candidateId, start, length, NORMALISE_VERSION)[:8]}.mp4"
            clip = fetch(youtube, sel, start, length, target, lut)
            if clip:
                clips.append(clip.model_copy(update={"path": str(target.relative_to(ctx.root))}))
        person = ShotsFile.model_validate(ctx.read_json("shots.json")).subject.split("·")[0].strip()
        for after, options in moments:
            for sel, start in options:
                target = out_dir / f"m{len(pauses) + 1:02d}-{key(sel.candidateId, start, moment_seconds, NORMALISE_VERSION)[:8]}.mp4"
                clip = fetch(youtube, sel, start, moment_seconds, target, lut)
                if clip and is_competition(ctx, target, person):
                    pauses.append(clip.model_copy(update={"path": str(target.relative_to(ctx.root)), "afterSeconds": round(after, 3)}))
                    break
                target.unlink(missing_ok=True)
    finally:
        youtube.close()
    ctx.write_json(OUTPUT, ColdOpenFile(slug=ctx.slug, seconds=seconds, clips=clips, moments=pauses).model_dump())
    total = sum(c.durationSeconds for c in clips)
    if lengths:
        print(f"   Cold open: {len(clips)} clips con sonido original · {total:.1f} s · "
              + ", ".join(c.credit.removeprefix("Fuente: ") for c in clips))
    print(f"   Momentos con sonido original: {len(pauses)} · "
          + ", ".join(f"{m.afterSeconds:.0f}s ({m.credit.removeprefix('Fuente: ')})" for m in pauses))


def validate(ctx: RunContext) -> bool:
    data = ColdOpenFile.model_validate(ctx.read_json(OUTPUT))
    return all((ctx.root / c.path).is_file() for c in [*data.clips, *data.moments])
