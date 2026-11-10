from __future__ import annotations

from pathlib import Path
from typing import Any

from .cache import atomic_write_json
from .config import REMOTION_FPS
from .types import SceneDraft


def write_timeline_manifest(
    scenes: list[SceneDraft],
    output_path: Path,
    *,
    fps: int = REMOTION_FPS,
) -> None:
    """Write scene markers that can be compared with YouTube retention later."""

    cursor_frames = 0
    markers: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        duration_in_frames = int(scene.get("durationInFrames", 0))
        start_seconds = cursor_frames / fps
        end_seconds = (cursor_frames + duration_in_frames) / fps
        marker = {
            "sceneIndex": index,
            "startSeconds": round(start_seconds, 3),
            "endSeconds": round(end_seconds, 3),
            "durationSeconds": round(duration_in_frames / fps, 3),
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
            "mediaVideoId",
            "mediaContactSheet",
            "mediaRemoteUrl",
            "mediaThumbnailUrl",
            "mediaSelectionTrace",
            "imageUrl",
            "videoUrl",
            "visualIntent",
            "mustContain",
            "avoid",
            "preferredShot",
        ):
            if scene.get(key) is not None:
                marker[key] = scene[key]
        markers.append(marker)
        cursor_frames += duration_in_frames

    atomic_write_json(
        output_path,
        {"fps": fps, "totalDurationSeconds": round(cursor_frames / fps, 3), "scenes": markers},
    )
