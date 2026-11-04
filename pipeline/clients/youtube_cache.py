from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Keys yt-dlp's --clean-infojson strips before writing an info file. Dropping
# them lets ``YoutubeDL.process_ie_result(info, download=True)`` re-run format
# selection and downloads exactly like ``--load-info-json`` does.
_PRIVATE_INFO_KEYS = frozenset(
    {
        "requested_downloads",
        "requested_formats",
        "requested_subtitles",
        "requested_entries",
        "entries",
        "filepath",
        "_filename",
        "filename",
        "infojson_filename",
        "original_url",
        "playlist_autonumber",
    }
)

# Fallback validity when no format URL carries an ``expire`` parameter.
DEFAULT_INFO_TTL_SECONDS = 3600.0


def sanitize_info(info: Any) -> Any:
    """Return a JSON-serialisable copy of ``info`` without yt-dlp private keys."""

    def filter_fn(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: filter_fn(item)
                for key, item in value.items()
                if item is not None and not str(key).startswith("__") and key not in _PRIVATE_INFO_KEYS
            }
        if isinstance(value, (list, tuple, set)):
            return [filter_fn(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return repr(value)

    sanitized = filter_fn(info)
    if isinstance(sanitized, dict):
        sanitized.setdefault("_type", "video")
    return sanitized


def earliest_format_expiry(info: dict[str, Any]) -> float | None:
    """Smallest ``expire`` timestamp found in the media format URLs, if any."""

    expiries: list[float] = []
    for fmt in info.get("formats") or []:
        if not isinstance(fmt, dict):
            continue
        url = fmt.get("url")
        if not isinstance(url, str):
            continue
        try:
            values = parse_qs(urlsplit(url).query).get("expire")
        except ValueError:
            continue
        if not values:
            continue
        try:
            expiries.append(float(values[0]))
        except (TypeError, ValueError):
            continue
    return min(expiries) if expiries else None


@dataclass(frozen=True)
class CachedInfo:
    video_id: str
    info: dict[str, Any]
    stored_at: float
    proxy_role: str
    session_id: str | None
    subtitle_cues: list[dict[str, Any]] | None

    @property
    def expires_at(self) -> float:
        expiry = earliest_format_expiry(self.info)
        return expiry if expiry is not None else self.stored_at + DEFAULT_INFO_TTL_SECONDS

    def is_fresh(self, *, now: float | None = None, margin_seconds: float) -> bool:
        current = time.time() if now is None else now
        return self.expires_at - margin_seconds > current


class InfoCache:
    """Per-video-id store of sanitized yt-dlp info dicts (one extraction per video).

    Entries are kept while every media URL is at least ``margin_seconds`` away
    from its ``expire`` parameter. A download that fails with a cached entry must
    call :meth:`invalidate` and extract again, so a stale entry can never cost
    more than the plain extraction it replaced.
    """

    def __init__(self, directory: Path, *, margin_seconds: float = 900.0) -> None:
        self.directory = Path(directory)
        self.margin_seconds = float(margin_seconds)

    def _path(self, video_id: str) -> Path:
        if not _VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError("video_id must be an 11-character YouTube id.")
        return self.directory / f"{video_id}.json"

    def load(self, video_id: str, *, now: float | None = None) -> CachedInfo | None:
        path = self._path(video_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        info = payload.get("info") if isinstance(payload, dict) else None
        if not isinstance(info, dict) or info.get("id") != video_id:
            self.invalidate(video_id)
            return None
        try:
            stored_at = float(payload.get("stored_at"))
        except (TypeError, ValueError):
            self.invalidate(video_id)
            return None
        cues = payload.get("subtitle_cues")
        entry = CachedInfo(
            video_id=video_id,
            info=info,
            stored_at=stored_at,
            proxy_role=str(payload.get("proxy_role") or "direct"),
            session_id=payload.get("session_id") if isinstance(payload.get("session_id"), str) else None,
            subtitle_cues=cues if isinstance(cues, list) else None,
        )
        if not entry.is_fresh(now=now, margin_seconds=self.margin_seconds):
            self.invalidate(video_id)
            return None
        return entry

    def store(
        self,
        video_id: str,
        info: dict[str, Any],
        *,
        proxy_role: str,
        session_id: str | None,
        subtitle_cues: list[dict[str, Any]] | None = None,
        now: float | None = None,
    ) -> CachedInfo:
        path = self._path(video_id)
        sanitized = sanitize_info(info)
        if not isinstance(sanitized, dict) or sanitized.get("id") != video_id:
            raise ValueError("The info dict does not belong to the requested video id.")
        stored_at = time.time() if now is None else now
        if subtitle_cues is None:
            previous = self.load(video_id, now=now)
            subtitle_cues = previous.subtitle_cues if previous else None
        payload = {
            "stored_at": stored_at,
            "proxy_role": proxy_role,
            "session_id": session_id,
            "subtitle_cues": subtitle_cues,
            "info": sanitized,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)
        return CachedInfo(video_id, sanitized, stored_at, proxy_role, session_id, subtitle_cues)

    def update_subtitle_cues(self, video_id: str, cues: list[dict[str, Any]]) -> None:
        entry = self.load(video_id)
        if entry is None:
            return
        self.store(
            video_id,
            entry.info,
            proxy_role=entry.proxy_role,
            session_id=entry.session_id,
            subtitle_cues=cues,
            now=entry.stored_at,
        )

    def invalidate(self, video_id: str) -> None:
        try:
            self._path(video_id).unlink(missing_ok=True)
        except OSError:
            pass


@dataclass(frozen=True)
class LibraryClip:
    path: Path
    manifest_path: Path
    source_height: int | None
    max_height_requested: int | None


class ClipLibrary:
    """Shared store of prepared clips keyed by (video id, start, end).

    Any run can reuse a clip another project already downloaded, provided it was
    taken from a source at least as tall as the resolution now requested, or
    from the best resolution the video offers under the same cap.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    @staticmethod
    def key(video_id: str, start_seconds: float, end_seconds: float) -> str:
        if not _VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError("video_id must be an 11-character YouTube id.")
        return f"{video_id}_{start_seconds:.3f}_{end_seconds:.3f}".replace(".", "p")

    def _paths(self, video_id: str, start_seconds: float, end_seconds: float) -> tuple[Path, Path]:
        stem = self.key(video_id, start_seconds, end_seconds)
        return self.directory / f"{stem}.mp4", self.directory / f"{stem}.json"

    def find(
        self,
        video_id: str,
        start_seconds: float,
        end_seconds: float,
        *,
        required_height: int,
    ) -> LibraryClip | None:
        clip_path, manifest_path = self._paths(video_id, start_seconds, end_seconds)
        if not clip_path.is_file() or clip_path.stat().st_size == 0:
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        source_height = _optional_int(manifest.get("source_height"))
        max_requested = _optional_int(manifest.get("max_height_requested"))
        tall_enough = source_height is not None and source_height >= required_height
        best_available = max_requested is not None and max_requested >= required_height
        if not (tall_enough or best_available):
            return None
        return LibraryClip(clip_path, manifest_path, source_height, max_requested)

    def store(
        self,
        video_id: str,
        start_seconds: float,
        end_seconds: float,
        clip_path: Path,
        *,
        source_height: int | None,
        max_height_requested: int,
        extra: dict[str, Any] | None = None,
    ) -> LibraryClip:
        target_path, manifest_path = self._paths(video_id, start_seconds, end_seconds)
        self.directory.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_suffix(".mp4.tmp")
        shutil.copy2(clip_path, temp_path)
        temp_path.replace(target_path)
        manifest = {
            "video_id": video_id,
            "clip_range_seconds": {"start": start_seconds, "end": end_seconds},
            "source_height": source_height,
            "max_height_requested": max_height_requested,
            "stored_at": time.time(),
            **(extra or {}),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return LibraryClip(target_path, manifest_path, source_height, max_height_requested)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None
