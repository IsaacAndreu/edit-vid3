"""Where the finished video goes quiet: stretches with nothing new on screen and pauses in the voice.

Our own, free stand-in for an "attention curve" (no model, no GPU, no API): the final render is read at 4 frames per
second at 160x90, and a moment "has something happening" when at least 0.5 % of the picture changes in a quarter of a
second (a cut, a label that appears, the camera moving). Measured on the reference channels: the Atlas reference has at most a
couple of gaps over 12 s in five minutes; a fast edit never goes over 4 s.

Warnings (never blocks the video):
- a stretch of `ritmo.quiet_seconds` (12) or more with nothing new on screen;
- in the first `ritmo.hook_seconds` (30), already `ritmo.hook_quiet` (6) seconds — the start is where people leave;
- a pause in the voice of `ritmo.silence_seconds` (2.5) or more.
The last END_SCREEN seconds (the end screen) are never checked.

out/<slug>/qa/ritmo.md (with what the voice says and what is on screen at each one) and qa/ritmo.json.
`python main.py --ritmo VÍDEO` runs it on a video already rendered.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

FPS = 4                   # samples per second of the picture
SIZE = (160, 90)
PIXEL_DELTA = 12          # 0-255: a pixel "changed" past this (grain and compression stay under it)
EVENT = 0.005             # share of the picture that has to change for "something happens"
AUDIO_RATE = 8000
AUDIO_STEP = 0.25         # seconds per loudness sample
SILENCE_DB = -45.0
END_SCREEN = 20.0         # seconds at the end never checked for voice pauses (end screen, music tail)


def activity(video: Path) -> np.ndarray:
    """Share of the picture that changes from each sample to the next (FPS per second)."""

    width, height = SIZE
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf",
                          f"fps={FPS},scale={width}:{height},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, height, width).astype(np.int16)
    if len(frames) < 2:
        return np.zeros(0)
    return (np.abs(np.diff(frames, axis=0)) > PIXEL_DELTA).mean(axis=(1, 2))


def loudness(video: Path) -> np.ndarray:
    """dBFS of the soundtrack every AUDIO_STEP seconds (empty when there is no audio)."""

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(AUDIO_RATE),
                          "-f", "s16le", "-"], capture_output=True).stdout
    samples = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    step = int(AUDIO_RATE * AUDIO_STEP)
    if len(samples) < step:
        return np.zeros(0)
    blocks = samples[: len(samples) // step * step].reshape(-1, step)
    return 20 * np.log10(np.sqrt((blocks ** 2).mean(axis=1)) + 1e-9)


def quiet_stretches(change: np.ndarray, least: float, event: float = EVENT) -> list[tuple[float, float]]:
    """(start, end) seconds of every run without an event that lasts `least` seconds or more."""

    found = []
    start = 0
    for i, value in enumerate(list(change) + [1.0]):       # the end closes the last run
        if value > event:
            if (i - start) / FPS >= least:
                found.append((start / FPS, i / FPS))
            start = i + 1
    return found


def silences(db: np.ndarray, least: float, duration: float) -> list[tuple[float, float]]:
    found = []
    start = None
    limit = max(0.0, duration - END_SCREEN)
    for i, value in enumerate(list(db) + [0.0]):
        if value < SILENCE_DB and i * AUDIO_STEP < limit:
            start = i if start is None else start
        elif start is not None:
            if (i - start) * AUDIO_STEP >= least:
                found.append((start * AUDIO_STEP, i * AUDIO_STEP))
            start = None
    return found


def _clock(s: float) -> str:
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def analyse(video: Path, cfg: dict[str, Any] | None = None, timeline: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    quiet = float(cfg.get("quiet_seconds", 12))
    hook_seconds = float(cfg.get("hook_seconds", 30))
    hook_quiet = float(cfg.get("hook_quiet", 6))
    pause = float(cfg.get("silence_seconds", 2.5))
    change = activity(video)
    duration = len(change) / FPS
    moving = float(np.mean(change > EVENT)) if len(change) else 0.0
    found: list[dict[str, Any]] = []
    for a, b in quiet_stretches(change, min(quiet, hook_quiet)):
        long_enough = b - a >= quiet
        in_hook = a < hook_seconds and b - a >= hook_quiet
        if (long_enough or in_hook) and a < duration - END_SCREEN:
            found.append({"kind": "quieto", "start": a, "end": b, "hook": a < hook_seconds})
    for a, b in silences(loudness(video), pause, duration):
        found.append({"kind": "silencio", "start": a, "end": b, "hook": a < hook_seconds})
    found.sort(key=lambda x: x["start"])
    if timeline:
        from .retencion import _on_screen

        for item in found:
            item["said"], item["seen"] = _on_screen(timeline, item["start"], item["end"])
    still = sum(x["end"] - x["start"] for x in found if x["kind"] == "quieto")
    return {"seconds": round(duration, 1), "moving": round(moving, 3),
            "quietShare": round(still / max(duration, 1e-9), 3), "longestQuiet": round(max(
                [b - a for a, b in quiet_stretches(change, 0.0)] or [0.0]), 1), "found": found,
            "curve": [round(float(x), 4) for x in _per_second(change)]}


def _per_second(change: np.ndarray) -> list[float]:
    if not len(change):
        return []
    whole = len(change) // FPS * FPS
    seconds = change[:whole].reshape(-1, FPS).max(axis=1).tolist()
    return seconds + ([float(change[whole:].max())] if whole < len(change) else [])


def markdown(slug: str, result: dict[str, Any]) -> str:
    found = result["found"]
    lines = [f"# Ritmo · {slug}", "",
             f"{result['moving']:.0%} del tiempo con algo moviéndose · tramo quieto más largo {result['longestQuiet']:.0f} s · "
             f"{result['quietShare']:.0%} del vídeo en tramos avisados", ""]
    if not found:
        lines.append("✅ Sin tramos quietos ni silencios largos")
    else:
        lines.append(f"⚠️ {len(found)} aviso{'s' if len(found) > 1 else ''} (no bloquean el vídeo):")
        lines.append("")
        for x in found:
            what = "sin nada nuevo en pantalla" if x["kind"] == "quieto" else "la voz calla"
            lines.append(f"- **{_clock(x['start'])}–{_clock(x['end'])}** · {x['end'] - x['start']:.0f} s {what}"
                         + (" · en el arranque" if x["hook"] else ""))
            if x.get("said"):
                lines.append(f"  - Voz: «{x['said'][:220]}»")
            if x.get("seen") and x["seen"] != "—":
                lines.append(f"  - En pantalla: {x['seen']}")
        lines += ["", "Qué hacer: un cambio de plano, un rótulo o un movimiento de cámara a mitad del tramo; "
                      "en el arranque, mejor recortar la frase."]
    return "\n".join(lines) + "\n"


def run(ctx: Any, final: Path | None = None) -> dict[str, Any] | None:
    """After the render (pipeline/render.py) or by hand (--ritmo). None when it is off or there is no video."""

    cfg = ctx.section("ritmo")
    if not cfg.get("enabled", True) or not shutil.which("ffmpeg"):
        return None
    final = final or ctx.out_dir / "video-final.mp4"
    if not final.is_file():
        return None
    timeline_path = ctx.work_dir / "timeline.json"
    timeline = json.loads(timeline_path.read_text("utf-8")) if timeline_path.is_file() else None
    result = analyse(final, cfg, timeline)
    qa = ctx.out_dir / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "ritmo.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (qa / "ritmo.md").write_text(markdown(ctx.slug, result), encoding="utf-8")
    return result


def summary(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    found = result["found"]
    quiet = sum(1 for x in found if x["kind"] == "quieto")
    silent = len(found) - quiet
    if not found:
        return f"sin tramos quietos · {result['moving']:.0%} del tiempo con movimiento"
    parts = [f"{quiet} tramo{'s' if quiet > 1 else ''} quieto{'s' if quiet > 1 else ''}" if quiet else "",
             f"{silent} silencio{'s' if silent > 1 else ''}" if silent else ""]
    return " · ".join(p for p in parts if p) + " (qa/ritmo.md)"
