"""Optional cold open — work/<slug>/coldopen.json + coldopen/.

With `timeline.cold_open_seconds: N` (usually set per video in materiales/<slug>/config.yaml),
the video opens with N seconds of the protagonist's peak moments WITH their original sound
(crowd, commentators) before the narration starts, as sports channels do. The fragments show the
protagonist alone in action (judge-vetted), are never reused later in the video, are at most 5 s
each and carry their source credit; their audio is levelled and mixed under nothing else.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from .context import RunContext
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
from .sourcing.common import key, tokens

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


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "selection.json", ctx.work_dir / "shots.json", ctx.work_dir / "fallback.json"]


def run(ctx: RunContext) -> None:
    seconds = float(ctx.section("timeline").get("cold_open_seconds", 0) or 0)
    if seconds <= 0:
        ctx.write_json(OUTPUT, ColdOpenFile(slug=ctx.slug).model_dump())
        print("   Sin cold open (timeline.cold_open_seconds = 0)")
        return
    picks = pick_fragments(ctx)
    lengths = plan_clips(seconds, len(picks))
    lut = find_lut(ctx)
    youtube = youtube_source(ctx)
    out_dir = ctx.work_dir / CLIP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    clips: list[ColdOpenClip] = []
    try:
        for sel in picks:
            if len(clips) == len(lengths):
                break
            length = lengths[len(clips)]
            start = float(sel.start)
            target = out_dir / f"c{len(clips) + 1:02d}-{key(sel.candidateId, start, length, NORMALISE_VERSION)[:8]}.mp4"
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
                    continue
            except Exception as error:  # a failed download just means one clip fewer
                print(f"   {sel.candidateId}: {str(error)[-120:]}")
                continue
            clips.append(ColdOpenClip(
                path=str(target.relative_to(ctx.root)), candidateId=sel.candidateId, url=sel.url or "",
                title=sel.title, channel=sel.channel, start=round(start, 3), end=round(start + info["duration"], 3),
                durationSeconds=round(info["duration"], 3), width=info["width"], height=info["height"],
                credit=sel.credit or "", attribution=sel.attribution,
            ))
    finally:
        youtube.close()
    ctx.write_json(OUTPUT, ColdOpenFile(slug=ctx.slug, seconds=seconds, clips=clips).model_dump())
    total = sum(c.durationSeconds for c in clips)
    print(f"   Cold open: {len(clips)} clips con sonido original · {total:.1f} s · "
          + ", ".join(c.credit.removeprefix("Fuente: ") for c in clips))


def validate(ctx: RunContext) -> bool:
    data = ColdOpenFile.model_validate(ctx.read_json(OUTPUT))
    return all((ctx.root / c.path).is_file() for c in data.clips)
