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


# --- the format chosen from the script ------------------------------------------------------------------------------

AUTO = "formato.auto.json"       # in the video's folder: what was chosen and why (decided once)

DETECT_SYSTEM = """
Eres editor de un canal de documentales de YouTube. Con el guion de un vídeo, elige el FORMATO que mejor encaja de la
lista (la forma de contarlo: ranking, caso real, misterio, historia…). Si el guion no encaja claramente en ninguno más
que en el habitual del canal, elige el habitual. Devuelve SOLO JSON: {"format": "nombre exacto de la lista",
"why": "por qué, en 1 frase"}.
""".strip()


def detect(ctx: Any, script: str) -> dict[str, str]:
    """{"format", "why"}: the format of formatos/ that suits this script (the channel's own when nothing fits better)."""

    from .llm import complete_json

    options = available(ctx.root)
    usual = str(ctx.config.get("format") or "")
    listing_text = "\n".join(f"- {name}: {data.get('nombre', name)}. {data.get('descripcion', '')} (p. ej. {data.get('ejemplos', '—')})"
                             for name, data in options.items())
    result = complete_json(ctx, stage="formato", section="planner", system=DETECT_SYSTEM, max_tokens=300,
                           user=f"FORMATOS:\n{listing_text}\n\nHABITUAL DEL CANAL: {usual or '(ninguno)'}\n\nGUION:\n{script[:9000]}")
    name = str(result.get("format") or "").strip()
    if name not in options:
        name = usual if usual in options else ""
    return {"format": name, "why": str(result.get("why") or "").strip()[:300]}


def ensure_auto(ctx: Any) -> bool:
    """A new video whose own config.yaml names no format gets the one that suits its script, written into that
    config.yaml (decided once; the original choice stays in formato.auto.json). `format_auto: false` turns it off.
    True when the video's config changed (the caller rebuilds its context)."""

    import json

    from .capitulos import started

    folder = ctx.materials_dir
    own_path = folder / "config.yaml"
    try:
        own = (yaml.safe_load(own_path.read_text("utf-8")) or {}) if own_path.is_file() else {}
    except (OSError, yaml.YAMLError):
        return False
    script = folder / "guion.txt"
    if (own.get("format") or (folder / AUTO).is_file() or not script.is_file() or started(ctx)
            or not ctx.config.get("format_auto", True)):
        return False
    try:
        choice = detect(ctx, script.read_text("utf-8"))
    except Exception as error:                   # no choice: the channel's format, as before
        print(f"   Formato automático no disponible ({type(error).__name__}: {str(error)[:120]})")
        return False
    usual = str(ctx.config.get("format") or "")
    (folder / AUTO).write_text(json.dumps({**choice, "channel": usual}, ensure_ascii=False), encoding="utf-8")
    if not choice["format"] or choice["format"] == usual:
        print(f"   Formato: el del canal ({usual or 'ninguno'}) · {choice['why']}")
        return False
    text = own_path.read_text("utf-8") if own_path.is_file() else ""
    own_path.write_text(text + ("" if not text or text.endswith("\n") else "\n") + f"format: {choice['format']}\n",
                        encoding="utf-8")
    print(f"   Formato elegido según el guion: {choice['format']} · {choice['why']}")
    return True
