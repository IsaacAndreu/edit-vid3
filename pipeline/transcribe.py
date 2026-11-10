from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .cache import JsonCache, sha256_file, sha256_text
from .config import Settings
from .media_tools import MediaToolError, probe_duration_seconds
from .runlog import log
from .timing import METRICS
from .types import Transcript, WordTimestamp


WHISPER_MODEL = "whisper-1"
# The transcription endpoint rejects uploads above 25 MB.
WHISPER_UPLOAD_LIMIT_BYTES = 25 * 1024 * 1024
_UPLOAD_COMFORT_BYTES = 24 * 1024 * 1024
_CACHE_NAMESPACE = "transcripts"
_CACHE_VARIANT = "verbose_json:word,segment:v1"


def _response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if isinstance(response, dict):
        return response
    raise TypeError("La respuesta de transcripción no tiene un formato reconocible.")


def _probe_duration_seconds(audio_path: Path) -> float:
    """Read the container duration so trailing speech/silence is not lost."""

    try:
        return max(0.0, probe_duration_seconds(audio_path))
    except MediaToolError:
        return 0.0


@contextmanager
def _upload_source(audio_path: Path) -> Iterator[Path]:
    """Yield a file Whisper accepts: the original, or a small mono copy when it is too big."""

    size = audio_path.stat().st_size
    if size <= _UPLOAD_COMFORT_BYTES:
        yield audio_path
        return

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            f"El audio pesa {size / 1_048_576:.1f} MB y Whisper admite 25 MB. "
            "Instala ffmpeg para que el pipeline lo comprima antes de subirlo, o conviértelo a MP3."
        )
    with tempfile.TemporaryDirectory(prefix="edit20-whisper-") as temp_dir:
        compact = Path(temp_dir) / "upload.mp3"
        log.info(
            f"   El audio pesa {size / 1_048_576:.1f} MB; se sube una copia mono a 48 kbps "
            "(los timestamps no cambian)."
        )
        result = subprocess.run(
            [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
                str(compact),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not compact.is_file():
            detail = (result.stderr or "").strip()[-300:]
            raise RuntimeError(f"ffmpeg no pudo comprimir el audio para Whisper. {detail}".strip())
        if compact.stat().st_size > WHISPER_UPLOAD_LIMIT_BYTES:
            raise RuntimeError(
                "Incluso comprimido, el audio supera los 25 MB que admite Whisper "
                "(más de una hora de voz). Divide la narración en dos vídeos."
            )
        yield compact


def _valid_cached_transcript(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("words"), list)
        and bool(payload["words"])
        and isinstance(payload.get("duration_seconds"), (int, float))
        and all(
            isinstance(word, dict) and {"word", "start", "end"} <= set(word)
            for word in payload["words"]
        )
    )


def transcribe_audio(
    audio_path: Path,
    settings: Settings,
    *,
    cache: JsonCache | None = None,
) -> Transcript:
    """Transcribe con Whisper API y solicita timestamps por palabra y segmento.

    With ``cache`` the result is stored by audio content hash, so re-running the
    same narration never pays for (or waits on) a second transcription.
    """

    audio_path = audio_path.expanduser().resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(f"No existe el audio: {audio_path}")

    cache_key = ""
    if cache is not None:
        cache_key = sha256_text(sha256_file(audio_path), WHISPER_MODEL, _CACHE_VARIANT)
        cached = cache.get(_CACHE_NAMESPACE, cache_key)
        if _valid_cached_transcript(cached):
            METRICS.count("whisper.cache_hits")
            log.info("   Transcripción reutilizada de la caché (sin llamada a Whisper).")
            return cached  # type: ignore[return-value]

    # Imported lazily so the rest of the pipeline works without the SDK loaded.
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    with _upload_source(audio_path) as upload_path, upload_path.open("rb") as audio_file:
        METRICS.count("whisper.calls")
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
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

    transcript: Transcript = {
        "text": str(payload.get("text") or ""),
        "duration_seconds": duration_seconds,
        "words": words,
        "segments": segments,
    }
    if cache is not None:
        cache.put(_CACHE_NAMESPACE, cache_key, transcript)
    return transcript
