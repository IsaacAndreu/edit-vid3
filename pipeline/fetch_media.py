from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .clients.openai_images import OpenAIImageClient
from .clients.pexels_client import PexelsAsset, PexelsClient, PexelsRateLimitError
from .config import Settings
from .media_ranker import select_best_asset
from .third_party_media import SelectedThirdPartyClip, public_asset_url, select_third_party_clip
from .candidate_analyzer import DeepSeekVisualJudge
from .clients.youtube_client import YouTubeClient, YouTubeClientError
from .types import SceneDraft


class MediaFetchError(RuntimeError):
    """Raised when a scene cannot be provided with its required media."""


MONTAGE_TEMPLATES = {"multi-shot-montage", "news-image-montage"}
YOUTUBE_MEDIA_TEMPLATES = {
    "kinetic-text-hook",
    "kenburns-image",
    "lower-third",
    "multi-shot-montage",
    "news-image-montage",
    "number-callout",
    "stat-overlay",
}


def _public_url(path: Path, project_root: Path) -> str:
    relative_path = path.resolve().relative_to((project_root / "public").resolve())
    return f"/{relative_path.as_posix()}"


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


def _copy_local_avatar(
    source: Path,
    target_dir: Path,
    project_root: Path,
    scene_index: int,
) -> str:
    if not source.is_file():
        raise MediaFetchError(f"No existe el clip de avatar: {source}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"avatar-{scene_index + 1:03d}{source.suffix.lower()}"
    shutil.copy2(source, target)
    return _public_url(target, project_root)


def _visual_prompt(scene: SceneDraft, keywords: list[str]) -> str:
    text = scene.get("text", "").strip()
    keyword_text = ", ".join(keywords) or text
    return (
        "Cinematic 16:9 b-roll image for a YouTube documentary scene. "
        "Natural composition, realistic lighting, no text, no logos, no watermark. "
        f"Scene context: {text}. Visual keywords: {keyword_text}."
    )


def _assign_asset(
    scene: SceneDraft,
    asset: PexelsAsset,
    *,
    query: str | None = None,
    relevance_score: float | None = None,
) -> None:
    if asset.kind == "video":
        scene["videoUrl"] = asset.url
        if asset.duration_seconds is not None:
            scene["videoDurationInSeconds"] = asset.duration_seconds
    else:
        scene["imageUrl"] = asset.url
    scene["mediaSourceUrl"] = asset.source_url
    scene["mediaProvider"] = "pexels"
    if query:
        scene["mediaQuery"] = query
    if relevance_score is not None:
        scene["mediaRelevanceScore"] = round(relevance_score, 2)
    if asset.photographer:
        scene["mediaPhotographer"] = asset.photographer


def _assign_montage_shots(
    scene: SceneDraft,
    keywords: list[str],
    pexels: PexelsClient,
    used_asset_urls: set[str],
    *,
    prefer_video: bool,
    existing_shots: list[dict[str, Any]] | None = None,
) -> bool:
    shots: list[dict[str, Any]] = list(existing_shots or [])
    existing_urls = {str(shot.get("url")) for shot in shots if isinstance(shot, dict)}
    shot_duration_seconds = float(scene.get("durationInFrames", 1)) / 30 / max(1, min(4, len(keywords)))
    for keyword_index, keyword in enumerate(keywords[:4]):
        candidates = _asset_candidates(
            pexels,
            [keyword],
            used_asset_urls,
            prefer_video=prefer_video,
        )
        selected = select_best_asset(
            candidates,
            required_duration_seconds=shot_duration_seconds,
        )
        asset = selected[0] if selected else None
        if asset is None:
            continue
        if asset.url in existing_urls:
            continue
        shot: dict[str, Any] = {"url": asset.url, "type": asset.kind}
        if selected:
            shot["query"] = selected[2]
            shot["relevanceScore"] = round(selected[1], 2)
        shot["sourceUrl"] = asset.source_url
        shot["provider"] = "pexels"
        if asset.photographer:
            shot["photographer"] = asset.photographer
        if asset.duration_seconds is not None:
            shot["durationInSeconds"] = asset.duration_seconds
        shots.append(shot)
        existing_urls.add(asset.url)
        used_asset_urls.add(asset.url)

    if not shots:
        return False
    scene["shots"] = shots
    return True


def _scene_visual_intent(scene: SceneDraft, keyword: str | None = None) -> str:
    intent = str(scene.get("visualIntent") or "").strip()
    if keyword:
        return f"{intent}; specifically show {keyword}" if intent else keyword
    return intent or str(scene.get("text") or "").strip()


def _scene_selection_guidance(scene: SceneDraft) -> str:
    guidance: list[str] = []
    must_contain = [str(item).strip() for item in scene.get("mustContain", []) if str(item).strip()]
    avoid = [str(item).strip() for item in scene.get("avoid", []) if str(item).strip()]
    preferred_shot = str(scene.get("preferredShot") or "").strip()
    if must_contain:
        guidance.append("Must visibly include: " + ", ".join(must_contain))
    if avoid:
        guidance.append("Avoid: " + ", ".join(avoid))
    if preferred_shot:
        guidance.append(f"Preferred framing/action: {preferred_shot}")
    return "; ".join(guidance)


def _record_third_party(
    scene: SceneDraft,
    clip: SelectedThirdPartyClip,
    project_root: Path,
) -> None:
    candidate = clip.candidate
    scene["videoUrl"] = public_asset_url(clip.path, project_root)
    scene["videoDurationInSeconds"] = clip.duration_seconds
    scene["mediaProvider"] = "youtube"
    scene["mediaSourceUrl"] = candidate.url
    scene["mediaSourceTitle"] = candidate.title
    scene["mediaUploader"] = candidate.uploader or ""
    scene["mediaQuery"] = candidate.query
    scene["mediaStartSeconds"] = clip.start_seconds
    scene["mediaEndSeconds"] = clip.end_seconds
    scene["mediaClipDurationSeconds"] = clip.duration_seconds
    scene["mediaSelectionScore"] = round(clip.relevance_score, 3)
    scene["mediaVisualScore"] = round(clip.visual_score, 3)
    scene["mediaSelectionReason"] = clip.reason
    scene["mediaTranscriptExcerpt"] = clip.transcript_excerpt


def _third_party_shot(clip: SelectedThirdPartyClip, project_root: Path) -> dict[str, Any]:
    candidate = clip.candidate
    return {
        "url": public_asset_url(clip.path, project_root),
        "type": "video",
        "provider": "youtube",
        "sourceUrl": candidate.url,
        "sourceTitle": candidate.title,
        "query": candidate.query,
        "uploader": candidate.uploader or "",
        "startSeconds": clip.start_seconds,
        "endSeconds": clip.end_seconds,
        "durationInSeconds": clip.duration_seconds,
        "relevanceScore": round(clip.relevance_score, 3),
        "visualScore": round(clip.visual_score, 3),
        "selectionReason": clip.reason,
        "transcriptExcerpt": clip.transcript_excerpt,
    }


def _asset_candidates(
    pexels: PexelsClient,
    keywords: list[str],
    used_asset_urls: set[str],
    *,
    prefer_video: bool,
) -> list[tuple[PexelsAsset, str, int]]:
    candidates: list[tuple[PexelsAsset, str, int]] = []
    for query_index, keyword in enumerate(keywords[:3]):
        if prefer_video:
            videos = pexels.search_video_candidates(keyword, exclude_urls=used_asset_urls)
            candidates.extend((asset, keyword, query_index) for asset in videos)
            if not videos:
                images = pexels.search_image_candidates(keyword, exclude_urls=used_asset_urls)
                candidates.extend((asset, keyword, query_index) for asset in images)
        else:
            images = pexels.search_image_candidates(keyword, exclude_urls=used_asset_urls)
            candidates.extend((asset, keyword, query_index) for asset in images)
            if not images:
                videos = pexels.search_video_candidates(keyword, exclude_urls=used_asset_urls)
                candidates.extend((asset, keyword, query_index) for asset in videos)
    return candidates


def _select_scene_asset(
    scene: SceneDraft,
    keywords: list[str],
    pexels: PexelsClient,
    used_asset_urls: set[str],
    *,
    prefer_video: bool,
) -> tuple[PexelsAsset, float, str] | None:
    selected = select_best_asset(
        _asset_candidates(pexels, keywords, used_asset_urls, prefer_video=prefer_video),
        required_duration_seconds=float(scene.get("durationInFrames", 1)) / 30,
    )
    return selected


def fetch_media(
    scenes: list[SceneDraft],
    settings: Settings,
    *,
    assets_dir: Path,
    avatar_dir: Path | None = None,
    third_party_enabled: bool = True,
) -> list[SceneDraft]:
    """Resolve third-party YouTube media first, then Pexels and generated images."""

    project_root = settings.project_root
    pexels = PexelsClient(settings.pexels_api_key)
    images = OpenAIImageClient(settings)
    resolved: list[SceneDraft] = []
    pexels_available = True
    used_asset_urls: set[str] = set()
    used_video_ids: set[str] = set()
    youtube: YouTubeClient | None = None
    visual_judge: DeepSeekVisualJudge | None = None
    if third_party_enabled:
        try:
            youtube = YouTubeClient()
            visual_judge = DeepSeekVisualJudge(
                settings.llm_api_key,
                model=settings.deepseek_vision_model,
                base_url=settings.deepseek_base_url,
            )
        except YouTubeClientError as error:
            print(f"Aviso: YouTube/yt-dlp no disponible; se usará el fallback: {error}")

    if youtube is not None and visual_judge is not None:
        print("   Fuente visual: YouTube/terceros primero; Pexels y GPT Image como fallback.")
    else:
        print("   Fuente visual: Pexels primero (YouTube/terceros desactivado o no disponible).")

    for scene_index, original_scene in enumerate(scenes):
        scene: SceneDraft = dict(original_scene)
        scene_type = scene.get("sceneType", "narrative")

        if scene_type == "avatar":
            source = _avatar_source(scene, avatar_dir, scene_index)
            if source is None:
                raise MediaFetchError(
                    f"La escena {scene_index + 1} es avatar pero no tiene videoUrl ni clip "
                    "scene-NNN.* en --avatar-dir."
                )
            if isinstance(source, Path):
                scene["videoUrl"] = _copy_local_avatar(
                    source,
                    assets_dir / "avatars",
                    project_root,
                    scene_index,
                )
            else:
                scene["videoUrl"] = source
            resolved.append(scene)
            continue

        # Full-screen title cards and whip transitions are intentionally media-free.
        if scene_type == "transition" or scene.get("templateName") == "whip-transition":
            resolved.append(scene)
            continue

        if scene.get("templateName") == "title-card":
            resolved.append(scene)
            continue

        keywords = scene.get("keywords") or []
        if not keywords and scene.get("text"):
            keywords = [scene["text"][:120]]

        if scene.get("templateName") in MONTAGE_TEMPLATES:
            third_party_shots: list[dict[str, Any]] = []
            if youtube is not None and visual_judge is not None:
                shot_keywords = keywords[:4] or [str(scene.get("visualIntent") or scene.get("text") or "")]
                for keyword in shot_keywords:
                    if not keyword.strip():
                        continue
                    selected_clip = select_third_party_clip(
                        visual_intent=_scene_visual_intent(scene, keyword),
                        keywords=[keyword],
                        transcript_context=str(scene.get("text") or ""),
                        selection_guidance=_scene_selection_guidance(scene),
                        youtube=youtube,
                        judge=visual_judge,
                        assets_dir=assets_dir,
                        used_video_ids=used_video_ids,
                    )
                    if selected_clip:
                        third_party_shots.append(_third_party_shot(selected_clip, project_root))
            if third_party_shots:
                scene["shots"] = third_party_shots
                first_shot = third_party_shots[0]
                scene["mediaProvider"] = "youtube"
                scene["mediaSourceUrl"] = str(first_shot["sourceUrl"])
                scene["mediaSourceTitle"] = str(first_shot.get("sourceTitle") or "")
                scene["mediaUploader"] = str(first_shot.get("uploader") or "")
                scene["mediaQuery"] = str(first_shot.get("query") or "")
                scene["mediaStartSeconds"] = float(first_shot["startSeconds"])
                scene["mediaEndSeconds"] = float(first_shot["endSeconds"])
                scene["mediaClipDurationSeconds"] = float(first_shot["durationInSeconds"])
                scene["mediaSelectionScore"] = float(first_shot["relevanceScore"])
                scene["mediaVisualScore"] = float(first_shot["visualScore"])
                scene["mediaSelectionReason"] = str(first_shot["selectionReason"])
                scene["mediaTranscriptExcerpt"] = str(first_shot["transcriptExcerpt"])

            if pexels_available:
                try:
                    _assign_montage_shots(
                        scene,
                        keywords,
                        pexels,
                        used_asset_urls,
                        prefer_video=scene.get("templateName") == "news-image-montage",
                        existing_shots=third_party_shots,
                    )
                except PexelsRateLimitError as error:
                    print(f"Aviso: {error}")
                    pexels_available = False
            if scene.get("shots"):
                resolved.append(scene)
                continue
            # A montage always receives a valid shot object, even if YouTube
            # and Pexels both fail. The generated image is the final fallback.
            generated_path = images.generate_image(
                _visual_prompt(scene, keywords),
                assets_dir / "images",
                quality="medium",
            )
            scene["shots"] = [{"url": _public_url(generated_path, project_root), "type": "image", "provider": "openai-image"}]
            scene["mediaProvider"] = "openai-image"
            resolved.append(scene)
            continue

        if (
            youtube is not None
            and visual_judge is not None
            and scene.get("templateName") in YOUTUBE_MEDIA_TEMPLATES
        ):
            try:
                selected_clip = select_third_party_clip(
                    visual_intent=_scene_visual_intent(scene),
                    keywords=keywords,
                    transcript_context=str(scene.get("text") or ""),
                    selection_guidance=_scene_selection_guidance(scene),
                    youtube=youtube,
                    judge=visual_judge,
                    assets_dir=assets_dir,
                    used_video_ids=used_video_ids,
                )
            except Exception as error:
                print(f"Aviso: selección de clip de terceros fallida; se usará el fallback: {error}")
                selected_clip = None
            if selected_clip:
                _record_third_party(scene, selected_clip, project_root)
                resolved.append(scene)
                continue

        prefer_video = scene.get("templateName") not in {"kenburns-image"}
        selected: tuple[PexelsAsset, float, str] | None = None
        if pexels_available:
            try:
                selected = _select_scene_asset(
                    scene,
                    keywords,
                    pexels,
                    used_asset_urls,
                    prefer_video=prefer_video,
                )
            except PexelsRateLimitError as error:
                print(f"Aviso: {error}")
                pexels_available = False
                selected = None

        asset = selected[0] if selected else None
        if asset:
            _assign_asset(
                scene,
                asset,
                query=selected[2] if selected else None,
                relevance_score=selected[1] if selected else None,
            )
            used_asset_urls.add(asset.url)
        else:
            # Heuristic placeholder until the LLM marks key scenes explicitly.
            quality = "high" if scene_type in {"hook", "stat"} else "medium"
            generated_path = images.generate_image(
                _visual_prompt(scene, keywords),
                assets_dir / "images",
                quality=quality,
            )
            scene["imageUrl"] = _public_url(generated_path, project_root)

        resolved.append(scene)

    return resolved
