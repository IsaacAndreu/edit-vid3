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

    return Settings(
        project_root=PROJECT_ROOT,
        llm_provider=provider,
        llm_model=model,
        llm_api_key=values["LLM_API_KEY"],
        pexels_api_key=values["PEXELS_API_KEY"],
        openai_api_key=values["OPENAI_API_KEY"],
        deepseek_vision_model=vision_model,
    )
