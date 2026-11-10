from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import threading
from concurrent.futures import Future
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ..media_tools import MediaToolError, probe_duration_seconds
from ..runlog import log, short_error
from ..subtitles import (
    SubtitleCue,
    clean_subtitle_text,
    parse_json3,
    parse_timestamp,
    parse_vtt,
    read_best_subtitles,
    subtitle_language_rank,
)
from ..timing import METRICS


__all__ = ["SubtitleCue", "YouTubeCandidate", "YouTubeClient", "YouTubeClientError"]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _YtdlpLogCapture:
    """Receives yt-dlp's messages so a failure can be explained instead of swallowed."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @staticmethod
    def _clean(message: object) -> str:
        return " ".join(_ANSI_RE.sub("", str(message)).split())

    def debug(self, message: object) -> None:  # yt-dlp also routes info through debug()
        pass

    def info(self, message: object) -> None:
        pass

    def warning(self, message: object) -> None:
        text = self._clean(message)
        self.warnings.append(text)
        log.debug("yt-dlp aviso: %s", text)

    def error(self, message: object) -> None:
        text = self._clean(message)
        self.errors.append(text)
        log.debug("yt-dlp error: %s", text)

    def last_error(self, *, limit: int = 300) -> str:
        if not self.errors:
            return ""
        text = self.errors[-1]
        return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class YouTubeCandidate:
    video_id: str
    url: str
    title: str
    uploader: str | None
    description: str
    duration_seconds: float | None
    view_count: int | None
    thumbnail_url: str | None
    query: str
    subtitles: tuple[SubtitleCue, ...] = ()


class YouTubeClientError(RuntimeError):
    """Actionable failure from YouTube discovery or clip preparation."""


class YouTubeClient:
    """Bounded, unauthenticated YouTube search and short-clip downloader."""

    MAX_SEARCH_RESULTS = 5
    MAX_CLIP_SECONDS = 5.0
    MIN_VIDEO_SECONDS = 5.0
    _VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

    def __init__(
        self,
        *,
        max_duration_seconds: float = 1800,
        socket_timeout_seconds: float = 20,
        max_parallel: int = 4,
        single_pass_subtitles: bool = True,
    ) -> None:
        if not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be a finite positive number.")
        if not math.isfinite(socket_timeout_seconds) or socket_timeout_seconds <= 0:
            raise ValueError("socket_timeout_seconds must be a finite positive number.")
        if isinstance(max_parallel, bool) or not isinstance(max_parallel, int) or max_parallel < 1:
            raise ValueError("max_parallel must be a positive integer.")
        self.max_duration_seconds = float(max_duration_seconds)
        self.socket_timeout_seconds = float(socket_timeout_seconds)
        # True: metadata and captions come from one yt-dlp extraction per video.
        # False: legacy behaviour, a second extraction per video just for captions.
        self.single_pass_subtitles = bool(single_pass_subtitles)
        self._subtitle_cache: dict[str, tuple[SubtitleCue, ...]] = {}
        self._search_futures: dict[tuple[str, int], Future[list[YouTubeCandidate]]] = {}
        self._clip_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        # Bounds simultaneous yt-dlp operations no matter how many scenes run in parallel.
        self._gate = threading.BoundedSemaphore(max_parallel)

    @staticmethod
    def ensure_available() -> None:
        """Fail early, with a fix, when yt-dlp is not importable."""

        try:
            import yt_dlp  # noqa: F401
        except ImportError as exc:
            raise YouTubeClientError(
                "yt-dlp is not installed. Install project dependencies with `pip install -r requirements.txt`."
            ) from exc

    def search(self, query: str, *, limit: int = 5) -> list[YouTubeCandidate]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_SEARCH_RESULTS:
            raise ValueError(f"limit must be an integer between 1 and {self.MAX_SEARCH_RESULTS}.")

        query = query.strip()
        key = (query.casefold(), limit)
        with self._lock:
            future = self._search_futures.get(key)
            owner = future is None
            if owner:
                future = self._search_futures[key] = Future()
        assert future is not None
        if owner:
            try:
                future.set_result(self._search_uncached(query, limit))
            except BaseException as exc:
                # Failures are not cached: the next scene may succeed.
                with self._lock:
                    self._search_futures.pop(key, None)
                future.set_exception(exc)
                raise
        else:
            METRICS.count("youtube.search_cache_hits")
        return list(future.result())

    def _search_uncached(self, query: str, limit: int) -> list[YouTubeCandidate]:
        with tempfile.TemporaryDirectory(prefix="edit20-youtube-search-") as temp_dir:
            subtitle_dir = Path(temp_dir)
            options = self._base_options()
            if self.single_pass_subtitles:
                options.update(self._subtitle_options(subtitle_dir))
                # One blocked video or caption track must not sink the other results.
                options["ignoreerrors"] = True
            capture: _YtdlpLogCapture = options["logger"]
            try:
                ydl = self._create_ydl(options)
                with self._gate, METRICS.timed("youtube.search"):
                    # With skip_download, download=True only writes the requested captions.
                    info = ydl.extract_info(
                        f"ytsearch{limit}:{query}",
                        download=self.single_pass_subtitles,
                    )
            except YouTubeClientError:
                raise
            except Exception as exc:
                raise YouTubeClientError(
                    f"YouTube search failed ({short_error(exc)}). Check network connectivity "
                    "and that YouTube is available."
                ) from exc

            entries = info.get("entries", []) if isinstance(info, dict) else []
            entries = [entry for entry in entries or [] if isinstance(entry, dict)]
            if not entries and capture.errors:
                raise YouTubeClientError(
                    f"YouTube search returned nothing; yt-dlp reported: {capture.last_error()}"
                )

            candidates: list[YouTubeCandidate] = []
            seen_ids: set[str] = set()
            for entry in entries:
                candidate = self._candidate_from_info(entry, query)
                if candidate is None or candidate.video_id in seen_ids:
                    continue
                seen_ids.add(candidate.video_id)
                captions = self._subtitles_for(candidate, subtitle_dir)
                candidates.append(replace(candidate, subtitles=captions))
                if len(candidates) >= limit:
                    break
            METRICS.count("youtube.videos_extracted", len(entries))
            return candidates

    def _subtitles_for(self, candidate: YouTubeCandidate, subtitle_dir: Path) -> tuple[SubtitleCue, ...]:
        with self._lock:
            cached = self._subtitle_cache.get(candidate.video_id)
        if cached is not None:
            return cached
        if self.single_pass_subtitles:
            captions = read_best_subtitles(subtitle_dir, candidate.video_id)
            if not captions:
                # Not cached: a later search may fetch the track that failed this time.
                return ()
        else:
            captions = self._retrieve_subtitles(candidate.url, candidate.video_id)
        with self._lock:
            self._subtitle_cache.setdefault(candidate.video_id, captions)
            return self._subtitle_cache[candidate.video_id]

    def download_clip(
        self,
        candidate: YouTubeCandidate,
        start_seconds: float,
        end_seconds: float,
        output_dir: Path,
        *,
        max_clip_seconds: float = 5.0,
    ) -> Path:
        if not self._VIDEO_ID_RE.fullmatch(candidate.video_id):
            raise YouTubeClientError("The candidate has an invalid YouTube video ID.")
        self._validate_youtube_url(candidate.url, expected_video_id=candidate.video_id)
        if not math.isfinite(start_seconds) or start_seconds < 0:
            raise ValueError("start_seconds must be a finite, non-negative number.")
        if not math.isfinite(end_seconds) or end_seconds <= start_seconds:
            raise ValueError("end_seconds must be finite and greater than start_seconds.")
        if not math.isfinite(max_clip_seconds) or max_clip_seconds <= 0:
            raise ValueError("max_clip_seconds must be a finite positive number.")

        requested_duration = end_seconds - start_seconds
        allowed_duration = min(requested_duration, float(max_clip_seconds), self.MAX_CLIP_SECONDS)
        if candidate.duration_seconds is not None:
            if not math.isfinite(candidate.duration_seconds) or candidate.duration_seconds <= start_seconds:
                raise ValueError("start_seconds must be earlier than the candidate video duration.")
            allowed_duration = min(allowed_duration, candidate.duration_seconds - start_seconds)
        if allowed_duration <= 0:
            raise ValueError("The requested clip range contains no downloadable video.")

        capped_end = start_seconds + allowed_duration
        digest = hashlib.sha256(
            f"{candidate.video_id}:{start_seconds:.6f}:{capped_end:.6f}".encode("utf-8")
        ).hexdigest()[:16]
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / f"youtube_{digest}.mp4"
        manifest_path = output_path.with_suffix(".json")

        with self._lock:
            clip_lock = self._clip_locks.setdefault(digest, threading.Lock())
        with clip_lock:
            if self._reusable_clip(output_path, manifest_path, allowed_duration):
                METRICS.count("youtube.clip_cache_hits")
                return output_path
            self._download_and_prepare(
                candidate,
                start_seconds,
                end_seconds,
                capped_end,
                allowed_duration,
                destination,
                output_path,
                manifest_path,
            )
        return output_path

    def _reusable_clip(self, output_path: Path, manifest_path: Path, allowed_duration: float) -> bool:
        """A clip already prepared for this exact range is reused, after re-checking its cap."""

        try:
            if not (output_path.is_file() and manifest_path.is_file() and output_path.stat().st_size > 0):
                return False
            self._validate_output_duration(output_path, allowed_duration)
        except (OSError, YouTubeClientError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return True

    def _download_and_prepare(
        self,
        candidate: YouTubeCandidate,
        start_seconds: float,
        end_seconds: float,
        capped_end: float,
        allowed_duration: float,
        destination: Path,
        output_path: Path,
        manifest_path: Path,
    ) -> None:
        options = {
            **self._base_options(),
            "skip_download": False,
            "format": "bestvideo[height<=720]",
            "outtmpl": str(Path("source.%(ext)s")),
            "download_ranges": self._download_range_callback(start_seconds, capped_end),
            "force_keyframes_at_cuts": True,
            "noplaylist": True,
            "nopart": True,
        }
        capture: _YtdlpLogCapture = options["logger"]
        try:
            with tempfile.TemporaryDirectory(prefix="edit20-youtube-", dir=destination) as temp_dir:
                options["outtmpl"] = str(Path(temp_dir) / "source.%(ext)s")
                ydl = self._create_ydl(options)
                with self._gate, METRICS.timed("youtube.download"):
                    ydl.download([candidate.url])
                source_files = [
                    path
                    for path in Path(temp_dir).glob("source.*")
                    if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
                ]
                if not source_files:
                    detail = capture.last_error()
                    raise YouTubeClientError(
                        "yt-dlp returned no video file. Check that the public video is still available."
                        + (f" yt-dlp reported: {detail}" if detail else "")
                    )
                source_path = source_files[0]
                # Prepared next to the source and moved into place only once validated,
                # so parallel scenes never observe a half-written clip.
                staged_path = Path(temp_dir) / "clip.mp4"
                with METRICS.timed("youtube.transcode"):
                    self._transcode_clip(source_path, staged_path, allowed_duration)
                self._validate_output_duration(staged_path, allowed_duration)
                os.replace(staged_path, output_path)
                self._write_provenance_manifest(
                    manifest_path,
                    candidate,
                    requested_start=start_seconds,
                    requested_end=end_seconds,
                    clip_start=start_seconds,
                    clip_end=capped_end,
                )
        except YouTubeClientError:
            output_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            raise
        except subprocess.TimeoutExpired as exc:
            output_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            raise YouTubeClientError("FFmpeg timed out while preparing the short clip.") from exc
        except FileNotFoundError as exc:
            output_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            raise YouTubeClientError(
                "A required executable or media file is missing. Install yt-dlp and FFmpeg, "
                "then ensure ffmpeg and ffprobe are available on PATH."
            ) from exc
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            raise YouTubeClientError(
                f"YouTube clip preparation failed ({short_error(exc)}). Check network access "
                "and that FFmpeg is installed and available on PATH."
            ) from exc

    @staticmethod
    def _write_provenance_manifest(
        path: Path,
        candidate: YouTubeCandidate,
        *,
        requested_start: float,
        requested_end: float,
        clip_start: float,
        clip_end: float,
    ) -> None:
        manifest = {
            "source": "youtube",
            "video_id": candidate.video_id,
            "url": candidate.url,
            "title": candidate.title,
            "uploader": candidate.uploader,
            "query": candidate.query,
            "requested_range_seconds": {"start": requested_start, "end": requested_end},
            "clip_range_seconds": {"start": clip_start, "end": clip_end},
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _base_options(self) -> dict[str, Any]:
        return {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": self.socket_timeout_seconds,
            "cachedir": False,
            "usenetrc": False,
            "cookiefile": None,
            "cookiesfrombrowser": None,
            # Messages are captured (not printed) so errors can be reported with their cause.
            "logger": _YtdlpLogCapture(),
        }

    @staticmethod
    def _subtitle_options(directory: Path) -> dict[str, Any]:
        return {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["es", "es-419", "en", "en-US"],
            "subtitlesformat": "vtt/json3/best",
            "outtmpl": str(directory / "%(id)s.%(ext)s"),
        }

    @staticmethod
    def _create_ydl(options: dict[str, Any]) -> Any:
        try:
            import yt_dlp
        except ImportError as exc:
            raise YouTubeClientError(
                "yt-dlp is not installed. Install project dependencies with `pip install -r requirements.txt`."
            ) from exc
        return yt_dlp.YoutubeDL(options)

    @staticmethod
    def _download_range_callback(start_seconds: float, end_seconds: float) -> Any:
        try:
            from yt_dlp.utils import download_range_func
        except ImportError as exc:
            raise YouTubeClientError(
                "The installed yt-dlp version does not provide download-range support. "
                "Upgrade yt-dlp and retry."
            ) from exc
        return download_range_func(None, [(start_seconds, end_seconds)])

    def _candidate_from_info(self, info: dict[str, Any], query: str) -> YouTubeCandidate | None:
        video_id = info.get("id")
        if not isinstance(video_id, str) or not self._VIDEO_ID_RE.fullmatch(video_id):
            return None
        if info.get("is_live") is True or info.get("live_status") in {"is_live", "is_upcoming"}:
            return None

        duration = self._finite_number(info.get("duration"))
        if duration is None or duration < self.MIN_VIDEO_SECONDS or duration > self.max_duration_seconds:
            return None

        supplied_url = next(
            (
                info.get(key)
                for key in ("webpage_url", "original_url", "url")
                if isinstance(info.get(key), str) and info.get(key).startswith(("https://", "http://"))
            ),
            None,
        )
        if supplied_url is not None:
            try:
                self._validate_youtube_url(supplied_url)
            except YouTubeClientError:
                return None
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        return YouTubeCandidate(
            video_id=video_id,
            url=canonical_url,
            title=str(info.get("title") or ""),
            uploader=self._optional_string(info.get("uploader") or info.get("channel")),
            description=str(info.get("description") or ""),
            duration_seconds=duration,
            view_count=self._optional_int(info.get("view_count")),
            thumbnail_url=self._optional_string(info.get("thumbnail")),
            query=query,
        )

    def _retrieve_subtitles(self, url: str, video_id: str) -> tuple[SubtitleCue, ...]:
        """Legacy two-pass caption lookup (used when single_pass_subtitles is False)."""

        try:
            with tempfile.TemporaryDirectory(prefix="edit20-youtube-subs-") as temp_dir:
                options = {**self._base_options(), **self._subtitle_options(Path(temp_dir))}
                ydl = self._create_ydl(options)
                # yt-dlp's skip_download prevents media retrieval; only available captions are written.
                with self._gate, METRICS.timed("youtube.subtitles"):
                    ydl.download([url])
                return read_best_subtitles(Path(temp_dir), video_id)
        except Exception as exc:
            # Captions are optional and must never make otherwise valid search results disappear.
            log.debug("Subtítulos no disponibles para %s: %s", video_id, short_error(exc))
            return ()

    # Thin delegates kept so callers and tests can keep using the class API.
    @classmethod
    def _parse_vtt(cls, content: str) -> list[SubtitleCue]:
        return parse_vtt(content)

    @staticmethod
    def _subtitle_language_rank(path: Path, video_id: str) -> tuple[int, str]:
        return subtitle_language_rank(path, video_id)

    @classmethod
    def _parse_json3(cls, content: str) -> list[SubtitleCue]:
        return parse_json3(content)

    @staticmethod
    def _parse_timestamp(timestamp: str) -> float | None:
        return parse_timestamp(timestamp)

    @classmethod
    def _clean_subtitle_text(cls, text: str) -> str:
        return clean_subtitle_text(text)

    @staticmethod
    def _validate_youtube_url(url: str, *, expected_video_id: str | None = None) -> None:
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError as exc:
            raise YouTubeClientError("The candidate URL is malformed.") from exc
        allowed_host = host == "youtube.com" or host.endswith(".youtube.com") or host == "youtu.be"
        if (
            parsed.scheme.lower() != "https"
            or not allowed_host
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            raise YouTubeClientError("Only public HTTPS youtube.com and youtu.be URLs are allowed.")
        if expected_video_id is not None:
            if host == "youtu.be":
                resource_id = parsed.path.strip("/").split("/", 1)[0]
            else:
                resource_id = parse_qs(parsed.query).get("v", [None])[0]
                if resource_id is None:
                    match = re.match(r"^/(?:embed|live|shorts|v)/([^/]+)", parsed.path)
                    resource_id = match.group(1) if match else None
            if resource_id != expected_video_id:
                raise YouTubeClientError("The candidate URL does not match its YouTube video ID.")

    @staticmethod
    def _transcode_clip(source: Path, destination: Path, duration_seconds: float) -> None:
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-t",
            f"{duration_seconds:.6f}",
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            r"scale=w=min(1280\,iw):h=-2,fps=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            detail = " ".join((result.stderr or "").split())[-300:]
            raise YouTubeClientError(
                "FFmpeg could not encode the clip as silent H.264 MP4. Check the source media "
                "and your FFmpeg installation." + (f" FFmpeg said: {detail}" if detail else "")
            )
        if not destination.is_file() or destination.stat().st_size == 0:
            raise YouTubeClientError("FFmpeg completed without producing a valid MP4 file.")

    @staticmethod
    def _validate_output_duration(path: Path, maximum_seconds: float) -> None:
        try:
            duration = probe_duration_seconds(path, timeout=30)
        except MediaToolError as exc:
            if "not found" in str(exc):
                raise FileNotFoundError("ffprobe") from exc
            raise YouTubeClientError(f"ffprobe could not validate the downloaded clip. {exc}") from exc
        if duration <= 0 or duration > maximum_seconds + 1e-6:
            raise YouTubeClientError(
                f"The prepared clip is {duration:.3f}s; the permitted maximum is "
                f"{maximum_seconds:.3f}s."
            )

    @staticmethod
    def _finite_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None
