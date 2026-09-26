from __future__ import annotations

from typing import Any, Literal, TypedDict


SceneType = Literal["hook", "narrative", "stat", "transition", "avatar"]


class WordTimestamp(TypedDict):
    word: str
    start: float
    end: float


class Transcript(TypedDict):
    text: str
    duration_seconds: float
    words: list[WordTimestamp]
    segments: list[dict[str, Any]]


class SceneDraft(TypedDict, total=False):
    text: str
    imageUrl: str
    videoUrl: str
    videoDurationInSeconds: float
    mediaSourceUrl: str
    mediaQuery: str
    mediaRelevanceScore: float
    mediaPhotographer: str
    visualIntent: str
    mustContain: list[str]
    avoid: list[str]
    preferredShot: str
    mediaProvider: str
    mediaSourceTitle: str
    mediaUploader: str
    mediaStartSeconds: float
    mediaEndSeconds: float
    mediaClipDurationSeconds: float
    mediaSelectionScore: float
    mediaVisualScore: float
    mediaSelectionReason: str
    mediaTranscriptExcerpt: str
    durationInFrames: int
    accentColor: str
    sceneType: SceneType
    templateName: str
    keywords: list[str]
    start_word_index: int
    end_word_index: int
    start_time_seconds: float
    end_time_seconds: float
    avatar_path: str
    shots: list[dict[str, Any]]
    timelinePoints: list[dict[str, Any]]
    comparisonColumns: list[dict[str, Any]]
