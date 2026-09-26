from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class RenderPostflightError(RuntimeError):
    """Raised when a rendered file fails the final technical checks."""


def master_audio(output_path: Path) -> None:
    """Normalize the final mix without re-encoding the video stream."""

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RenderPostflightError("No se encontró ffmpeg para masterizar el audio final.")

    temporary_path = output_path.with_name(f"{output_path.stem}.audio-mastered.tmp{output_path.suffix}")
    if temporary_path.exists():
        temporary_path.unlink()

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(output_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        "-af",
        "loudnorm=I=-16:LRA=7:TP=-1.5:print_format=summary",
        "-ac",
        "2",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(temporary_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        temporary_path.replace(output_path)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        suffix = f" Detalle: {detail[-500:]}" if detail else ""
        raise RenderPostflightError(f"Falló la masterización de audio.{suffix}") from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def inspect_render(
    output_path: Path, expected_duration_seconds: float, size: tuple[int, int] = (1920, 1080)
) -> list[dict[str, Any]]:
    """Check container, streams, resolution and A/V duration after rendering."""

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RenderPostflightError("No se encontró ffprobe para verificar el render final.")

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        suffix = f" Detalle: {detail[-500:]}" if detail else ""
        raise RenderPostflightError(f"No se pudo inspeccionar el render final.{suffix}") from error
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    issues: list[dict[str, Any]] = []

    if video is None:
        issues.append({"code": "missing-video", "message": "El render no contiene stream de vídeo."})
    else:
        if (video.get("width"), video.get("height")) != size:
            issues.append(
                {
                    "code": "invalid-resolution",
                    "message": f"Resolución inesperada: {video.get('width')}x{video.get('height')}.",
                }
            )
    if audio is None:
        issues.append({"code": "missing-audio", "message": "El render no contiene stream de audio."})

    durations = []
    for label, stream in (("video", video), ("audio", audio)):
        if stream and stream.get("duration") is not None:
            duration = float(stream["duration"])
            durations.append((label, duration))
            if abs(duration - expected_duration_seconds) > 0.15:
                issues.append(
                    {
                        "code": "duration-drift",
                        "message": f"Duración {label}: {duration:.3f}s; esperada: {expected_duration_seconds:.3f}s.",
                    }
                )

    if len(durations) == 2 and abs(durations[0][1] - durations[1][1]) > 0.1:
        issues.append({"code": "av-duration-mismatch", "message": "Los streams de vídeo y audio no terminan juntos."})

    return issues


def write_postflight_report(path: Path, issues: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"status": "error" if issues else "ok", "issues": issues}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def enforce_postflight(issues: list[dict[str, Any]]) -> None:
    if issues:
        details = " ".join(f"[{issue['code']}] {issue['message']}" for issue in issues)
        raise RenderPostflightError(f"Postflight bloqueado: {details}")
