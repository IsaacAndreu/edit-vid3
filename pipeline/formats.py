"""Video formats as files: formatos/<name>.yaml (historia, ranking, lista, explicativo…).

A format says how the video is told, whatever the channel: how the script is cut into events
(`guion`, added to the planner's prompt), which graphics suit it (`graficos`, and how often:
`segundos_por_grafico`), and how its titles read (`titulos`). A new format is a new file; only
formats with their own graphics pass (ranking, prohibidos) also have code in graphics.py.
Pick one with `format: <name>` in config.yaml, a channel profile, a series or the video's config.yaml.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import PROJECT_ROOT, ConfigError

FORMATS_DIR = "formatos"


def folder(root: Path) -> Path:
    """The project's formatos/ (a test root without one uses the repository's)."""

    own = root / FORMATS_DIR
    return own if own.is_dir() else PROJECT_ROOT / FORMATS_DIR


@lru_cache(maxsize=64)
def _read(path: Path, stamp: float) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} debe contener un mapa YAML.")
    return data


def available(root: Path) -> dict[str, dict[str, Any]]:
    return {p.stem: _read(p, p.stat().st_mtime) for p in sorted(folder(root).glob("*.yaml"))}


def spec(root: Path, name: str) -> dict[str, Any]:
    """formatos/<name>.yaml ({} without a format)."""

    if not name:
        return {}
    path = folder(root) / f"{name}.yaml"
    if not path.is_file():
        raise ConfigError(f"No existe el formato {FORMATS_DIR}/{name}.yaml (hay: {', '.join(available(root)) or 'ninguno'}).")
    return _read(path, path.stat().st_mtime)


def listing(root: Path) -> str:
    lines = []
    for name, data in available(root).items():
        lines += [f"{name:14} {data.get('nombre', name)}: {data.get('descripcion', '')}",
                  f"{'':14} p. ej. {data.get('ejemplos', '—')}"]
    return "\n".join(lines)
