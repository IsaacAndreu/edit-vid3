"""Optional cold open — work/<slug>/coldopen.json + coldopen/.

With `timeline.cold_open_seconds: N` (usually set per video in materiales/<slug>/config.yaml),
the video opens with N seconds of the protagonist's peak moments WITH their original sound
(crowd, commentators) before the narration starts, as sports channels do. The fragments are the
ones the judge already picked for the hook shots (which search for the protagonist's peak), each
one at most 5 s and with its source credit; their audio is levelled and mixed under nothing else.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from .context import RunContext
from .ingest import FPS, NORMALISE_VERSION, _frame_filter, find_lut, lut_filter, probe
from .schemas import MAX_THIRD_PARTY_SECONDS, ColdOpenClip, ColdOpenFile, SelectionFile, ShotsFile
from .sourcing import youtube_source
from .sourcing.common import key

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
    vf = f"{_frame_filter(source, 1920, 1080)},setsar=1,fps={FPS}{lut_filter(lut)},format=yuv420p"
    tmp = target.with_name(target.stem + ".tmp.mp4")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-ss", f"{max(0.0, offset):.3f}",
         "-frames:v", str(frames), "-t", f"{frames / FPS:.3f}", "-vf", vf,
         "-af", "aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "2", "-c:a", "aac", "-b:a", "192k",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-movflags", "+faststart", str(tmp)],
        check=True, capture_output=True, text=True,
    )
    tmp.replace(target)


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "selection.json", ctx.work_dir / "shots.json"]


def run(ctx: RunContext) -> None:
    seconds = float(ctx.section("timeline").get("cold_open_seconds", 0) or 0)
    if seconds <= 0:
        ctx.write_json(OUTPUT, ColdOpenFile(slug=ctx.slug).model_dump())
        print("   Sin cold open (timeline.cold_open_seconds = 0)")
        return
    hook_seconds = float(ctx.section("judge").get("hook_seconds", 30))
    shots = {s.id: s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots}
    picks, seen = [], set()
    for sel in SelectionFile.model_validate(ctx.read_json("selection.json")).selections:
        shot = shots.get(sel.shotId)
        if (shot is None or shot.start >= hook_seconds or sel.status != "selected" or sel.source != "youtube"
                or sel.kind != "video" or sel.candidateId in seen or sel.start is None):
            continue
        seen.add(sel.candidateId)
        picks.append(sel)
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
            start = max(0.0, float(sel.start) - 0.3)
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
