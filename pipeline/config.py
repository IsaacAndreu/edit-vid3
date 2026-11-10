from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .templates import PROJECT_ROOT, load_manifest


REMOTION_FPS = load_manifest().fps
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

DEFAULT_MEDIA_CONCURRENCY = 3
DEFAULT_YOUTUBE_PARALLEL = 4
WORDS_FORMATS = ("compact", "full")


class ConfigError(ValueError):
    """Raised when the pipeline cannot start with the current environment."""


@dataclass(frozen=True)
class Settings:
    project_root: Path
    llm_provider: str
    llm_model: str
    llm_api_key: str
    pexels_api_key: str
    openai_api_key: str
    deepseek_vision_model: str
    # Optional tuning. Every value has an environment override documented in .env.example.
    media_concurrency: int = DEFAULT_MEDIA_CONCURRENCY
    youtube_parallel: int = DEFAULT_YOUTUBE_PARALLEL
    youtube_single_pass: bool = True
    download_stock: bool = True
    segment_words_format: str = "compact"
    render_concurrency: str | None = None

    @property
    def deepseek_base_url(self) -> str:
        return DEEPSEEK_BASE_URL


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(f"{name}={raw!r} debe ser un entero entre {minimum} y {maximum}.") from error
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name}={value} debe estar entre {minimum} y {maximum}.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "si", "sí", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name}={raw!r} debe ser 1 o 0.")


def load_settings(env_file: Path | None = None) -> Settings:
    """Load and validate settings before any pipeline work starts."""

    dotenv_path = env_file or PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)

    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    model = os.getenv("LLM_MODEL", "deepseek-flash").strip()
    values = {
        "LLM_API_KEY": os.getenv("LLM_API_KEY", "").strip(),
        "PEXELS_API_KEY": os.getenv("PEXELS_API_KEY", "").strip(),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
    }
    vision_model = os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-flash").strip()

    missing = [name for name, value in values.items() if not value]
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(
            f"Faltan variables obligatorias en {dotenv_path}: {joined}. "
            "Copia .env.example a .env y completa las API keys."
        )

    if provider != "deepseek":
        raise ConfigError(
            f"LLM_PROVIDER={provider!r} no está implementado todavía; "
            "el esqueleto actual soporta únicamente 'deepseek'."
        )

    if not model:
        raise ConfigError("LLM_MODEL no puede estar vacío.")
    if not vision_model:
        raise ConfigError("DEEPSEEK_VISION_MODEL no puede estar vacío.")

    words_format = os.getenv("SEGMENT_WORDS_FORMAT", "compact").strip().lower() or "compact"
    if words_format not in WORDS_FORMATS:
        raise ConfigError(
            f"SEGMENT_WORDS_FORMAT={words_format!r} no es válido; usa 'compact' o 'full'."
        )

    return Settings(
        project_root=PROJECT_ROOT,
        llm_provider=provider,
        llm_model=model,
        llm_api_key=values["LLM_API_KEY"],
        pexels_api_key=values["PEXELS_API_KEY"],
        openai_api_key=values["OPENAI_API_KEY"],
        deepseek_vision_model=vision_model,
        media_concurrency=_env_int("MEDIA_CONCURRENCY", DEFAULT_MEDIA_CONCURRENCY, minimum=1, maximum=8),
        youtube_parallel=_env_int("YOUTUBE_PARALLEL", DEFAULT_YOUTUBE_PARALLEL, minimum=1, maximum=12),
        youtube_single_pass=_env_bool("YOUTUBE_SINGLE_PASS", True),
        download_stock=_env_bool("PEXELS_DOWNLOAD", True),
        segment_words_format=words_format,
        render_concurrency=os.getenv("REMOTION_CONCURRENCY", "").strip() or None,
    )
