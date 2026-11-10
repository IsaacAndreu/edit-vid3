"""Small shared wrappers around ffprobe so every stage reads durations the same way."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path


class MediaToolError(RuntimeError):
    """ffprobe is missing or could not read the file."""


def probe_duration_seconds(path: Path | str, *, timeout: float = 30.0) -> float:
    """Return the container duration in seconds or raise ``MediaToolError``."""

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MediaToolError("ffprobe was not found; install ffmpeg/ffprobe and add it to PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError(f"ffprobe timed out after {timeout:.0f}s reading {path}.") from exc
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[:400]
        raise MediaToolError(f"Could not read media duration with ffprobe. {detail}".strip())
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaToolError("ffprobe returned no valid media duration.") from exc
    if not math.isfinite(duration):
        raise MediaToolError("ffprobe returned a non-finite media duration.")
    return duration
