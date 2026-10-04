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


def decode_audio(audio_path: Path, rate: int = 16000):
    """16 kHz mono float32 with ffmpeg, so faster-whisper never opens the file itself: its PyAV call broke with
    av 19 («open() got an unexpected keyword argument 'metadata_errors'»)."""

    import subprocess

    import numpy as np

    done = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(audio_path), "-f", "s16le", "-ac", "1",
                           "-ar", str(rate), "-"], capture_output=True, check=True)
    return np.frombuffer(done.stdout, np.int16).astype(np.float32) / 32768.0


def _transcribe_local(audio_path: Path, model: str, language: str, compute_type: str, device: str = "cpu") -> dict[str, Any]:
    from faster_whisper import WhisperModel

    import os

    # every core: faster-whisper uses 4 threads by default, half of an 8-core server
    whisper = WhisperModel(model, device=device, compute_type=compute_type, cpu_threads=os.cpu_count() or 4)
    segments, info = whisper.transcribe(
        decode_audio(audio_path),
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


def _cuda_dlls() -> None:
    """Windows: let CTranslate2 find cuBLAS/cuDNN where pip puts them (the CUDA build of torch, nvidia-* wheels)."""

    import glob
    import os
    import site
    import sys

    if sys.platform != "win32":
        return
    roots = [*site.getsitepackages(), site.getusersitepackages()]
    for root in roots:
        for folder in [os.path.join(root, "torch", "lib"), *glob.glob(os.path.join(root, "nvidia", "*", "bin"))]:
            if os.path.isdir(folder):
                os.add_dll_directory(folder)
                os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")


def _transcribe_gpu(audio_path: Path, model: str, language: str) -> dict[str, Any] | None:
    """Whisper on an NVIDIA card, in a child process: a missing CUDA library (cuBLAS/cuDNN) can kill the
    process outright, and then the narration is simply transcribed on the processor. None = use the CPU."""

    import subprocess
    import sys
    import tempfile

    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            return None
    except Exception:
        return None
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "words.json"
        code = ("import json,sys; from pipeline.whisper_local import _cuda_dlls, _transcribe_local as t; _cuda_dlls(); "
                "json.dump(t(sys.argv[1], sys.argv[2], sys.argv[3], 'int8', 'cuda'), open(sys.argv[4], 'w', encoding='utf-8'))")
        try:
            result = subprocess.run([sys.executable, "-c", code, str(audio_path), model, language, str(out)],
                                    cwd=str(Path(__file__).resolve().parent.parent), capture_output=True, text=True,
                                    timeout=3600)
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode == 0 and out.is_file():
            print("   Whisper en la gráfica")
            return json.loads(out.read_text("utf-8"))
        tail = ((result.stderr or result.stdout) if result is not None else "tiempo agotado").strip().splitlines()[-1:] or ["?"]
        print(f"   Whisper en CPU: la gráfica no pudo ({tail[0][:100]})")
        return None


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
    device: str = "auto",
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
        raw = _transcribe_gpu(audio_path, model, language) if device in ("auto", "cuda") else None
        if raw is None:
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
