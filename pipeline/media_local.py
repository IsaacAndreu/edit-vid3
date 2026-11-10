"""Scenes whose media is a local file: operator overrides and (reserved) avatar clips."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .media_context import MediaContext, MediaFetchError, Plan
from .media_tools import MediaToolError, probe_duration_seconds
from .templates import MEDIA_SHOTS
from .third_party_media import public_asset_url
from .types import SceneDraft


VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def resolve_override(context: MediaContext, plan: Plan) -> None:
    """Use the file the operator fixed for this scene in overrides.json."""

    scene = plan.scene
    source = Path(str(scene["mediaOverride"])).expanduser()
    if not source.is_file():
        raise MediaFetchError(f"Escena {plan.number}: no existe el fichero de override {source}.")
    suffix = source.suffix.lower()
    if suffix not in VIDEO_SUFFIXES | IMAGE_SUFFIXES:
        raise MediaFetchError(
            f"Escena {plan.number}: {source.name} no es un vídeo o imagen admitido "
            f"({', '.join(sorted(VIDEO_SUFFIXES | IMAGE_SUFFIXES))})."
        )
    target_dir = context.assets_dir / "overrides"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"scene-{plan.number:03d}{suffix}"
    shutil.copy2(source, target)
    url = public_asset_url(target, context.project_root)
    is_video = suffix in VIDEO_SUFFIXES
    duration: float | None = None
    if is_video:
        try:
            duration = probe_duration_seconds(target)
        except MediaToolError:
            duration = None

    for key in ("imageUrl", "videoUrl", "videoDurationInSeconds", "shots"):
        scene.pop(key, None)  # type: ignore[misc]
    if plan.spec is not None and plan.spec.media == MEDIA_SHOTS:
        shot: dict[str, Any] = {"url": url, "type": "video" if is_video else "image", "provider": "local"}
        if duration:
            shot["durationInSeconds"] = duration
        scene["shots"] = [shot]
    elif is_video:
        scene["videoUrl"] = url
        if duration:
            scene["videoDurationInSeconds"] = duration
    else:
        scene["imageUrl"] = url
    scene["mediaProvider"] = "local"
    scene["mediaSourceUrl"] = str(source)
    context.providers[plan.index] = "local"


def _avatar_source(scene: SceneDraft, avatar_dir: Path | None, scene_index: int) -> Path | str | None:
    configured = scene.get("videoUrl") or scene.get("avatar_path")
    if configured:
        path = Path(str(configured)).expanduser()
        return path if path.exists() else str(configured)

    if avatar_dir:
        candidates = sorted(
            path
            for path in avatar_dir.expanduser().glob(f"scene-{scene_index + 1:03d}.*")
            if path.suffix.lower() in {".mp4", ".mov", ".webm"}
        )
        if candidates:
            return candidates[0]
    return None


def resolve_avatar(context: MediaContext, plan: Plan) -> None:
    """Legacy avatar clips. The segmenter never emits avatar scenes today."""

    scene = plan.scene
    source = _avatar_source(scene, context.avatar_dir, plan.index)
    if source is None:
        raise MediaFetchError(
            f"La escena {plan.number} es avatar pero no tiene videoUrl ni clip "
            "scene-NNN.* en --avatar-dir."
        )
    if isinstance(source, Path):
        if not source.is_file():
            raise MediaFetchError(f"No existe el clip de avatar: {source}")
        target_dir = context.assets_dir / "avatars"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"avatar-{plan.number:03d}{source.suffix.lower()}"
        shutil.copy2(source, target)
        scene["videoUrl"] = public_asset_url(target, context.project_root)
    else:
        scene["videoUrl"] = source
    context.providers[plan.index] = "avatar"
