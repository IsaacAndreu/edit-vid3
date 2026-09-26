from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import SceneDraft


def write_timeline_manifest(scenes: list[SceneDraft], output_path: Path) -> None:
    """Write scene markers that can be compared with YouTube retention later."""

    cursor_frames = 0
    markers: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        duration_in_frames = int(scene.get("durationInFrames", 0))
        start_seconds = cursor_frames / 30
        end_seconds = (cursor_frames + duration_in_frames) / 30
        marker = {
            "sceneIndex": index,
            "startSeconds": round(start_seconds, 3),
            "endSeconds": round(end_seconds, 3),
            "durationSeconds": round(duration_in_frames / 30, 3),
            "templateName": scene.get("templateName"),
            "sceneType": scene.get("sceneType"),
            "text": scene.get("text", ""),
            "keywords": scene.get("keywords", []),
        }
        if scene.get("shots"):
            marker["shots"] = scene["shots"]
        for key in (
            "mediaQuery",
            "mediaSourceUrl",
            "mediaRelevanceScore",
            "mediaPhotographer",
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
            "visualIntent",
            "mustContain",
            "avoid",
            "preferredShot",
        ):
            if scene.get(key) is not None:
                marker[key] = scene[key]
        markers.append(marker)
        cursor_frames += duration_in_frames

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"fps": 30, "totalDurationSeconds": round(cursor_frames / 30, 3), "scenes": markers}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
