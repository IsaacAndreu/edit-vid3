"""Shared state of the media stage: options, per-scene plan and the run context."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .candidate_analyzer import DeepSeekVisualJudge
from .checkpoint import MediaCheckpoint
from .clients.pexels_client import PexelsClient
from .clients.youtube_client import YouTubeClient
from .config import DEFAULT_MEDIA_CONCURRENCY, Settings
from .templates import TemplateSpec
from .types import SceneDraft


class MediaFetchError(RuntimeError):
    """Raised when a scene cannot be provided with its required media."""


KIND_AVATAR = "avatar"
KIND_NONE = "none"
KIND_OVERRIDE = "override"
KIND_SINGLE = "single"
KIND_SHOTS = "shots"

NO_PROVIDER = "ninguno"


@dataclass
class MediaOptions:
    third_party_enabled: bool = True
    concurrency: int = DEFAULT_MEDIA_CONCURRENCY
    download_stock: bool = True
    checkpoint_path: Path | None = None
    # False ignores (and overwrites) whatever a previous run stored.
    resume: bool = True
    # 1-based scene numbers to resolve again, avoiding their previous pick.
    redo_scenes: frozenset[int] = frozenset()


@dataclass
class Plan:
    """What one scene needs from the media stage."""

    index: int
    scene: SceneDraft
    kind: str
    spec: TemplateSpec | None
    keywords: list[str] = field(default_factory=list)
    third_party: bool = False
    # YouTube selections to attempt: [None] for a single clip, one keyword per montage shot.
    slots: list[str | None] = field(default_factory=list)
    fingerprint: str = ""

    @property
    def number(self) -> int:
        return self.index + 1


@dataclass
class MediaContext:
    """Everything the phases share during one run."""

    settings: Settings
    assets_dir: Path
    options: MediaOptions
    checkpoint: MediaCheckpoint
    pexels: PexelsClient
    avatar_dir: Path | None = None
    youtube: YouTubeClient | None = None
    judge: DeepSeekVisualJudge | None = None
    image_client: Any | None = None

    # Cross-scene de-duplication.
    used_video_ids: set[str] = field(default_factory=set)
    used_asset_urls: set[str] = field(default_factory=set)
    claim_lock: threading.Lock = field(default_factory=threading.Lock)

    # Results gathered for the summary, the timeline and the timing file.
    providers: dict[int, str] = field(default_factory=dict)
    traces: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    third_party_seconds: dict[int, float] = field(default_factory=dict)
    # Scenes that fell back because of an outage; they are retried on the next run.
    transient_misses: set[int] = field(default_factory=set)

    @property
    def project_root(self) -> Path:
        return self.settings.project_root

    @property
    def images(self) -> Any:
        """GPT Image client, built on first use so runs that never need it skip the SDK."""

        if self.image_client is None:
            from .clients.openai_images import OpenAIImageClient

            self.image_client = OpenAIImageClient(self.settings)
        return self.image_client
