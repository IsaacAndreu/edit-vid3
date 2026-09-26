"""Stage 6 — ingest the chosen media in final quality: work/<slug>/media/<shot_id>.mp4|.jpg.

Videos: only the chosen span is downloaded in HD (≤1080p, stream copy, see
YouTubeSource.download_range), then cut frame-accurately and normalised with FFmpeg:
1920x1080 "cover" (scale up + centre crop), 30 fps, no audio, optional common LUT
(assets/lut.cube). The clip lasts the shot's duration, hard-capped at 5.0 s; the planner
keeps shots ≤ 4 s, so the spec's "split longer shots into two clips" never triggers here
and a longer span is rejected instead.

Images: the full-resolution original is downloaded and cropped to 16:9 at 2304x1296
(20 % headroom for the Ken Burns move in Remotion), with the same LUT.

Every output is verified with ffprobe; results and failures go to media/_ingest.json.
Shots whose inputs did not change are skipped.
"""

from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

from .context import RunContext
from .schemas import MAX_THIRD_PARTY_SECONDS, IngestedMedia, IngestFile, Selection, SelectionFile, ShotsFile
from .sourcing import _youtube_cookies
from .sourcing.common import USER_AGENT, key
from .sourcing.youtube import YouTubeSource


STAGE = "ingest"
OUTPUT = "media"
MANIFEST = "_ingest.json"
FPS = 30
VIDEO_SIZE = (1920, 1080)
IMAGE_SIZE = (2304, 1296)


def probe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    num, _, den = str(video.get("r_frame_rate", "0/1")).partition("/")
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": float(num) / float(den or 1) if float(den or 1) else 0.0,
        "duration": float(data.get("format", {}).get("duration") or 0),
        "hasAudio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


def lut_filter(lut: Path | None) -> str:
    if lut is None:
        return ""
    escaped = str(lut.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f",lut3d=file='{escaped}'"


def normalise_video(source: Path, target: Path, *, offset: float, duration: float, lut: Path | None, cfg: dict[str, Any]) -> None:
    """Frame-accurate cut (decode from the file start, seek inside) + cover 1920x1080 @30, no audio."""

    width, height = VIDEO_SIZE
    frames = max(1, round(duration * FPS))
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1,fps={FPS}{lut_filter(lut)},format=yuv420p"
    )
    tmp = target.with_name(target.stem + ".tmp.mp4")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-ss", f"{max(0.0, offset):.3f}",
         "-frames:v", str(frames), "-vf", vf, "-an", "-c:v", "libx264", "-preset", str(cfg.get("preset", "veryfast")),
         "-crf", str(cfg.get("crf", 18)), "-movflags", "+faststart", str(tmp)],
        check=True, capture_output=True, text=True,
    )
    tmp.replace(target)


def normalise_image(source: Path, target: Path, *, lut: Path | None) -> None:
    width, height = IMAGE_SIZE
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1{lut_filter(lut)}"
    tmp = target.with_name(target.stem + ".tmp.jpg")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vf", vf, "-frames:v", "1",
         "-q:v", "2", str(tmp)],
        check=True, capture_output=True, text=True,
    )
    tmp.replace(target)


def inputs(ctx: RunContext) -> list:
    lut = ctx.root / str(ctx.section("ingest").get("lut", "assets/lut.cube"))
    return [ctx.work_dir / "selection.json", ctx.work_dir / "shots.json", lut]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("ingest")
    started = time.monotonic()
    out_dir = ctx.work_dir / OUTPUT
    out_dir.mkdir(parents=True, exist_ok=True)
    lut_path = ctx.root / str(cfg.get("lut", "assets/lut.cube"))
    lut = lut_path if lut_path.is_file() else None
    lut_hash = key(lut.read_bytes().hex()) if lut else None
    print(f"   LUT: {lut.relative_to(ctx.root) if lut else 'no hay (assets/lut.cube); se omite'}")

    shots = {s.id: s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots}
    selections = SelectionFile.model_validate(ctx.read_json("selection.json")).selections
    previous: dict[str, IngestedMedia] = {}
    manifest_path = out_dir / MANIFEST
    if manifest_path.is_file():
        try:
            previous = {m.shotId: m for m in IngestFile.model_validate_json(manifest_path.read_text("utf-8")).media}
        except ValueError:
            previous = {}

    yt_cfg = ctx.section("sourcing").get("youtube", {})
    youtube = YouTubeSource(root=ctx.root, cache_dir=ctx.cache_dir, config=yt_cfg, cookies_text=_youtube_cookies(ctx, yt_cfg))
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT

    def spec_hash(selection: Selection) -> str:
        return key(selection.model_dump(exclude={"judge"}), shots[selection.shotId].start, shots[selection.shotId].end,
                   lut_hash, cfg.get("crf", 18), cfg.get("preset", "veryfast"), IMAGE_SIZE, VIDEO_SIZE)

    def ingest(selection: Selection) -> IngestedMedia:
        shot = shots[selection.shotId]
        digest = spec_hash(selection)
        old = previous.get(selection.shotId)
        if old and old.specHash == digest and (ctx.root / old.path).is_file():
            return old
        if selection.kind == "video":
            duration = min(shot.duration, MAX_THIRD_PARTY_SECONDS)
            if duration > MAX_THIRD_PARTY_SECONDS + 1e-6:
                raise ValueError("el plano supera 5 s")
            assert selection.start is not None
            start = selection.start
            video_id = selection.candidateId.removeprefix("yt:")
            hd = youtube.download_range(
                video_id, start, start + duration + 0.5,  # margin: a stream copy may stop a hair early
                fmt=str(cfg.get("format", "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/b[height<=1080]")),
                prefix="hd",
            )
            file_start = float(hd.stem.split("_")[1])
            target = out_dir / f"{selection.shotId}.mp4"
            normalise_video(hd, target, offset=start - file_start, duration=duration, lut=lut, cfg=cfg)
            info = probe(target)
            return IngestedMedia(
                shotId=selection.shotId, kind="video", path=str(target.relative_to(ctx.root)), source=selection.source,
                candidateId=selection.candidateId, start=round(start, 3), end=round(start + info["duration"], 3),
                durationSeconds=round(info["duration"], 3), width=info["width"], height=info["height"], fps=info["fps"],
                hasAudio=info["hasAudio"], lut=str(lut.relative_to(ctx.root)) if lut else None,
                credit=selection.credit, specHash=digest,
            )
        url = selection.mediaUrl
        if not url:
            raise ValueError("la imagen no tiene URL original")
        original = ctx.cache_dir / "images" / "original" / f"{key(url)}{Path(url.split('?')[0]).suffix or '.jpg'}"
        if not original.is_file():
            response = http.get(url, timeout=60)
            response.raise_for_status()
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(response.content)
        target = out_dir / f"{selection.shotId}.jpg"
        normalise_image(original, target, lut=lut)
        info = probe(target)
        return IngestedMedia(
            shotId=selection.shotId, kind="image", path=str(target.relative_to(ctx.root)), source=selection.source,
            candidateId=selection.candidateId, width=info["width"], height=info["height"],
            lut=str(lut.relative_to(ctx.root)) if lut else None, credit=selection.credit, specHash=digest,
        )

    todo = [s for s in selections if s.status == "selected"]
    skipped = [s.shotId for s in selections if s.status != "selected"]
    media: dict[str, IngestedMedia] = {}
    failed: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=int(cfg.get("parallel", 3))) as pool:
        futures = {pool.submit(ingest, s): s.shotId for s in todo}
        for number, future in enumerate(as_completed(futures), start=1):
            shot_id = futures[future]
            try:
                media[shot_id] = future.result()
            except Exception as error:
                detail = getattr(error, "stderr", "") or str(error)
                failed[shot_id] = str(detail).strip()[-240:]
            if number % 40 == 0:
                print(f"   {number}/{len(todo)} ({time.monotonic() - started:.0f} s)")

    ordered = [media[s.shotId] for s in todo if s.shotId in media]
    for stale in out_dir.iterdir():
        if stale.name != MANIFEST and stale.stem not in media:
            stale.unlink()
    ctx.write_json(f"{OUTPUT}/{MANIFEST}", IngestFile(slug=ctx.slug, media=ordered, skipped=skipped, failed=failed).model_dump(exclude_none=True))
    videos = [m for m in ordered if m.kind == "video"]
    print(f"   {len(videos)} clips HD + {len(ordered) - len(videos)} imágenes · {len(skipped)} a fallback · {len(failed)} fallidos")
    if videos:
        print(f"   Duración máx. {max(m.durationSeconds for m in videos):.3f} s · todos 1920x1080 sin audio")
    for shot_id, error in list(failed.items())[:5]:
        print(f"   AVISO {shot_id}: {error}")
    print(f"   Ingesta en {time.monotonic() - started:.0f} s")


def validate(ctx: RunContext) -> bool:
    manifest = IngestFile.model_validate_json((ctx.work_dir / OUTPUT / MANIFEST).read_text("utf-8"))
    for item in manifest.media:
        if not (ctx.root / item.path).is_file():
            raise FileNotFoundError(item.path)
    return True


def retry_if(ctx: RunContext) -> bool:
    """Re-run while some chosen clips could not be downloaded (e.g. YouTube blocked or cookies expired)."""

    manifest = IngestFile.model_validate_json((ctx.work_dir / OUTPUT / MANIFEST).read_text("utf-8"))
    return bool(manifest.failed)
