from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import SceneDraft


DEFAULT_ACCENT_COLORS = {
    "hook": "#f97316",
    "narrative": "#38bdf8",
    "stat": "#f6c945",
    "transition": "#ffffff",
    "avatar": "#34d399",
}


def _scene_props(scene: SceneDraft) -> dict[str, Any]:
    scene_type = scene.get("sceneType", "narrative")
    props: dict[str, Any] = {
        "templateName": scene.get("templateName", "placeholder"),
        "durationInFrames": int(scene.get("durationInFrames", 1)),
        "accentColor": scene.get("accentColor") or DEFAULT_ACCENT_COLORS.get(scene_type, "#ffffff"),
        "sceneType": scene_type,
    }

    for key in (
        "text",
        "imageUrl",
        "videoUrl",
        "videoDurationInSeconds",
        "mediaSourceUrl",
        "mediaQuery",
        "mediaRelevanceScore",
        "mediaPhotographer",
        "visualIntent",
        "mustContain",
        "avoid",
        "preferredShot",
        "mediaProvider",
        "mediaSourceTitle",
        "mediaUploader",
        "mediaStartSeconds",
        "mediaEndSeconds",
        "mediaClipDurationSeconds",
        "mediaSelectionScore",
        "mediaVisualScore",
        "mediaSelectionReason",
        "mediaTranscriptExcerpt",
        "keywords",
        "shots",
        "timelinePoints",
        "comparisonColumns",
    ):
        value = scene.get(key)
        if value is not None and value != []:
            props[key] = value
    return props


def build_props(
    scenes: list[SceneDraft],
    output_path: Path | None = None,
    *,
    audio_url: str | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {"scenes": [_scene_props(scene) for scene in scenes]}
    if audio_url:
        props["audioUrl"] = audio_url
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(props, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return props
