from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import requests


@dataclass(frozen=True)
class PexelsAsset:
    kind: Literal["video", "image"]
    url: str
    source_url: str
    photographer: str | None = None
    duration_seconds: float | None = None
    alt_text: str = ""
    width: int | None = None
    height: int | None = None
    result_rank: int = 0


class PexelsRateLimitError(RuntimeError):
    """Raised after bounded retries when Pexels still returns HTTP 429."""


class PexelsClient:
    BASE_URL = "https://api.pexels.com/v1"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 20,
        max_retries: int = 2,
        min_interval_seconds: float = 0.15,
    ) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Authorization": api_key})
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, Any]] = {}

    def _get(self, path: str, params: dict[str, str | int]) -> dict[str, Any]:
        cache_key = (path, tuple(sorted((key, str(value)) for key, value in params.items())))
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        for attempt in range(self._max_retries + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._min_interval_seconds:
                time.sleep(self._min_interval_seconds - elapsed)

            response = self._session.get(url, params=params, timeout=self._timeout_seconds)
            self._last_request_at = time.monotonic()

            if response.status_code == 429:
                if attempt >= self._max_retries:
                    raise PexelsRateLimitError(
                        "Pexels ha agotado el rate limit después de varios reintentos. "
                        "El pipeline puede continuar usando GPT Image como fallback."
                    )
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                time.sleep(min(30.0, max(1.0, delay)))
                continue

            response.raise_for_status()
            payload = response.json()
            self._cache[cache_key] = payload
            return payload

        raise AssertionError("El cliente Pexels salió del bucle de reintentos inesperadamente.")

    def search_video_candidates(
        self,
        keyword: str,
        *,
        exclude_urls: set[str] | None = None,
        limit: int = 8,
    ) -> list[PexelsAsset]:
        payload = self._get(
            "/videos/search",
            {
                "query": keyword,
                "orientation": "landscape",
                "size": "medium",
                "per_page": limit,
            },
        )
        excluded = exclude_urls or set()
        assets: list[PexelsAsset] = []
        for result_rank, video in enumerate(payload.get("videos", [])):
            files = [file for file in video.get("video_files", []) if file.get("link")]
            landscape_files = [
                file for file in files if (file.get("width") or 0) >= (file.get("height") or 0)
            ]
            candidates = sorted(
                landscape_files or files,
                key=lambda file: file.get("width") or 0,
                reverse=True,
            )
            selected = next((file for file in candidates if file["link"] not in excluded), None)
            if selected:
                user = video.get("user") or {}
                duration_seconds = None
                if video.get("duration") is not None:
                    try:
                        duration_seconds = float(video["duration"])
                    except (TypeError, ValueError):
                        duration_seconds = None
                assets.append(
                    PexelsAsset(
                        kind="video",
                        url=selected["link"],
                        source_url=video.get("url", ""),
                        photographer=user.get("name"),
                        duration_seconds=duration_seconds,
                        alt_text=str(video.get("url", "")),
                        width=selected.get("width"),
                        height=selected.get("height"),
                        result_rank=result_rank,
                    )
                )
        return assets

    def search_video(self, keyword: str, *, exclude_urls: set[str] | None = None) -> PexelsAsset | None:
        return next(iter(self.search_video_candidates(keyword, exclude_urls=exclude_urls)), None)

    def search_image_candidates(
        self,
        keyword: str,
        *,
        exclude_urls: set[str] | None = None,
        limit: int = 8,
    ) -> list[PexelsAsset]:
        payload = self._get(
            "/search",
            {
                "query": keyword,
                "orientation": "landscape",
                "per_page": limit,
            },
        )
        excluded = exclude_urls or set()
        assets: list[PexelsAsset] = []
        for result_rank, photo in enumerate(payload.get("photos", [])):
            src = photo.get("src") or {}
            image_url = src.get("large2x") or src.get("large") or src.get("original")
            if image_url and image_url not in excluded:
                assets.append(
                    PexelsAsset(
                        kind="image",
                        url=image_url,
                        source_url=photo.get("url", ""),
                        photographer=photo.get("photographer"),
                        alt_text=str(photo.get("alt") or ""),
                        width=photo.get("width"),
                        height=photo.get("height"),
                        result_rank=result_rank,
                    )
                )
        return assets

    def search_image(self, keyword: str, *, exclude_urls: set[str] | None = None) -> PexelsAsset | None:
        return next(iter(self.search_image_candidates(keyword, exclude_urls=exclude_urls)), None)
