"""Shared fakes for tests. Nothing here touches the network or runs media tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.clients.pexels_client import PexelsAsset
from pipeline.clients.youtube_client import YouTubeCandidate
from pipeline.config import Settings
from pipeline.third_party_media import (
    OUTCOME_NO_CANDIDATES,
    OUTCOME_SELECTED,
    SelectedThirdPartyClip,
    SelectionTrace,
)


def make_settings(project_root: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = dict(
        project_root=project_root,
        llm_provider="deepseek",
        llm_model="deepseek-flash",
        llm_api_key="llm-key",
        pexels_api_key="pexels-key",
        openai_api_key="openai-key",
        deepseek_vision_model="deepseek-flash",
        media_concurrency=1,
    )
    values.update(overrides)
    return Settings(**values)


def assets_dir_for(project_root: Path, run: str = "run") -> Path:
    path = project_root / "public" / "pipeline-assets" / run
    path.mkdir(parents=True, exist_ok=True)
    return path


def scene(template: str = "kenburns-image", scene_type: str = "narrative", **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "text": "Casino por dentro",
        "keywords": ["casino roulette table", "casino floor"],
        "visualIntent": "roulette wheel spinning in a casino",
        "mustContain": ["roulette"],
        "avoid": ["logo"],
        "preferredShot": "close-up",
        "sceneType": scene_type,
        "templateName": template,
        "durationInFrames": 150,
        "start_word_index": 0,
        "end_word_index": 5,
    }
    base.update(extra)
    return base


def youtube_candidate(video_id: str = "videoid0001") -> YouTubeCandidate:
    return YouTubeCandidate(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title=f"Title {video_id}",
        uploader="Uploader",
        description="",
        duration_seconds=120,
        view_count=1,
        thumbnail_url=None,
        query="casino roulette table",
    )


class FakeSelector:
    """Stands in for ``select_third_party_clip``; creates the clip file it returns."""

    def __init__(self, *, video_ids: list[str] | None = None, miss: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._video_ids = list(video_ids or [])
        self.miss = miss

    def __call__(self, **kwargs: Any) -> SelectedThirdPartyClip | None:
        self.calls.append(kwargs)
        trace: SelectionTrace = kwargs["trace"]
        trace.queries = ["q"]
        if self.miss:
            trace.outcome = OUTCOME_NO_CANDIDATES
            return None
        excluded = set(kwargs.get("excluded_video_ids") or ())
        used: set[str] = kwargs["used_video_ids"]
        lock = kwargs.get("claim_lock")
        video_id = None
        with lock:
            pool = self._video_ids or [f"auto{len(self.calls):07d}"]
            for candidate_id in pool:
                if candidate_id not in used and candidate_id not in excluded:
                    video_id = candidate_id
                    used.add(candidate_id)
                    break
        if video_id is None:
            trace.outcome = OUTCOME_NO_CANDIDATES
            return None
        clip_dir = kwargs["assets_dir"] / "third-party" / "clips"
        clip_dir.mkdir(parents=True, exist_ok=True)
        clip = clip_dir / f"youtube_{video_id}.mp4"
        clip.write_bytes(b"clip")
        trace.outcome = OUTCOME_SELECTED
        return SelectedThirdPartyClip(
            path=clip,
            candidate=youtube_candidate(video_id),
            start_seconds=10.0,
            end_seconds=14.5,
            transcript_excerpt="the roulette wheel spins",
            relevance_score=0.61,
            visual_score=0.83,
            reason="roulette wheel clearly visible",
        )


class FakePexels:
    def __init__(
        self,
        *,
        videos: bool = True,
        images: bool = True,
        error: Exception | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self.videos = videos
        self.images = images
        self.error = error
        self.download_error = download_error
        self.calls: list[tuple[str, str]] = []
        self.downloads: list[str] = []

    def _maybe_fail(self) -> None:
        if self.error is not None:
            raise self.error

    def search_video_candidates(self, keyword: str, *, exclude_urls: set[str] | None = None, limit: int = 8) -> list[PexelsAsset]:
        self.calls.append(("video", keyword))
        self._maybe_fail()
        if not self.videos:
            return []
        slug = keyword.replace(" ", "-")
        assets = [
            PexelsAsset(
                kind="video",
                url=f"https://videos.pexels.com/{slug}-{rank}.mp4",
                source_url=f"https://www.pexels.com/video/{slug}-{rank}/",
                photographer="Ana",
                duration_seconds=12.0,
                alt_text=slug,
                width=1920,
                height=1080,
                result_rank=rank,
                thumbnail_url=f"https://images.pexels.com/{slug}-{rank}.jpg",
            )
            for rank in range(3)
        ]
        return [asset for asset in assets if asset.url not in (exclude_urls or set())]

    def search_image_candidates(self, keyword: str, *, exclude_urls: set[str] | None = None, limit: int = 8) -> list[PexelsAsset]:
        self.calls.append(("image", keyword))
        self._maybe_fail()
        if not self.images:
            return []
        slug = keyword.replace(" ", "-")
        assets = [
            PexelsAsset(
                kind="image",
                url=f"https://images.pexels.com/photos/{slug}-{rank}.jpeg",
                source_url=f"https://www.pexels.com/photo/{slug}-{rank}/",
                photographer="Luis",
                alt_text=keyword,
                width=4000,
                height=3000,
                result_rank=rank,
            )
            for rank in range(3)
        ]
        return [asset for asset in assets if asset.url not in (exclude_urls or set())]

    def download_asset(self, asset_url: str, output_dir: Path, **_kwargs: Any) -> Path:
        if self.download_error is not None:
            raise self.download_error
        self.downloads.append(asset_url)
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / ("pexels_" + asset_url.rsplit("/", 1)[-1])
        target.write_bytes(b"asset")
        return target


class FakeImages:
    def __init__(self, *, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls: list[tuple[str, str]] = []

    def generate_image(self, prompt: str, output_dir: Path, *, quality: str = "medium") -> Path:
        self.calls.append((prompt, quality))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("content policy violation")
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"generated-{len(self.calls):03d}.png"
        target.write_bytes(b"png")
        return target
