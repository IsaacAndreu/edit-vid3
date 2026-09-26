from __future__ import annotations

import math
import re
from typing import Any

from .clients.deepseek_client import segment_with_deepseek
from .config import REMOTION_FPS, Settings
from .types import SceneDraft, SceneType, Transcript


VALID_SCENE_TYPES: set[str] = {"hook", "narrative", "stat", "transition"}
VALID_TEMPLATES_BY_TYPE: dict[str, set[str]] = {
    "hook": {"kinetic-text-hook", "title-card"},
    "narrative": {
        "kenburns-image",
        "lower-third",
        "multi-shot-montage",
        "news-image-montage",
        "timeline-graphic",
        "comparison-panel",
    },
    "stat": {
        "number-callout",
        "stat-overlay",
        "blueprint-data-panel",
        "timeline-graphic",
        "comparison-panel",
    },
    "transition": {"title-card", "whip-transition"},
}

VALID_TEMPLATE_NAMES: set[str] = {
    "kinetic-text-hook",
    "kenburns-image",
    "number-callout",
    "stat-overlay",
    "blueprint-data-panel",
    "title-card",
    "whip-transition",
    "lower-third",
    "multi-shot-montage",
    "news-image-montage",
    "timeline-graphic",
    "comparison-panel",
}
DEFAULT_TEMPLATE_BY_TYPE: dict[SceneType, str] = {
    "hook": "kinetic-text-hook",
    "narrative": "kenburns-image",
    "stat": "number-callout",
    "transition": "title-card",
    # AvatarScene is not present in the checked-out registry yet.
    "avatar": "placeholder",
}

MAX_VISUAL_TEXT_WORDS = 10
MAX_WHIP_DURATION_IN_FRAMES = 10
LOWER_THIRD_STOPWORDS = {
    "a", "al", "cada", "como", "con", "de", "del", "el", "en", "es",
    "la", "las", "los", "más", "para", "por", "que", "se", "una", "un", "y",
    "pero", "tienes", "luego", "solo", "si", "también", "porque", "puede", "eso", "lo",
}
STAT_VALUE_PATTERN = re.compile(
    r"[+-]?\d[\d.,]*(?:\s*[-–—]\s*[+-]?\d[\d.,]*)?(?:\s*[%€$£])?"
)


def _scene_type(value: Any) -> SceneType:
    candidate = str(value or "narrative").strip().lower()
    if candidate == "avatar":
        return "narrative"
    return candidate if candidate in VALID_SCENE_TYPES else "narrative"  # type: ignore[return-value]


def _template_name(
    value: Any,
    scene_type: SceneType,
    raw_scene_type: str,
    duration_in_frames: int,
    text: str,
    has_timeline_points: bool = False,
    has_comparison_columns: bool = False,
) -> str:
    candidate = str(value or "").strip()
    if raw_scene_type == "avatar":
        return DEFAULT_TEMPLATE_BY_TYPE[scene_type]
    if scene_type == "transition" and duration_in_frames <= MAX_WHIP_DURATION_IN_FRAMES:
        return "whip-transition"
    if candidate == "whip-transition" and duration_in_frames > MAX_WHIP_DURATION_IN_FRAMES:
        return "title-card"
    if scene_type == "narrative" and candidate == "lower-third" and not _has_named_entity(text):
        return "kenburns-image"
    if scene_type == "stat":
        if candidate == "blueprint-data-panel":
            return candidate
        if candidate == "timeline-graphic" and has_timeline_points:
            return candidate
        if candidate == "comparison-panel" and has_comparison_columns:
            return candidate
        numeric_values = STAT_VALUE_PATTERN.findall(text)
        if not numeric_values:
            return "blueprint-data-panel"
        if len(numeric_values) == 1 and duration_in_frames >= 30:
            return "stat-overlay"
        return "number-callout"
    if candidate == "timeline-graphic" and not has_timeline_points:
        return DEFAULT_TEMPLATE_BY_TYPE[scene_type]
    if candidate == "comparison-panel" and not has_comparison_columns:
        return DEFAULT_TEMPLATE_BY_TYPE[scene_type]
    if candidate not in VALID_TEMPLATE_NAMES:
        return DEFAULT_TEMPLATE_BY_TYPE[scene_type]
    if candidate not in VALID_TEMPLATES_BY_TYPE.get(scene_type, set()):
        return DEFAULT_TEMPLATE_BY_TYPE[scene_type]
    return candidate


def _keywords(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(keyword).strip() for keyword in value if str(keyword).strip()][:3]


def _short_list(value: Any, *, limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def _visual_intent(value: Any, keywords: list[str], fallback_text: str) -> str:
    candidate = str(value or "").strip()
    if candidate:
        return " ".join(candidate.split())[:240]
    if keywords:
        return ", ".join(keywords)[:240]
    return " ".join(fallback_text.split())[:180]


def _visual_text(value: Any, fallback: str) -> str:
    candidate = str(value or fallback).strip()
    words = candidate.split()
    if len(words) <= MAX_VISUAL_TEXT_WORDS:
        return candidate
    return " ".join(words[:MAX_VISUAL_TEXT_WORDS]).rstrip(".,;:!?—-") + "…"


def _has_named_entity(text: str) -> bool:
    """Allow lower-thirds mainly for people, companies, places, and institutions."""

    words = re.findall(r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9-]*", text)
    meaningful = [word for word in words if word.lower() not in LOWER_THIRD_STOPWORDS and len(word) > 2]
    return bool(meaningful)


def _normalize_template_mix(scenes: list[SceneDraft]) -> None:
    consecutive_lower_thirds = 0
    for scene in scenes:
        if scene.get("templateName") != "lower-third":
            consecutive_lower_thirds = 0
            continue
        text = str(scene.get("text") or "")
        if consecutive_lower_thirds >= 2 and not _has_named_entity(text):
            scene["templateName"] = "kenburns-image"
            consecutive_lower_thirds = 0
            continue
        consecutive_lower_thirds += 1


def _timeline_points(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    points: list[dict[str, Any]] = []
    for point in value[:6]:
        if not isinstance(point, dict) or not str(point.get("label") or "").strip():
            continue
        try:
            position = float(point.get("position", 0))
        except (TypeError, ValueError):
            continue
        normalized: dict[str, Any] = {
            "label": str(point["label"]).strip(),
            "position": min(1.0, max(0.0, position)),
        }
        if point.get("value") is not None and str(point["value"]).strip():
            normalized["value"] = str(point["value"]).strip()
        points.append(normalized)
    return points


def _comparison_columns(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    columns: list[dict[str, Any]] = []
    for column in value[:4]:
        if not isinstance(column, dict) or not str(column.get("title") or "").strip():
            continue
        items = column.get("items")
        if not isinstance(items, list):
            continue
        clean_items = [str(item).strip() for item in items[:6] if str(item).strip()]
        if clean_items:
            columns.append({"title": str(column["title"]).strip(), "items": clean_items})
    return columns if len(columns) >= 2 else []


def _word_index(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_timeline(scenes: list[SceneDraft], audio_duration_seconds: float, fps: int) -> None:
    """Make sparse/overlapping LLM boundaries play as a continuous timeline."""

    if not scenes:
        return

    scenes.sort(key=lambda scene: (scene.get("start_word_index", 0), scene.get("end_word_index", 0)))
    cursor_frame = 0
    for index, scene in enumerate(scenes):
        raw_end = float(scene.get("end_time_seconds", 0.0))
        if index + 1 < len(scenes):
            next_raw_start = float(scenes[index + 1].get("start_time_seconds", raw_end))
            target_end = max(raw_end, next_raw_start)
        else:
            target_end = max(raw_end, audio_duration_seconds)

        target_frame = max(cursor_frame + 1, math.ceil(target_end * fps))
        scene["start_time_seconds"] = cursor_frame / fps
        scene["end_time_seconds"] = target_frame / fps
        scene["durationInFrames"] = target_frame - cursor_frame
        cursor_frame = target_frame


def segment_script(
    script_text: str,
    transcript: Transcript,
    settings: Settings,
    *,
    fps: int = REMOTION_FPS,
) -> list[SceneDraft]:
    words = transcript["words"]
    raw_scenes = segment_with_deepseek(script_text, words, settings)
    if not raw_scenes:
        raise RuntimeError("DeepSeek no devolvió escenas.")

    scenes: list[SceneDraft] = []
    last_word_index = len(words) - 1
    for raw_scene in raw_scenes:
        start_index = max(0, min(last_word_index, _word_index(raw_scene.get("start_word_index"), 0)))
        end_index = max(start_index, min(last_word_index, _word_index(raw_scene.get("end_word_index"), start_index)))
        start_seconds = words[start_index]["start"]
        end_seconds = max(start_seconds, words[end_index]["end"])
        raw_scene_type = str(raw_scene.get("sceneType") or "").strip().lower()
        scene_type = _scene_type(raw_scene_type)
        fallback_text = " ".join(word["word"] for word in words[start_index : end_index + 1])
        text = _visual_text(raw_scene.get("text"), fallback_text)
        timeline_points = _timeline_points(raw_scene.get("timelinePoints"))
        comparison_columns = _comparison_columns(raw_scene.get("comparisonColumns"))
        if start_index == 0 or (scene_type == "narrative" and "?" in text):
            scene_type = "hook"
        duration_in_frames = max(1, math.ceil((end_seconds - start_seconds) * fps))
        template_name = _template_name(
            raw_scene.get("templateName"),
            scene_type,
            raw_scene_type,
            duration_in_frames,
            text,
            bool(timeline_points),
            bool(comparison_columns),
        )
        if start_index == 0:
            template_name = "kinetic-text-hook"

        keywords = _keywords(raw_scene.get("keywords"))
        scene: SceneDraft = {
            "text": text,
            "keywords": keywords,
            "visualIntent": _visual_intent(raw_scene.get("visualIntent"), keywords, text),
            "mustContain": _short_list(raw_scene.get("mustContain")),
            "avoid": _short_list(raw_scene.get("avoid")),
            "preferredShot": str(raw_scene.get("preferredShot") or "action").strip()[:40],
            "sceneType": scene_type,
            "templateName": template_name,
            "start_word_index": start_index,
            "end_word_index": end_index,
            "start_time_seconds": start_seconds,
            "end_time_seconds": end_seconds,
            "durationInFrames": duration_in_frames,
        }
        if timeline_points:
            scene["timelinePoints"] = timeline_points
        if comparison_columns:
            scene["comparisonColumns"] = comparison_columns
        scenes.append(scene)

    _normalize_timeline(scenes, transcript.get("duration_seconds", 0.0), fps)
    _normalize_template_mix(scenes)

    return scenes
