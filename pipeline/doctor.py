"""Render doctor: the finished video is watched once for black and frozen frames, and what it finds is fixed.

- Black (blackdetect): a stretch where the whole picture is black, other than the first and last half second.
- Frozen (freezedetect): the same picture for longer than `doctor.freeze_seconds` in a shot of moving footage — a
  clip shorter than its shot is held on its last frame (render.shot_filter pads with clones) and reads as a freeze.
  Graphics, photos, chapter cards and the end screen hold still on purpose and are never counted.

Each problem is mapped to its render segment. A footage segment is rebuilt with its clip slowed down to fill the
shot instead of holding the last frame (at most `doctor.max_stretch`, 1.6x); any other segment is cut again
from its source (a cut that went wrong is the usual reason for a black flash). Then the video is joined again
(no re-encoding) and checked once more. out/<slug>/qa/doctor.json keeps what was found and what was fixed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

STILL_TYPES = {"chapter", "endscreen", "stat", "card", "question", "datacard", "split"}


def detect(video: Path, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """[{kind: black|frozen, start, end}] in seconds, from one pass of ffmpeg over a small copy of the picture."""

    cfg = cfg or {}
    black = float(cfg.get("black_seconds", 0.25))
    freeze = float(cfg.get("freeze_seconds", 1.0))
    chain = (f"scale=320:-2,blackdetect=d={black}:pix_th=0.08:pic_th=0.98,"
             f"freezedetect=n={float(cfg.get('freeze_noise', 0.002))}:d={freeze}")
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf", chain, "-f", "null", "-"],
                            capture_output=True, text=True)
    return parse(result.stderr)


def parse(log: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for start, end in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log):
        found.append({"kind": "black", "start": float(start), "end": float(end)})
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", log)]
    for n, start in enumerate(starts):
        found.append({"kind": "frozen", "start": start, "end": ends[n] if n < len(ends) else None})
    return sorted(found, key=lambda p: p["start"])


def still_on_purpose(timeline: dict[str, Any], a: int, b: int) -> bool:
    """Frames [a, b) where a still picture is meant: a graphic or card drawn over, a photo, a chapter card."""

    for group in timeline.get("groups", []):
        if group["from"] < b and a < group["from"] + group["durationInFrames"]:
            return True
    for shot in timeline.get("shots", []):
        if shot["from"] < b and a < shot["from"] + shot["durationInFrames"]:
            media = shot.get("media") or {}
            if shot.get("type") in STILL_TYPES or media.get("kind") != "video" or media.get("freeze"):
                return True
    return False


def problems(timeline: dict[str, Any], found: list[dict[str, Any]], fps: int) -> list[dict[str, Any]]:
    """The detections that are real problems, in frames."""

    total = timeline["durationInFrames"]
    out = []
    for p in found:
        a = int(p["start"] * fps)
        b = int((p["end"] if p["end"] is not None else total / fps) * fps)
        if p["kind"] == "black":
            a, b = max(a, fps // 2), min(b, total - fps // 2)          # a fade in or out is not a problem
            if b - a < 3:
                continue
        elif still_on_purpose(timeline, a, b):
            continue
        out.append({**p, "from": a, "to": b})
    return out


def segments_hit(segments: list[Any], problem: dict[str, Any]) -> list[int]:
    return [i for i, s in enumerate(segments) if s.start < problem["to"] and problem["from"] < s.start + s.frames]


def stretch_factor(clip_seconds: float, frames: int, offset: int, fps: int, rate: float = 1.0) -> float | None:
    """How much slower the clip must play to fill its shot (None when it already fills it)."""

    available = clip_seconds * fps / max(rate, 1e-6) - offset
    needed = frames
    if available <= 0 or available >= needed - 1:
        return None
    return needed / available


def report(path: Path, found: list[dict[str, Any]], fixed: list[str], left: list[dict[str, Any]]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"found": found, "fixed": fixed, "left": left}, ensure_ascii=False, indent=1), "utf-8")


def summary(found: list[dict[str, Any]], fixed: list[str], left: list[dict[str, Any]], fps: int) -> str:
    if not found:
        return "Render doctor: sin negros ni congelados"
    words = {"black": "negro", "frozen": "congelado"}
    rest = "; ".join(f"{words[p['kind']]} en {p['from'] / fps:.1f}s ({(p['to'] - p['from']) / fps:.1f} s)" for p in left[:5])
    return (f"Render doctor: {len(found)} problema(s), {max(0, len(found) - len(left))} arreglado(s)"
            + (f" ({', '.join(fixed[:6])})" if fixed else "")
            + (f" · quedan: {rest}" if left else ""))
