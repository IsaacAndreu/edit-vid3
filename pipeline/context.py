from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .config import PROJECT_ROOT, ConfigError


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or PROJECT_ROOT / "config.yaml"
    if not config_path.is_file():
        raise ConfigError(f"No existe {config_path}.")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} debe contener un mapa YAML.")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        merged[key] = deep_merge(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) else value
    return merged


@dataclass
class RunContext:
    """Everything a stage needs to locate its inputs and outputs. No stage state lives here."""

    slug: str
    root: Path
    config: dict[str, Any]
    _env_loaded: bool = field(default=False, repr=False)

    @classmethod
    def create(cls, slug: str, *, root: Path = PROJECT_ROOT, config: dict[str, Any] | None = None) -> "RunContext":
        if config is not None:
            return cls(slug=slug, root=root, config=config)
        base = load_config(root / "config.yaml")
        ctx = cls(slug=slug, root=root, config=base)
        # Per-video overrides: materiales/<slug>/config.yaml (e.g. timeline: {cold_open_seconds: 10}).
        override = ctx.materials_dir / "config.yaml"
        if override.is_file():
            ctx.config = deep_merge(base, load_config(override))
        return ctx

    def _dir(self, key: str, default: str) -> Path:
        return self.root / str(self.config.get("paths", {}).get(key, default))

    @property
    def materials_dir(self) -> Path:
        return self._dir("materials", "materiales") / self.slug

    @property
    def work_dir(self) -> Path:
        return self._dir("work", "work") / self.slug

    @property
    def out_dir(self) -> Path:
        return self._dir("out", "out") / self.slug

    @property
    def cache_dir(self) -> Path:
        return self._dir("cache", "cache")

    @property
    def fps(self) -> int:
        return int(self.config.get("video", {}).get("fps", 30))

    def section(self, name: str) -> dict[str, Any]:
        value = self.config.get(name, {})
        return value if isinstance(value, dict) else {}

    def env(self, name: str, *, required: bool = True) -> str:
        """Read an API key lazily so a stage only demands the keys it really uses."""

        if not self._env_loaded:
            load_dotenv(self.root / ".env", override=False)
            self._env_loaded = True
        value = os.getenv(name, "").strip()
        if required and not value:
            raise ConfigError(f"Falta {name} en .env (o en las variables de entorno).")
        return value

    def write_json(self, relative: str, payload: Any) -> Path:
        path = self.work_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def read_json(self, relative: str) -> Any:
        return json.loads((self.work_dir / relative).read_text(encoding="utf-8"))
