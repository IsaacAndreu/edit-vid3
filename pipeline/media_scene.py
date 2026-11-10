"""Pure helpers that read from or write media fields on a scene."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .clients.pexels_client import PexelsAsset, PexelsClient
from .config import REMOTION_FPS
from .media_ranker import select_best_asset
from .third_party_media import SelectedThirdPartyClip, SelectionTrace, public_asset_url
from .types import SceneDraft


def is_remote(url: object) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def visual_prompt(scene: SceneDraft, keywords: list[str]) -> str:
    text = scene.get("text", "").strip()
    keyword_text = ", ".join(keywords) or text
    return (
        "Cinematic 16:9 b-roll image for a YouTube documentary scene. "
        "Natural composition, realistic lighting, no text, no logos, no watermark. "
        f"Scene context: {text}. Visual keywords: {keyword_text}."
    )


def scene_visual_intent(scene: SceneDraft, keyword: str | None = None) -> str:
    intent = str(scene.get("visualIntent") or "").strip()
    if keyword:
        return f"{intent}; specifically show {keyword}" if intent else keyword
    return intent or str(scene.get("text") or "").strip()


def scene_selection_guidance(scene: SceneDraft) -> str:
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


# ---------------------------------------------------------------------------
# YouTube provenance
# ---------------------------------------------------------------------------
def clip_record(clip: SelectedThirdPartyClip, project_root: Path) -> dict[str, Any]:
    """Single provenance record of a selected YouTube clip (also the montage shot shape)."""

    candidate = clip.candidate
    record: dict[str, Any] = {
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
        "videoId": candidate.video_id,
    }
    if clip.contact_sheet is not None:
        try:
            record["contactSheet"] = public_asset_url(clip.contact_sheet, project_root)
        except ValueError:
            pass
    return record


def apply_clip_provenance(scene: SceneDraft, record: dict[str, Any]) -> None:
    """Copy a clip record to the scene-level provenance fields."""

    scene["mediaProvider"] = "youtube"
    scene["mediaSourceUrl"] = str(record["sourceUrl"])
    scene["mediaSourceTitle"] = str(record.get("sourceTitle") or "")
    scene["mediaUploader"] = str(record.get("uploader") or "")
    scene["mediaQuery"] = str(record.get("query") or "")
    scene["mediaStartSeconds"] = float(record["startSeconds"])
    scene["mediaEndSeconds"] = float(record["endSeconds"])
    scene["mediaClipDurationSeconds"] = float(record["durationInSeconds"])
    scene["mediaSelectionScore"] = float(record["relevanceScore"])
    scene["mediaVisualScore"] = float(record["visualScore"])
    scene["mediaSelectionReason"] = str(record["selectionReason"])
    scene["mediaTranscriptExcerpt"] = str(record["transcriptExcerpt"])
    if record.get("videoId"):
        scene["mediaVideoId"] = str(record["videoId"])
    if record.get("contactSheet"):
        scene["mediaContactSheet"] = str(record["contactSheet"])


def trace_payload(trace: SelectionTrace, slot: str | None, project_root: Path) -> dict[str, Any]:
    """Serializable audit of one selection attempt, with contact sheets as public URLs."""

    payload = trace.as_dict()
    if slot is not None:
        payload["keyword"] = slot
    for finalist in payload["finalists"]:
        sheet = finalist.get("contactSheet")
        if sheet:
            try:
                finalist["contactSheet"] = public_asset_url(Path(sheet), project_root)
            except ValueError:
                pass
    return payload


# ---------------------------------------------------------------------------
# Pexels
# ---------------------------------------------------------------------------
def assign_asset(
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
    if asset.thumbnail_url:
        scene["mediaThumbnailUrl"] = asset.thumbnail_url


def asset_candidates(
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


def select_scene_asset(
    scene: SceneDraft,
    keywords: list[str],
    pexels: PexelsClient,
    used_asset_urls: set[str],
    *,
    prefer_video: bool,
) -> tuple[PexelsAsset, float, str] | None:
    return select_best_asset(
        asset_candidates(pexels, keywords, used_asset_urls, prefer_video=prefer_video),
        required_duration_seconds=float(scene.get("durationInFrames", 1)) / REMOTION_FPS,
    )


def assign_montage_shots(
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
    shot_duration_seconds = (
        float(scene.get("durationInFrames", 1)) / REMOTION_FPS / max(1, min(4, len(keywords)))
    )
    for keyword in keywords[:4]:
        candidates = asset_candidates(
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
        if asset.thumbnail_url:
            shot["thumbnailUrl"] = asset.thumbnail_url
        shots.append(shot)
        existing_urls.add(asset.url)
        used_asset_urls.add(asset.url)

    if not shots:
        return False
    scene["shots"] = shots
    return True
