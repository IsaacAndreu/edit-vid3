"""Single source of truth for scene templates, shared with the Remotion side.

``templates/manifest.json`` is read here by the Python pipeline and imported by
``templates/registry.ts`` / ``Root.tsx``. Adding a template means: create the
component, register it in ``registry.ts`` and describe it in the manifest.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "templates" / "manifest.json"

MEDIA_NONE = "none"
MEDIA_SINGLE = "single"
MEDIA_SHOTS = "shots"
_VALID_MEDIA = {MEDIA_NONE, MEDIA_SINGLE, MEDIA_SHOTS}

# A figure a "requiresNumber" template can display: 12, 5,26 %, 10-15 €, +3.5…
NUMERIC_VALUE_PATTERN = re.compile(
    r"[+-]?\d[\d.,]*(?:\s*[-–—]\s*[+-]?\d[\d.,]*)?(?:\s*[%€$£])?"
)


class TemplateManifestError(ValueError):
    """Raised when templates/manifest.json is missing or malformed."""


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    scene_types: tuple[str, ...]
    media: str
    background: bool
    third_party: bool
    prefer_video: bool
    llm: bool
    requires_number: bool = False
    requires_field: str | None = None
    max_duration_in_frames: int | None = None


@dataclass(frozen=True)
class TemplateManifest:
    fps: int
    width: int
    height: int
    templates: dict[str, TemplateSpec]
    default_by_scene_type: dict[str, str]

    def get(self, name: str | None) -> TemplateSpec | None:
        return self.templates.get(str(name or ""))

    @property
    def llm_template_names(self) -> list[str]:
        """Templates the segmenter may choose, in manifest order."""

        return [spec.name for spec in self.templates.values() if spec.llm]

    @property
    def valid_template_names(self) -> set[str]:
        return set(self.llm_template_names)

    @property
    def templates_by_scene_type(self) -> dict[str, set[str]]:
        by_type: dict[str, set[str]] = {}
        for spec in self.templates.values():
            if not spec.llm:
                continue
            for scene_type in spec.scene_types:
                by_type.setdefault(scene_type, set()).add(spec.name)
        return by_type


def parse_manifest(payload: Any) -> TemplateManifest:
    if not isinstance(payload, dict) or not isinstance(payload.get("templates"), dict):
        raise TemplateManifestError("templates/manifest.json no contiene un objeto 'templates'.")

    templates: dict[str, TemplateSpec] = {}
    for name, raw in payload["templates"].items():
        if not isinstance(raw, dict):
            raise TemplateManifestError(f"La plantilla {name!r} del manifiesto no es un objeto.")
        media = str(raw.get("media", MEDIA_NONE))
        if media not in _VALID_MEDIA:
            raise TemplateManifestError(
                f"La plantilla {name!r} declara media={media!r}; valores válidos: {sorted(_VALID_MEDIA)}."
            )
        max_frames = raw.get("maxDurationInFrames")
        templates[name] = TemplateSpec(
            name=name,
            scene_types=tuple(str(item) for item in raw.get("sceneTypes", [])),
            media=media,
            background=bool(raw.get("background", False)),
            third_party=bool(raw.get("thirdParty", False)),
            prefer_video=bool(raw.get("preferVideo", False)),
            llm=bool(raw.get("llm", True)),
            requires_number=bool(raw.get("requiresNumber", False)),
            requires_field=str(raw["requiresField"]) if raw.get("requiresField") else None,
            max_duration_in_frames=int(max_frames) if max_frames is not None else None,
        )

    defaults = payload.get("defaultTemplateBySceneType") or {}
    if not isinstance(defaults, dict):
        raise TemplateManifestError("defaultTemplateBySceneType debe ser un objeto.")
    for scene_type, template_name in defaults.items():
        if template_name not in templates:
            raise TemplateManifestError(
                f"La plantilla por defecto de {scene_type!r} ({template_name!r}) no existe en el manifiesto."
            )

    try:
        fps = int(payload.get("fps", 30))
        width = int(payload.get("width", 1920))
        height = int(payload.get("height", 1080))
    except (TypeError, ValueError) as error:
        raise TemplateManifestError("fps, width y height del manifiesto deben ser enteros.") from error
    if fps <= 0 or width <= 0 or height <= 0:
        raise TemplateManifestError("fps, width y height del manifiesto deben ser positivos.")

    return TemplateManifest(
        fps=fps,
        width=width,
        height=height,
        templates=templates,
        default_by_scene_type={str(key): str(value) for key, value in defaults.items()},
    )


@lru_cache(maxsize=1)
def load_manifest() -> TemplateManifest:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except OSError as error:
        raise TemplateManifestError(f"No se pudo leer {MANIFEST_PATH}: {error}") from error
    except json.JSONDecodeError as error:
        raise TemplateManifestError(f"{MANIFEST_PATH} no es JSON válido: {error}") from error
    return parse_manifest(payload)


def template_spec(name: str | None) -> TemplateSpec | None:
    return load_manifest().get(name)
