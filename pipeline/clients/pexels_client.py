from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import requests

from ..timing import METRICS


# A 1080p render gains nothing from 4K sources; they only make decoding slower.
TARGET_VIDEO_WIDTH = 1920


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
    thumbnail_url: str | None = None


class PexelsRateLimitError(RuntimeError):
    """Raised after bounded retries when Pexels still returns HTTP 429."""


class PexelsError(RuntimeError):
    """A Pexels request failed for a reason other than rate limiting."""


def pick_video_file(files: list[dict[str, Any]], excluded: set[str]) -> dict[str, Any] | None:
    """Choose the smallest landscape file that still covers 1920 px, else the widest one."""

    usable = [file for file in files if file.get("link") and file["link"] not in excluded]
    if not usable:
        return None
    landscape = [file for file in usable if (file.get("width") or 0) >= (file.get("height") or 0)]
    pool = landscape or usable
    enough = [file for file in pool if (file.get("width") or 0) >= TARGET_VIDEO_WIDTH]
    if enough:
        return min(enough, key=lambda file: file.get("width") or 0)
    return max(pool, key=lambda file: file.get("width") or 0)


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
        # Serialises API calls so pacing and the cache stay correct under threads.
        self._lock = threading.Lock()

    def _get(self, path: str, params: dict[str, str | int]) -> dict[str, Any]:
        cache_key = (path, tuple(sorted((key, str(value)) for key, value in params.items())))
        with self._lock:
            if cache_key in self._cache:
                METRICS.count("pexels.cache_hits")
                return self._cache[cache_key]
            return self._get_uncached(path, params, cache_key)

    def _get_uncached(
        self,
        path: str,
        params: dict[str, str | int],
        cache_key: tuple[str, tuple[tuple[str, str], ...]],
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        for attempt in range(self._max_retries + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._min_interval_seconds:
                time.sleep(self._min_interval_seconds - elapsed)

            METRICS.count("pexels.requests")
            try:
                response = self._session.get(url, params=params, timeout=self._timeout_seconds)
            except requests.RequestException as error:
                self._last_request_at = time.monotonic()
                if attempt >= self._max_retries:
                    raise PexelsError(
                        f"Pexels no respondió tras {self._max_retries + 1} intentos "
                        f"({type(error).__name__})."
                    ) from error
                time.sleep(min(8.0, 2**attempt))
                continue
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

            if response.status_code in {401, 403}:
                raise PexelsError(
                    f"Pexels rechazó la clave (HTTP {response.status_code}). Revisa PEXELS_API_KEY en .env."
                )
            if response.status_code >= 500 and attempt < self._max_retries:
                time.sleep(min(8.0, 2**attempt))
                continue
            if response.status_code >= 400:
                raise PexelsError(f"Pexels devolvió HTTP {response.status_code} para {path}.")

            try:
                payload = response.json()
            except ValueError as error:
                raise PexelsError("Pexels devolvió una respuesta que no es JSON.") from error
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
            selected = pick_video_file(files, excluded)
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
                        thumbnail_url=video.get("image") or None,
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
                        thumbnail_url=src.get("medium") or src.get("small") or None,
                    )
                )
        return assets

    def search_image(self, keyword: str, *, exclude_urls: set[str] | None = None) -> PexelsAsset | None:
        return next(iter(self.search_image_candidates(keyword, exclude_urls=exclude_urls)), None)


    def download_asset(self, asset_url: str, output_dir: Path, *, timeout_seconds: float = 120) -> Path:
        """Store a chosen photo/video locally so renders do not depend on the network.

        The file name derives from the URL, so repeated runs reuse the same file.
        """

        if urlsplit(asset_url).scheme != "https":
            raise PexelsError("Solo se descargan assets de Pexels por HTTPS.")
        suffix = Path(urlsplit(asset_url).path).suffix.lower()
        if suffix not in {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".mp4" if "video" in asset_url else ".jpg"
        digest = hashlib.sha256(asset_url.encode("utf-8")).hexdigest()[:16]
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"pexels_{digest}{suffix}"
        if target.is_file() and target.stat().st_size > 0:
            METRICS.count("pexels.download_cache_hits")
            return target

        partial = target.with_name(f".{target.name}.{threading.get_ident()}.part")
        try:
            with METRICS.timed("pexels.download"):
                # The CDN needs no API key; a plain request avoids leaking it to another host.
                with requests.get(asset_url, stream=True, timeout=(10, timeout_seconds)) as response:
                    if response.status_code >= 400:
                        raise PexelsError(f"La descarga de Pexels devolvió HTTP {response.status_code}.")
                    with partial.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                handle.write(chunk)
            if partial.stat().st_size == 0:
                raise PexelsError("La descarga de Pexels llegó vacía.")
            os.replace(partial, target)
        except requests.RequestException as error:
            raise PexelsError(f"No se pudo descargar el asset de Pexels ({type(error).__name__}).") from error
        finally:
            partial.unlink(missing_ok=True)
        return target
