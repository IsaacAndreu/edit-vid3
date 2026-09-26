from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config import Settings
from .types import Transcript, WordTimestamp


def _response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if isinstance(response, dict):
        return response
    raise TypeError("La respuesta de transcripción no tiene un formato reconocible.")


def _probe_duration_seconds(audio_path: Path) -> float:
    """Read the container duration so trailing speech/silence is not lost."""

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return max(0.0, float(result.stdout.strip()))
    except (OSError, ValueError, subprocess.CalledProcessError):
        return 0.0


def transcribe_audio(audio_path: Path, settings: Settings) -> Transcript:
    """Transcribe con Whisper API y solicita timestamps por palabra y segmento."""

    audio_path = audio_path.expanduser().resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(f"No existe el audio: {audio_path}")

    client = OpenAI(api_key=settings.openai_api_key)
    with audio_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
        )

    payload = _response_to_dict(response)
    words: list[WordTimestamp] = []
    for item in payload.get("words") or []:
        word = item.get("word") if isinstance(item, dict) else getattr(item, "word", None)
        start = item.get("start") if isinstance(item, dict) else getattr(item, "start", None)
        end = item.get("end") if isinstance(item, dict) else getattr(item, "end", None)
        if word is not None and start is not None and end is not None:
            words.append({"word": str(word), "start": float(start), "end": float(end)})

    if not words:
        raise RuntimeError(
            "Whisper no devolvió timestamps de palabras. "
            "La segmentación necesita response_format=verbose_json y granularidad word."
        )

    try:
        api_duration_seconds = float(payload.get("duration") or 0)
    except (TypeError, ValueError):
        api_duration_seconds = 0.0
    duration_seconds = max(api_duration_seconds, _probe_duration_seconds(audio_path), words[-1]["end"])

    segments: list[dict[str, Any]] = []
    for segment in payload.get("segments") or []:
        segments.append(segment if isinstance(segment, dict) else dict(segment))

    return {
        "text": str(payload.get("text") or ""),
        "duration_seconds": duration_seconds,
        "words": words,
        "segments": segments,
    }
