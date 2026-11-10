from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .build_props import DEFAULT_ACCENT_COLORS
from .cache import atomic_write_json
from .config import REMOTION_FPS
from .templates import MEDIA_SHOTS, NUMERIC_VALUE_PATTERN, load_manifest
from .types import SceneDraft


_MANIFEST = load_manifest()
VALID_TEMPLATE_NAMES = _MANIFEST.valid_template_names
_NUMERIC_PATTERN = NUMERIC_VALUE_PATTERN
MAX_THIRD_PARTY_CLIP_SECONDS = 5.0


class PipelineQualityError(RuntimeError):
    """Raised when the props are unsafe to render."""


@dataclass(frozen=True)
class QAIssue:
    level: Literal["error", "warning"]
    code: str
    message: str
    scene_index: int | None = None


def _issue(
    level: Literal["error", "warning"],
    code: str,
    message: str,
    scene_index: int | None = None,
) -> QAIssue:
    return QAIssue(level=level, code=code, message=message, scene_index=scene_index)


def validate_scene_plan(
    scenes: list[SceneDraft],
    audio_duration_seconds: float,
    *,
    fps: int = REMOTION_FPS,
) -> list[QAIssue]:
    """Validate render-critical invariants before Remotion is started."""

    issues: list[QAIssue] = []
    if not scenes:
        return [_issue("error", "empty-scenes", "No hay escenas para renderizar.")]

    total_frames = sum(int(scene.get("durationInFrames", 0)) for scene in scenes)
    expected_frames = math.ceil(max(0.0, audio_duration_seconds) * fps)
    if abs(total_frames - expected_frames) > 1:
        issues.append(
            _issue(
                "error",
                "duration-mismatch",
                f"Las escenas suman {total_frames} frames y el audio requiere {expected_frames}.",
            )
        )

    for index, scene in enumerate(scenes, start=1):
        template_name = str(scene.get("templateName") or "")
        spec = _MANIFEST.get(template_name)
        duration_in_frames = int(scene.get("durationInFrames", 0))
        text = str(scene.get("text") or "").strip()

        if template_name not in VALID_TEMPLATE_NAMES:
            issues.append(
                _issue("error", "unknown-template", f"Plantilla desconocida: {template_name!r}.", index)
            )
        if duration_in_frames <= 0:
            issues.append(_issue("error", "invalid-duration", "La escena no tiene duración positiva.", index))
        effective_accent_color = scene.get("accentColor") or DEFAULT_ACCENT_COLORS.get(
            str(scene.get("sceneType") or "narrative"),
            "#ffffff",
        )
        if not str(effective_accent_color).strip():
            issues.append(_issue("error", "missing-accent", "La escena no tiene accentColor.", index))

        max_frames = spec.max_duration_in_frames if spec else None
        if max_frames is not None and duration_in_frames > max_frames:
            issues.append(
                _issue(
                    "error",
                    "long-whip",
                    f"{template_name} de {duration_in_frames} frames; el máximo permitido es {max_frames}.",
                    index,
                )
            )

        if spec and spec.requires_number and not _NUMERIC_PATTERN.search(text):
            issues.append(
                _issue(
                    "error",
                    "numeric-template-without-number",
                    f"{template_name} no puede recibir una frase sin cifra: {text!r}.",
                    index,
                )
            )

        if spec and spec.requires_field and not scene.get(spec.requires_field):
            issues.append(
                _issue(
                    "error",
                    "missing-structured-data",
                    f"{template_name} necesita el campo {spec.requires_field}.",
                    index,
                )
            )

        if len(text.split()) > 10:
            issues.append(
                _issue(
                    "warning",
                    "long-visual-text",
                    "El texto visual supera 10 palabras y puede resultar ilegible.",
                    index,
                )
            )

        # Root.tsx plays a video background when kenburns-image has videoUrl and
        # no imageUrl (YouTube clip or Pexels video), so either one is enough.
        if template_name == "kenburns-image" and not (scene.get("imageUrl") or scene.get("videoUrl")):
            issues.append(
                _issue("error", "missing-image", "KenBurnsImage necesita imageUrl o videoUrl.", index)
            )

        if spec and spec.media == MEDIA_SHOTS:
            shots = scene.get("shots")
            if not isinstance(shots, list) or not shots:
                issues.append(_issue("error", "missing-shots", f"{template_name} necesita shots.", index))
            else:
                for shot_index, shot in enumerate(shots, start=1):
                    if not isinstance(shot, dict) or not shot.get("url") or shot.get("type") not in {"image", "video"}:
                        issues.append(
                            _issue(
                                "error",
                                "invalid-shot",
                                f"Shot {shot_index} no tiene url y type válidos.",
                                index,
                            )
                        )
                    if isinstance(shot, dict):
                        _validate_third_party_clip(issues, shot, index, f"shot {shot_index}")
                        _warn_if_video_is_short(issues, shot, duration_in_frames, index, f"shot {shot_index}", fps)

        if scene.get("videoUrl"):
            _validate_third_party_clip(issues, scene, index, "vídeo de escena")
            _warn_if_video_is_short(issues, scene, duration_in_frames, index, "video de escena", fps)

    return issues


def _validate_third_party_clip(
    issues: list[QAIssue],
    media: dict[str, Any],
    scene_index: int,
    media_label: str,
) -> None:
    if media.get("provider") != "youtube" and media.get("mediaProvider") != "youtube":
        return
    raw_duration = media.get("durationInSeconds", media.get("mediaClipDurationSeconds"))
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        issues.append(
            _issue(
                "error",
                "third-party-duration-missing",
                f"{media_label} de YouTube no incluye su duración comprobable.",
                scene_index,
            )
        )
        return
    if duration <= 0 or duration > MAX_THIRD_PARTY_CLIP_SECONDS + 1e-6:
        issues.append(
            _issue(
                "error",
                "third-party-clip-over-limit",
                f"{media_label} de YouTube dura {duration:.3f}s; máximo permitido: {MAX_THIRD_PARTY_CLIP_SECONDS:.1f}s.",
                scene_index,
            )
        )


def _warn_if_video_is_short(
    issues: list[QAIssue],
    media: dict[str, Any],
    scene_duration_in_frames: int,
    scene_index: int,
    media_label: str,
    fps: int = REMOTION_FPS,
) -> None:
    duration = media.get("videoDurationInSeconds")
    if duration is None:
        duration = media.get("durationInSeconds")
    try:
        duration_seconds = float(duration)
    except (TypeError, ValueError):
        return

    if duration_seconds * fps + 1 < scene_duration_in_frames:
        is_youtube = media.get("provider") == "youtube" or media.get("mediaProvider") == "youtube"
        ending = (
            "se quedará en el último fotograma tras reproducirse una vez"
            if is_youtube
            else "se reproducirá en loop"
        )
        issues.append(
            _issue(
                "warning",
                "short-third-party-video" if is_youtube else "short-video-looped",
                f"{media_label} dura {duration_seconds:.2f}s y la escena {scene_duration_in_frames / fps:.2f}s; {ending}.",
                scene_index,
            )
        )


def write_qa_report(path: Path, issues: list[QAIssue]) -> None:
    payload = {
        "status": "error" if any(issue.level == "error" for issue in issues) else "ok",
        "issues": [asdict(issue) for issue in issues],
    }
    atomic_write_json(path, payload)


def enforce_qa(issues: list[QAIssue]) -> None:
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        lines = []
        for issue in errors:
            where = f"escena {issue.scene_index}: " if issue.scene_index is not None else ""
            lines.append(f"  - {where}[QA:{issue.code}] {issue.message}")
        raise PipelineQualityError(
            f"QA pre-render bloqueada por {len(errors)} error(es):\n" + "\n".join(lines)
        )
