"""Colour matching: every clip and photo brought towards the same exposure, contrast, saturation and
white balance, plus a common look per channel — so footage from a 1972 broadcast, a 2010 TV feed and a
fan's phone reads as one edit instead of a compilation.

Measured on a few small frames of the piece that will be used (after the same crop/fit as the output),
then corrected only part of the way (`grade.strength`), with hard limits: a night scene stays a night
scene, a black-and-white photo is never tinted. Applied while normalising (ingest/fallback), so the
render does not pay for it.

    grade:
      enabled: true
      strength: 0.6          # 0 = untouched, 1 = all the way to the targets
      luma: 0.45             # target mean brightness (0-1)
      contrast: 0.22         # target spread of brightness (standard deviation, 0-1)
      saturation: 0.30       # target mean saturation (0-1)
      warmth: 0.02           # target red-minus-blue balance (0 neutral, + warm, − cold)
      look: cine             # common tone: neutral | cine | frio | calido
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

LOOKS = {
    "neutral": "",
    # teal shadows, warm highlights: the usual documentary/sports grade
    "cine": ",colorbalance=rs=-0.03:gs=0.0:bs=0.04:rh=0.04:gh=0.01:bh=-0.03",
    "frio": ",colorbalance=rs=-0.02:bs=0.03:rm=-0.02:bm=0.03",
    "calido": ",colorbalance=rm=0.03:bm=-0.03:rh=0.02:bh=-0.02",
}
SIZE = (192, 108)


def frames(source: Path, prefilter: str, offset: float = 0.0, duration: float | None = None,
           image: bool = False) -> np.ndarray | None:
    """Up to 8 small RGB frames (float 0-1) of the part that will be used."""

    w, h = SIZE
    cmd = ["ffmpeg", "-v", "error"]
    if not image and offset > 0:
        cmd += ["-ss", f"{offset:.3f}"]
    cmd += ["-i", str(source)]
    if not image and duration:
        cmd += ["-t", f"{duration:.3f}"]
    rate = "" if image else "fps=3,"
    cmd += ["-vf", f"{rate}{prefilter},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1:color=black@0,format=rgb24",
            "-frames:v", "1" if image else "8", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, check=True, timeout=120).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    if len(raw) < w * h * 3:
        return None
    data = np.frombuffer(raw[: len(raw) // (w * h * 3) * w * h * 3], dtype=np.uint8)
    return data.reshape(-1, h, w, 3).astype(np.float32) / 255.0


def stats(rgb: np.ndarray) -> dict[str, float] | None:
    """Mean/spread of brightness, mean saturation and red-blue balance, ignoring the padding (pure black)."""

    pixels = rgb.reshape(-1, 3)
    keep = pixels.max(axis=1) > 0.004
    if keep.sum() < 50:
        return None
    pixels = pixels[keep]
    luma = pixels @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    top, low = pixels.max(axis=1), pixels.min(axis=1)
    lit = top > 0.08
    saturation = float(((top - low)[lit] / top[lit]).mean()) if lit.any() else 0.0
    return {"luma": float(luma.mean()), "contrast": float(luma.std()), "saturation": saturation,
            "warmth": float((pixels[:, 0] - pixels[:, 2]).mean())}


def correction(measured: dict[str, float], cfg: dict[str, Any]) -> dict[str, float]:
    """eq contrast/brightness/saturation and red/blue gains, part of the way to the targets."""

    k = max(0.0, min(1.0, float(cfg.get("strength", 0.6))))
    m, s = measured["luma"], measured["contrast"]
    contrast = 1.0
    if s > 0.02:
        contrast = float(np.clip((float(cfg.get("contrast", 0.22)) / s) ** k, 0.85, 1.25))
    wanted = m + k * (float(cfg.get("luma", 0.45)) - m)
    brightness = float(np.clip(wanted - ((m - 0.5) * contrast + 0.5), -0.10, 0.10))
    colour = measured["saturation"] > 0.08          # black-and-white stays black-and-white
    saturation = float(np.clip((float(cfg.get("saturation", 0.30)) / max(measured["saturation"], 0.05)) ** k, 0.8, 1.25)) if colour else 1.0
    shift = float(np.clip(k * (float(cfg.get("warmth", 0.02)) - measured["warmth"]), -0.08, 0.08)) if colour else 0.0
    return {"contrast": contrast, "brightness": brightness, "saturation": saturation, "red": 1 + shift, "blue": 1 - shift}


def filters(c: dict[str, float], look: str = "neutral") -> str:
    """ffmpeg filter chain (starting with a comma) for a correction plus the channel look."""

    chain = f",eq=contrast={c['contrast']:.3f}:brightness={c['brightness']:.3f}:saturation={c['saturation']:.3f}"
    if abs(c["red"] - 1) > 0.004:
        chain += f",colorchannelmixer=rr={c['red']:.3f}:bb={c['blue']:.3f}"
    return chain + LOOKS.get(str(look), "")


def grade_filter(source: Path, prefilter: str, cfg: dict[str, Any] | None, *, offset: float = 0.0,
                 duration: float | None = None, image: bool = False) -> str:
    """The grade for one piece of media, or "" when disabled or it cannot be measured."""

    if not cfg or not cfg.get("enabled", True):
        return ""
    rgb = frames(source, prefilter, offset, duration, image)
    measured = stats(rgb) if rgb is not None else None
    if measured is None:
        return LOOKS.get(str(cfg.get("look", "neutral")), "")
    return filters(correction(measured, cfg), str(cfg.get("look", "neutral")))
