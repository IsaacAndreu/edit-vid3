from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REMOTION_FPS = 30
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


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
    # Optional. Residential proxy for YouTube media bytes (googlevideo.com),
    # used by yt-dlp and the ffmpeg range download it drives.
    youtube_proxy: str | None = None
    # Optional. Proxy for YouTube metadata (search, video page/player, subtitles).
    # Falls back to youtube_proxy so media URLs stay bound to the fetching IP.
    youtube_metadata_proxy: str | None = None
    # Shared on-disk cache: yt-dlp player data, info dicts per video id and the
    # clip library reused across runs.
    youtube_cache_dir: Path = PROJECT_ROOT / ".cache"
    youtube_max_height: int = 720

    @property
    def deepseek_base_url(self) -> str:
        return DEEPSEEK_BASE_URL


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
    youtube_proxy = os.getenv("YOUTUBE_PROXY", "").strip() or None
    youtube_metadata_proxy = os.getenv("YOUTUBE_METADATA_PROXY", "").strip() or None
    cache_dir_value = os.getenv("YOUTUBE_CACHE_DIR", "").strip()
    youtube_cache_dir = Path(cache_dir_value).expanduser() if cache_dir_value else PROJECT_ROOT / ".cache"
    max_height_value = os.getenv("YOUTUBE_MAX_HEIGHT", "720").strip()

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
    try:
        youtube_max_height = int(max_height_value)
    except ValueError as error:
        raise ConfigError("YOUTUBE_MAX_HEIGHT debe ser un entero (por ejemplo 720).") from error
    if youtube_max_height < 144:
        raise ConfigError("YOUTUBE_MAX_HEIGHT debe ser al menos 144.")

    return Settings(
        project_root=PROJECT_ROOT,
        llm_provider=provider,
        llm_model=model,
        llm_api_key=values["LLM_API_KEY"],
        pexels_api_key=values["PEXELS_API_KEY"],
        openai_api_key=values["OPENAI_API_KEY"],
        deepseek_vision_model=vision_model,
        youtube_proxy=youtube_proxy,
        youtube_metadata_proxy=youtube_metadata_proxy,
        youtube_cache_dir=youtube_cache_dir,
        youtube_max_height=youtube_max_height,
    )
