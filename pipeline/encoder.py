"""Which H.264 encoder to use: the NVIDIA card's (NVENC) when it works, else x264 on the processor.

`render.encoder`: auto (default) | nvenc | x264. NVENC is tried once per run with a tiny test encode;
any failure means x264, so a machine without a card (or with old drivers) renders exactly as before.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def nvenc_works() -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=0.2:r=30",
                                 "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def use_nvenc(cfg: dict) -> bool:
    choice = str(cfg.get("encoder", "auto") or "auto").lower()
    if choice == "x264":
        return False
    return nvenc_works()


def video_args(cfg: dict, crf: int | float, preset: str = "veryfast", nvenc: bool | None = None) -> list[str]:
    """ffmpeg arguments for an H.264 yuv420p stream of about the quality of x264 at `crf`."""

    if nvenc if nvenc is not None else use_nvenc(cfg):
        # constant quality (cq ≈ crf), p5 = good quality at many times x264's speed on a GTX 16xx
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(int(round(float(crf)))), "-b:v", "0",
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
