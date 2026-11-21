"""How long one third-party clip may run on screen: `content.max_third_party_seconds`, per channel and per video.

It used to be a constant (MAX_THIRD_PARTY_SECONDS = 5 s) checked in 29 places. On 21-11 the owner decided to work as
the competition does (11 s of a crowd, 50 s of a game scene) and to take the risk of claims, channel by channel:

- `content.max_third_party_seconds` (5 when nothing is set): the cap of a clip from YouTube or an archive;
- your own clips (source «propio») have none; the quoted passages with their own sound keep `quotes.max_seconds`.

Neither key makes a stage run again (runner.SPEED_KEYS): a video half made with 5 s goes on with 5 s clips and
validates; only what is cut from now on may run longer. The schemas check a wide ceiling (HARD_LIMIT_SECONDS); the
real per-video cap is applied by the stages and checked again by QA before the render. To lower it in one channel
(claims), set the key in its profile: nothing else changes.
"""

from __future__ import annotations

from typing import Any

from .schemas import HARD_LIMIT_SECONDS, MAX_THIRD_PARTY_SECONDS


def seconds(ctx: Any) -> float:
    """The cap of this video, between 1 s and HARD_LIMIT_SECONDS."""

    try:
        cfg = ctx.section("content") or {}
    except Exception:
        cfg = {}
    value = cfg.get("max_third_party_seconds", MAX_THIRD_PARTY_SECONDS)
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = MAX_THIRD_PARTY_SECONDS
    return max(1.0, min(HARD_LIMIT_SECONDS, value))


def longest_runs(timeline: dict[str, Any], fps: float | None = None) -> list[dict[str, Any]]:
    """Per source on screen, its longest unbroken run in seconds (consecutive shots of one file, played one after the
    other): what a claim on a video can be matched with. Longest first."""

    fps = float(fps or timeline.get("fps") or 30)
    best: dict[str, dict[str, Any]] = {}
    run_src, run_frames, run_from = None, 0, 0
    for shot in sorted(timeline.get("shots") or [], key=lambda s: int(s.get("from") or 0)):
        media = shot.get("media") or {}
        if media.get("kind") != "video" or media.get("source") in (None, "generated", "propio"):
            run_src, run_frames = None, 0
            continue
        src = str(media.get("src") or "")
        frames = int(shot.get("durationInFrames") or 0) * float(media.get("rate") or 1.0)
        if src == run_src:
            run_frames += frames
        else:
            run_src, run_frames, run_from = src, frames, int(shot.get("from") or 0)
        key = str(media.get("credit") or src)
        seconds_ = round(run_frames / fps, 1)
        if key not in best or seconds_ > best[key]["seconds"]:
            best[key] = {"source": key, "seconds": seconds_, "at": round(run_from / fps, 1), "src": src}
    return sorted(best.values(), key=lambda r: -r["seconds"])
