"""Per-scene manual corrections applied after segmentation.

Example ``overrides.json`` (scene numbers are 1-based, as shown in the report)::

    {
      "scenes": {
        "23": {"media": "planos/ruleta.mp4"},
        "31": {"keywords": ["casino security camera"], "visualIntent": "CCTV room with monitors"},
        "40": {"text": "5,26 % de ventaja", "templateName": "stat-overlay"}
      }
    }

``media`` is a local image or video (relative paths resolve against the
overrides file); the scene then skips YouTube, Pexels and GPT Image.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import SceneDraft


class OverridesError(ValueError):
    """The overrides file is malformed or points at a scene that does not exist."""


_TEXT_KEYS = {"text", "visualIntent", "preferredShot", "templateName", "accentColor"}
_LIST_KEYS = {"keywords", "mustContain", "avoid"}
ALLOWED_KEYS = _TEXT_KEYS | _LIST_KEYS | {"media"}


def load_overrides(path: Path) -> dict[int, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise OverridesError(f"No se pudo leer {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise OverridesError(f"{path} no es JSON válido: {error}") from error

    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(scenes, dict):
        raise OverridesError(f'{path} debe tener la forma {{"scenes": {{"<nº de escena>": {{...}}}}}}.')

    overrides: dict[int, dict[str, Any]] = {}
    for raw_number, raw in scenes.items():
        try:
            number = int(raw_number)
        except (TypeError, ValueError) as error:
            raise OverridesError(f"{path}: {raw_number!r} no es un número de escena.") from error
        if not isinstance(raw, dict):
            raise OverridesError(f"{path}: la escena {number} debe ser un objeto.")
        unknown = sorted(set(raw) - ALLOWED_KEYS)
        if unknown:
            raise OverridesError(
                f"{path}: la escena {number} usa claves no admitidas {unknown}. "
                f"Admitidas: {sorted(ALLOWED_KEYS)}."
            )
        entry: dict[str, Any] = {}
        for key, value in raw.items():
            if key in _LIST_KEYS:
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise OverridesError(f"{path}: escena {number}, {key} debe ser una lista de textos.")
                entry[key] = [item.strip() for item in value if item.strip()]
            elif key == "media":
                media_path = Path(str(value)).expanduser()
                if not media_path.is_absolute():
                    media_path = (path.parent / media_path).resolve()
                if not media_path.is_file():
                    raise OverridesError(f"{path}: escena {number}, no existe el fichero {media_path}.")
                entry[key] = str(media_path)
            else:
                if not isinstance(value, str) or not value.strip():
                    raise OverridesError(f"{path}: escena {number}, {key} debe ser un texto no vacío.")
                entry[key] = value.strip()
        overrides[number] = entry
    return overrides


def apply_overrides(scenes: list[SceneDraft], overrides: dict[int, dict[str, Any]]) -> list[int]:
    """Mutate ``scenes`` in place; return the scene numbers that were changed."""

    out_of_range = sorted(number for number in overrides if not 1 <= number <= len(scenes))
    if out_of_range:
        raise OverridesError(
            f"Los overrides citan las escenas {out_of_range}, pero el plan tiene {len(scenes)} (1-{len(scenes)})."
        )
    for number, entry in overrides.items():
        scene = scenes[number - 1]
        for key, value in entry.items():
            if key == "media":
                scene["mediaOverride"] = value
            else:
                scene[key] = value  # type: ignore[literal-required]
    return sorted(overrides)
