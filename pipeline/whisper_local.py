"""Raw Whisper transcription with word timestamps, cached globally by audio hash.

Only timings are taken from here: the script text is always the source of truth
(see ``pipeline/align.py``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path(cache_dir: Path, audio_path: Path, provider: str, model: str, language: str) -> Path:
    key = f"{file_sha256(audio_path)[:16]}-{provider}-{model}-{language}".replace("/", "_")
    return cache_dir / "whisper" / f"{key}.json"


def _transcribe_local(audio_path: Path, model: str, language: str, compute_type: str) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    whisper = WhisperModel(model, device="cpu", compute_type=compute_type)
    segments, info = whisper.transcribe(
        str(audio_path),
        language=language or None,
        word_timestamps=True,
        vad_filter=False,
        beam_size=5,
        condition_on_previous_text=False,
    )
    words: list[dict[str, Any]] = []
    for segment in segments:
        for word in segment.words or []:
            words.append({"word": word.word.strip(), "start": float(word.start), "end": float(word.end)})
    return {"duration": float(info.duration), "language": info.language, "words": words}


def _transcribe_openai(audio_path: Path, api_key: str) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    with audio_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
    payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    words = [
        {"word": str(item["word"]).strip(), "start": float(item["start"]), "end": float(item["end"])}
        for item in payload.get("words") or []
    ]
    return {"duration": float(payload.get("duration") or 0.0), "language": payload.get("language"), "words": words}


def transcribe(
    audio_path: Path,
    *,
    cache_dir: Path,
    provider: str = "local",
    model: str = "medium",
    language: str = "es",
    compute_type: str = "int8",
    openai_api_key: str = "",
) -> tuple[dict[str, Any], bool]:
    """Return (raw transcript, served_from_cache)."""

    cache_path = _cache_path(cache_dir, audio_path, provider, model if provider == "local" else "whisper-1", language)
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("words"):
                return cached, True
        except (OSError, json.JSONDecodeError):
            pass

    if provider == "local":
        raw = _transcribe_local(audio_path, model, language, compute_type)
    elif provider == "openai":
        if not openai_api_key:
            raise RuntimeError("align.provider=openai necesita OPENAI_API_KEY en .env.")
        raw = _transcribe_openai(audio_path, openai_api_key)
    else:
        raise ValueError(f"align.provider desconocido: {provider!r} (usa 'local' u 'openai').")

    if not raw["words"]:
        raise RuntimeError("Whisper no devolvió timestamps por palabra.")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")
    return raw, False
