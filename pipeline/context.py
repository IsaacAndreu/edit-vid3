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


CHANNELS_DIR = "canales"


def channel_profile(root: Path, name: str) -> dict[str, Any]:
    """canales/<name>.yaml: what makes a channel look and search like itself (brand, music, sources, ideas…)."""

    path = root / CHANNELS_DIR / f"{name}.yaml"
    if not path.is_file():
        known = sorted(p.stem for p in (root / CHANNELS_DIR).glob("*.yaml")) if (root / CHANNELS_DIR).is_dir() else []
        raise ConfigError(f"No existe el perfil de canal {path.relative_to(root)} (hay: {', '.join(known) or 'ninguno'}).")
    return load_config(path)


VIDEO_FILES = ("guion.txt", "voz.mp3", "titulo.txt")


def video_folders(root: Path, materials: str = "materiales") -> list[Path]:
    """Every video folder: materiales/<video>/ and, inside a channel folder, materiales/<canal>/<video>/.
    A folder with a script, voice or title is a video; one without them that holds folders (or is named
    after a channel) groups videos, with a config.yaml for all of them (e.g. `canal: aviacion`)."""

    base = root / materials
    out: list[Path] = []
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        subs = [sub for sub in sorted(folder.iterdir()) if sub.is_dir() and not sub.name.startswith(".")]
        grouping = (not any((folder / name).is_file() for name in VIDEO_FILES)
                    and (subs or (root / CHANNELS_DIR / f"{folder.name}.yaml").is_file()))
        out += subs if grouping else [folder]
    return out


def find_video(root: Path, slug: str, materials: str = "materiales") -> Path:
    """materiales/<slug>/, or materiales/<canal>/<slug>/ when the video sits in a channel folder."""

    flat = root / materials / slug
    if flat.is_dir():
        return flat
    return next((f for f in video_folders(root, materials) if f.name == slug), flat)


@dataclass
class RunContext:
    """Everything a stage needs to locate its inputs and outputs. No stage state lives here."""

    slug: str
    root: Path
    config: dict[str, Any]
    _env_loaded: bool = field(default=False, repr=False)

    @classmethod
    def create(cls, slug: str, *, root: Path = PROJECT_ROOT, config: dict[str, Any] | None = None,
               channel: str | None = None, series: str | None = None) -> "RunContext":
        """config.yaml ⊕ formatos/<format>.yaml → ajustes ⊕ canales/<canal>.yaml ⊕ its series.<serie> ⊕
        materiales/<canal>/config.yaml (a channel folder) ⊕ materiales/<slug>/config.yaml (later wins).

        The channel is `channel`, else `canal:` in the video's config.yaml, else `canal:` in config.yaml;
        the series (a recurring format of the channel: estafas, auge y caída…) is `series`, else `serie:`.
        The format (chosen anywhere in those layers) can bring settings of its own (`ajustes:`, e.g. the
        news format's recent-footage search), which the channel, the series and the video can still change."""

        if config is not None:
            return cls(slug=slug, root=root, config=config)
        base = load_config(root / "config.yaml")
        ctx = cls(slug=slug, root=root, config=base)
        # Per-video overrides: materiales/<slug>/config.yaml (e.g. timeline: {cold_open_seconds: 10}).
        path = ctx.materials_dir / "config.yaml"
        override = load_config(path) if path.is_file() else {}
        group = ctx.materials_dir.parent / "config.yaml"           # materiales/<canal>/config.yaml, for all its videos
        if ctx.materials_dir.parent != ctx._dir("materials", "materiales") and group.is_file():
            override = deep_merge(load_config(group), override)
        name = channel or override.get("canal") or base.get("canal")
        profile = channel_profile(root, str(name)) if name else {}
        catalog = profile.pop("series", None) or base.get("series") or {}
        serie = series or override.get("serie")
        chosen: dict[str, Any] = {}
        if serie:
            if str(serie) not in catalog:
                raise ConfigError(f"El canal {name or '(ninguno)'} no tiene la serie «{serie}» "
                                  f"(hay: {', '.join(catalog) or 'ninguna'}).")
            chosen = catalog[str(serie)]
        video = {k: v for k, v in override.items() if k not in ("canal", "serie")}

        def layered(extra: dict[str, Any]) -> dict[str, Any]:
            merged = deep_merge(deep_merge(deep_merge(deep_merge(base, extra), profile), chosen), video)
            merged.pop("series", None)
            if name:
                merged["canal"] = str(name)
            if serie:
                merged["serie"] = str(serie)
            return merged

        ctx.config = layered({})
        adjustments = ctx.format.get("ajustes")      # an unknown format fails here, not halfway through the night
        if isinstance(adjustments, dict) and adjustments:
            ctx.config = layered(adjustments)
        return ctx

    @property
    def channel(self) -> str:
        return str(self.config.get("canal") or "")

    @property
    def series(self) -> str:
        return str(self.config.get("serie") or "")

    @property
    def format(self) -> dict[str, Any]:
        """formatos/<format>.yaml of this video ({} without a format)."""

        from .formats import spec

        return spec(self.root, str(self.config.get("format") or ""))

    def _dir(self, key: str, default: str) -> Path:
        return self.root / str(self.config.get("paths", {}).get(key, default))

    @property
    def materials_dir(self) -> Path:
        base = self._dir("materials", "materiales")
        return find_video(self.root, self.slug, str(base.relative_to(self.root)))

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

    @property
    def language(self) -> str:
        """Name of the narration language for LLM prompts (align.language: es, en, pt…)."""

        code = str(self.section("align").get("language", "es"))
        return {"es": "español", "en": "English", "pt": "português", "fr": "français", "it": "italiano",
                "de": "Deutsch"}.get(code, code)

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
