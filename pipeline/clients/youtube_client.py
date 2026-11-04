from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from .youtube_cache import CachedInfo, ClipLibrary, InfoCache
from .youtube_proxy import ProxyConfig, new_session_id, scrub_proxy_env
from .youtube_traffic import TrafficMeter


@dataclass(frozen=True)
class SubtitleCue:
    start_seconds: float
    end_seconds: float
    text: str


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


@dataclass(frozen=True)
class StoryboardFrame:
    """One thumbnail of the seek-bar storyboard: a crop inside a mosaic image."""

    time_seconds: float
    fragment_url: str
    x: int
    y: int
    width: int
    height: int


class YouTubeClientError(RuntimeError):
    """Actionable failure from YouTube discovery or clip preparation."""


class YouTubeClient:
    """Bounded, unauthenticated YouTube search and short-clip downloader.

    Network discipline, from most to least traffic saved:

    * yt-dlp extracts a video's info dict (page + player + JS challenges) once
      per video id. The sanitized dict is stored on disk and re-fed with
      ``process_ie_result(info, download=True)`` for subtitles and every clip,
      exactly like ``--load-info-json``, while its media URLs stay valid.
    * Searches run ``extract_flat`` so results are not individually extracted.
    * Clips are capped at 720p/30fps and the smallest encoding at that size.
    * Prepared clips go to a shared library keyed by (video, range) so any run
      can reuse them; metadata and media traffic can use different proxies with
      a sticky session; local ffmpeg/ffprobe never inherit proxy variables.
    * Every byte that goes through each proxy role is counted in ``traffic``.
    """

    MAX_SEARCH_RESULTS = 5
    MAX_CLIP_SECONDS = 5.0
    MIN_VIDEO_SECONDS = 5.0
    DEFAULT_MAX_HEIGHT = 720
    DEFAULT_MAX_FPS = 30
    INFO_EXPIRY_MARGIN_SECONDS = 15 * 60
    _VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
    _TAG_RE = re.compile(r"<[^>]*>")

    def __init__(
        self,
        *,
        max_duration_seconds: float = 1800,
        socket_timeout_seconds: float = 20,
        proxies: ProxyConfig | None = None,
        cache_dir: Path | None = None,
        clip_library_dir: Path | None = None,
        max_height: int = DEFAULT_MAX_HEIGHT,
        max_fps: int = DEFAULT_MAX_FPS,
        info_expiry_margin_seconds: float = INFO_EXPIRY_MARGIN_SECONDS,
        traffic: TrafficMeter | None = None,
    ) -> None:
        if not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be a finite positive number.")
        if not math.isfinite(socket_timeout_seconds) or socket_timeout_seconds <= 0:
            raise ValueError("socket_timeout_seconds must be a finite positive number.")
        if isinstance(max_height, bool) or not isinstance(max_height, int) or max_height < 144:
            raise ValueError("max_height must be an integer of at least 144 pixels.")
        if isinstance(max_fps, bool) or not isinstance(max_fps, int) or max_fps < 1:
            raise ValueError("max_fps must be a positive integer.")
        self.max_duration_seconds = float(max_duration_seconds)
        self.socket_timeout_seconds = float(socket_timeout_seconds)
        self.max_height = max_height
        self.max_fps = max_fps
        self.proxies = proxies or ProxyConfig()
        self.traffic = traffic or TrafficMeter()
        self.session_id = new_session_id()
        self._temp_cache: tempfile.TemporaryDirectory[str] | None = None
        if cache_dir is None:
            self._temp_cache = tempfile.TemporaryDirectory(prefix="edit20-youtube-cache-")
            cache_dir = Path(self._temp_cache.name)
        self.cache_dir = Path(cache_dir)
        self.info_cache = InfoCache(self.cache_dir / "youtube-info", margin_seconds=info_expiry_margin_seconds)
        self.clip_library = ClipLibrary(Path(clip_library_dir) if clip_library_dir else self.cache_dir / "youtube-clips")
        self._subtitle_cache: dict[str, tuple[SubtitleCue, ...]] = {}
        self._ydls: dict[str, Any] = {}

    # ------------------------------------------------------------------ search

    def search(self, query: str, *, limit: int = 5) -> list[YouTubeCandidate]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_SEARCH_RESULTS:
            raise ValueError(f"limit must be an integer between 1 and {self.MAX_SEARCH_RESULTS}.")

        query = query.strip()
        try:
            ydl = self._ydl("metadata")
            # Flat extraction: the search response already carries id, title,
            # duration, uploader and live status; the full page is fetched once
            # per video later (and cached) instead of once per search result.
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        except YouTubeClientError:
            raise
        except Exception as exc:
            raise YouTubeClientError(
                f"YouTube search failed ({type(exc).__name__}). Check network connectivity "
                "and that YouTube is available."
            ) from exc

        entries = info.get("entries", []) if isinstance(info, dict) else []
        candidates: list[YouTubeCandidate] = []
        seen_ids: set[str] = set()
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            candidate = self._candidate_from_info(entry, query)
            if candidate is None or candidate.video_id in seen_ids:
                continue
            seen_ids.add(candidate.video_id)
            if candidate.video_id not in self._subtitle_cache:
                self._subtitle_cache[candidate.video_id] = self._retrieve_subtitles(
                    candidate.url,
                    candidate.video_id,
                )
            captions = self._subtitle_cache[candidate.video_id]
            candidates.append(
                YouTubeCandidate(
                    video_id=candidate.video_id,
                    url=candidate.url,
                    title=candidate.title,
                    uploader=candidate.uploader,
                    description=candidate.description,
                    duration_seconds=candidate.duration_seconds,
                    view_count=candidate.view_count,
                    thumbnail_url=candidate.thumbnail_url,
                    query=candidate.query,
                    subtitles=captions,
                )
            )
            if len(candidates) >= limit:
                break
        return candidates

    # ---------------------------------------------------------------- download

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

        try:
            library_hit = self.clip_library.find(
                candidate.video_id,
                start_seconds,
                capped_end,
                required_height=self.max_height,
            )
            if library_hit is not None:
                shutil.copy2(library_hit.path, output_path)
                self._validate_output_duration(output_path, allowed_duration)
                self.traffic.clip_library_hits += 1
                self._write_provenance_manifest(
                    manifest_path,
                    candidate,
                    requested_start=start_seconds,
                    requested_end=end_seconds,
                    clip_start=start_seconds,
                    clip_end=capped_end,
                    source_height=library_hit.source_height,
                    reused_from_library=True,
                )
                return output_path

            with tempfile.TemporaryDirectory(prefix="edit20-youtube-", dir=destination) as temp_dir:
                source_path, source_height = self._download_range(
                    candidate,
                    Path(temp_dir),
                    start_seconds,
                    capped_end,
                )
                self._transcode_clip(source_path, output_path, allowed_duration)
                self._validate_output_duration(output_path, allowed_duration)
                self._write_provenance_manifest(
                    manifest_path,
                    candidate,
                    requested_start=start_seconds,
                    requested_end=end_seconds,
                    clip_start=start_seconds,
                    clip_end=capped_end,
                    source_height=source_height,
                    reused_from_library=False,
                )
                try:
                    self.clip_library.store(
                        candidate.video_id,
                        start_seconds,
                        capped_end,
                        output_path,
                        source_height=source_height,
                        max_height_requested=self.max_height,
                        extra={"url": candidate.url, "title": candidate.title},
                    )
                except OSError:
                    pass  # The library is a cache; never fail the job for it.
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
                f"YouTube clip preparation failed ({type(exc).__name__}). Check network access "
                "and that FFmpeg is installed and available on PATH."
            ) from exc
        return output_path

    def _download_range(
        self,
        candidate: YouTubeCandidate,
        temp_dir: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> tuple[Path, int | None]:
        """Fetch only [start, end) of the video, reusing the cached info dict when valid.

        A cached dict costs zero metadata requests. If its URLs no longer work
        (expired or bound to another exit IP) the entry is dropped and the clip is
        fetched the ordinary way, which also refreshes the cache. That fallback
        is one extraction, the same price as never having had a cache.
        """

        cached = self.info_cache.load(candidate.video_id)
        if cached is not None:
            try:
                result = self._run_download(
                    lambda ydl: ydl.process_ie_result(copy.deepcopy(cached.info), download=True),
                    temp_dir,
                    start_seconds,
                    end_seconds,
                )
                self.traffic.info_reuses += 1
                return self._collect_source(temp_dir, result)
            except Exception:
                self.info_cache.invalidate(candidate.video_id)
                self.traffic.info_refreshes += 1
                for stale in temp_dir.glob("source.*"):
                    stale.unlink(missing_ok=True)

        try:
            result = self._run_download(
                lambda ydl: ydl.extract_info(candidate.url, download=True),
                temp_dir,
                start_seconds,
                end_seconds,
            )
        except Exception:
            # A failing exit IP should not poison the next clip: rotate the session.
            self._rotate_session()
            raise
        self.traffic.extractions += 1
        if isinstance(result, dict) and result.get("id") == candidate.video_id:
            try:
                self.info_cache.store(
                    result["id"],
                    result,
                    proxy_role="download",
                    session_id=self.session_id,
                    subtitle_cues=None,
                )
            except (OSError, ValueError):
                pass
        return self._collect_source(temp_dir, result)

    def _run_download(
        self,
        action: Callable[[Any], Any],
        temp_dir: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> Any:
        ydl = self._ydl("download")
        ydl.params["outtmpl"] = {"default": str(temp_dir / "source.%(ext)s")}
        ydl.params["download_ranges"] = self._download_range_callback(start_seconds, end_seconds)
        return action(ydl)

    def _collect_source(self, temp_dir: Path, result: Any) -> tuple[Path, int | None]:
        source_files = [
            path
            for path in temp_dir.glob("source.*")
            if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
        ]
        if not source_files:
            raise YouTubeClientError(
                "yt-dlp returned no video file. Check that the public video is still available."
            )
        source_path = source_files[0]
        self.traffic.clip_downloads += 1
        self.traffic.record("download", source_path.stat().st_size)
        return source_path, self._downloaded_height(result)

    @staticmethod
    def _downloaded_height(result: Any) -> int | None:
        if not isinstance(result, dict):
            return None
        downloads = result.get("requested_downloads")
        candidates: list[Any] = []
        if isinstance(downloads, list):
            candidates.extend(item.get("height") for item in downloads if isinstance(item, dict))
        candidates.append(result.get("height"))
        for value in candidates:
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _rotate_session(self) -> None:
        self.session_id = new_session_id()
        self._ydls.pop("download", None)
        if self.proxies.shares_exit_ip:
            self._ydls.pop("metadata", None)

    # ------------------------------------------------------------ storyboards

    def storyboard_frames(
        self,
        candidate: YouTubeCandidate,
        start_seconds: float,
        end_seconds: float,
        *,
        max_frames: int = 4,
    ) -> list[StoryboardFrame]:
        """Seek-bar thumbnails covering [start, end] from the cached info dict.

        Returns an empty list when the video has no storyboard or no cached
        info; callers then fall back to downloading the clip for preview.
        """

        if max_frames < 1:
            raise ValueError("max_frames must be at least 1.")
        if not self._VIDEO_ID_RE.fullmatch(candidate.video_id):
            return []
        cached = self.info_cache.load(candidate.video_id)
        if cached is None:
            return []
        storyboard = self._best_storyboard(cached.info)
        if storyboard is None:
            return []
        duration = self._finite_number(cached.info.get("duration")) or candidate.duration_seconds
        if duration is None or duration <= 0:
            return []
        fps = self._finite_number(storyboard.get("fps"))
        rows = self._optional_int(storyboard.get("rows"))
        columns = self._optional_int(storyboard.get("columns"))
        width = self._optional_int(storyboard.get("width"))
        height = self._optional_int(storyboard.get("height"))
        fragments = [
            fragment.get("url")
            for fragment in storyboard.get("fragments") or []
            if isinstance(fragment, dict) and isinstance(fragment.get("url"), str)
        ]
        if not fps or fps <= 0 or not rows or not columns or not width or not height or not fragments:
            return []
        per_fragment = rows * columns
        total_frames = per_fragment * len(fragments)
        end_seconds = min(end_seconds, duration)
        if end_seconds <= start_seconds:
            return []
        indices: list[int] = []
        for position in range(max_frames):
            moment = start_seconds + (end_seconds - start_seconds) * (position + 0.5) / max_frames
            index = min(total_frames - 1, max(0, int(moment * fps)))
            if index not in indices:
                indices.append(index)
        if len(indices) < 2:
            # Coarse storyboards (one frame every several seconds) may cover the
            # whole clip with one thumbnail; add neighbours for context.
            for neighbour in (indices[0] - 1, indices[0] + 1):
                if 0 <= neighbour < total_frames and neighbour not in indices:
                    indices.append(neighbour)
            indices.sort()
        frames: list[StoryboardFrame] = []
        for index in indices:
            fragment_index, within = divmod(index, per_fragment)
            row, column = divmod(within, columns)
            url = fragments[fragment_index]
            try:
                self._validate_storyboard_url(url)
            except YouTubeClientError:
                return []
            frames.append(
                StoryboardFrame(
                    time_seconds=index / fps,
                    fragment_url=url,
                    x=column * width,
                    y=row * height,
                    width=width,
                    height=height,
                )
            )
        return frames

    def storyboard_sheet(
        self,
        candidate: YouTubeCandidate,
        start_seconds: float,
        end_seconds: float,
        output_path: Path,
        *,
        max_frames: int = 4,
    ) -> Path | None:
        """Build a contact sheet from storyboard thumbnails without touching the proxy.

        Storyboard mosaics live on the i.ytimg.com CDN and are fetched directly.
        Returns ``None`` when the video has no usable storyboard.
        """

        frames = self.storyboard_frames(candidate, start_seconds, end_seconds, max_frames=max_frames)
        if not frames:
            return None
        try:
            with tempfile.TemporaryDirectory(prefix="edit20-storyboard-") as temp_dir:
                mosaics: dict[str, Path] = {}
                for frame in frames:
                    if frame.fragment_url in mosaics:
                        continue
                    mosaic_path = Path(temp_dir) / f"mosaic-{len(mosaics):02d}.jpg"
                    mosaic_path.write_bytes(self._fetch_direct(frame.fragment_url))
                    mosaics[frame.fragment_url] = mosaic_path
                from ..candidate_analyzer import create_storyboard_contact_sheet

                create_storyboard_contact_sheet(
                    [(mosaics[frame.fragment_url], frame.x, frame.y, frame.width, frame.height) for frame in frames],
                    output_path,
                )
        except Exception:
            return None
        self.traffic.storyboard_previews += 1
        return output_path

    def _fetch_direct(self, url: str) -> bytes:
        """GET a CDN resource bypassing every proxy (explicit and environment)."""

        import requests

        session = requests.Session()
        session.trust_env = False
        response = session.get(url, timeout=self.socket_timeout_seconds)
        response.raise_for_status()
        content = response.content
        self.traffic.record("direct", len(content))
        return content

    @staticmethod
    def _best_storyboard(info: dict[str, Any]) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_area = -1
        for fmt in info.get("formats") or []:
            if not isinstance(fmt, dict):
                continue
            if fmt.get("format_note") != "storyboard" and fmt.get("protocol") != "mhtml":
                continue
            try:
                area = int(fmt.get("width") or 0) * int(fmt.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if area > best_area:
                best, best_area = fmt, area
        return best

    @staticmethod
    def _validate_storyboard_url(url: str) -> None:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise YouTubeClientError("Malformed storyboard URL.") from exc
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not (host == "ytimg.com" or host.endswith(".ytimg.com")):
            raise YouTubeClientError("Storyboards must come from the ytimg.com CDN.")

    # ------------------------------------------------------------- yt-dlp glue

    def _ydl(self, role: str) -> Any:
        """One YoutubeDL per proxy role for the whole run.

        Re-creating the object per call used to re-download the player JS
        (needed for the signature timestamp and JS challenges) every time.
        """

        ydl = self._ydls.get(role)
        if ydl is None:
            options = self._metadata_options() if role == "metadata" else self._download_options()
            ydl = self._create_ydl(options)
            if not hasattr(ydl, "params"):
                ydl.params = options
            self.traffic.wrap_ydl(ydl, role)
            self._ydls[role] = ydl
        return ydl

    def _base_options(self, role: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": self.socket_timeout_seconds,
            # Persist signature functions and the JS-challenge solver's player
            # cache between runs instead of re-fetching the player per call.
            "cachedir": str(self.cache_dir / "yt-dlp"),
            "usenetrc": False,
            "cookiefile": None,
            "cookiesfrombrowser": None,
            "writethumbnail": False,
        }
        proxy = self.proxies.for_role(role, self.session_id)
        if proxy is not None:
            options["proxy"] = proxy
        return options

    def _metadata_options(self) -> dict[str, Any]:
        return {
            **self._base_options("metadata"),
            "extract_flat": "in_playlist",
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["es", "es-419", "en", "en-US"],
            "subtitlesformat": "vtt/json3/best",
        }

    def _download_options(self) -> dict[str, Any]:
        cap = f"[height<={self.max_height}]"
        return {
            **self._base_options("download"),
            "skip_download": False,
            # Resolution first, then frame rate up to the output's 30 fps, then
            # the smallest encoding of that size: a 720p60 or high-bitrate VP9
            # stream buys nothing after the clip is re-encoded at 1280x720/30.
            "format": f"bestvideo{cap}[fps<={self.max_fps}]/bestvideo{cap}/best{cap}",
            "format_sort": ["res", "fps", "+size", "+br"],
            "force_keyframes_at_cuts": True,
            "nopart": True,
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

    # --------------------------------------------------------------- metadata

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
        thumbnail = self._optional_string(info.get("thumbnail"))
        if thumbnail is None:
            thumbnails = info.get("thumbnails")
            if isinstance(thumbnails, list) and thumbnails and isinstance(thumbnails[-1], dict):
                thumbnail = self._optional_string(thumbnails[-1].get("url"))
        return YouTubeCandidate(
            video_id=video_id,
            url=canonical_url,
            title=str(info.get("title") or ""),
            uploader=self._optional_string(info.get("uploader") or info.get("channel")),
            description=str(info.get("description") or ""),
            duration_seconds=duration,
            view_count=self._optional_int(info.get("view_count")),
            thumbnail_url=thumbnail,
            query=query,
        )

    def _retrieve_subtitles(self, url: str, video_id: str) -> tuple[SubtitleCue, ...]:
        """Captions for ``video_id`` using at most one yt-dlp extraction per video.

        Order of preference: cues already stored next to the cached info dict
        (no network), subtitle files fetched from the cached info dict's URLs
        (no page/player requests), and finally a full extraction that is then
        cached for the downloads that follow.
        """

        try:
            cached = self.info_cache.load(video_id)
            if cached is not None and cached.subtitle_cues is not None:
                self.traffic.info_reuses += 1
                return self._cues_from_json(cached.subtitle_cues)
            if cached is not None:
                try:
                    cues = self._subtitles_from_info(cached.info, video_id)
                except Exception:
                    self.info_cache.invalidate(video_id)
                    self.traffic.info_refreshes += 1
                else:
                    self.traffic.info_reuses += 1
                    self.info_cache.update_subtitle_cues(video_id, self._cues_to_json(cues))
                    return cues
            entry = self._extract_with_subtitles(url, video_id)
            return self._cues_from_json(entry.subtitle_cues or [])
        except Exception:
            # Captions are optional and must never make otherwise valid search results disappear.
            return ()

    def _extract_with_subtitles(self, url: str, video_id: str) -> CachedInfo:
        ydl = self._ydl("metadata")
        with tempfile.TemporaryDirectory(prefix="edit20-youtube-subs-") as temp_dir:
            ydl.params["outtmpl"] = {"default": str(Path(temp_dir) / "%(id)s.%(ext)s")}
            # skip_download is set, so yt-dlp writes only the captions it finds.
            info = ydl.extract_info(url, download=True)
            cues = self._parse_subtitle_files(Path(temp_dir), video_id)
        self.traffic.extractions += 1
        if not isinstance(info, dict) or info.get("id") != video_id:
            raise YouTubeClientError("yt-dlp returned metadata for a different video.")
        return self.info_cache.store(
            video_id,
            info,
            proxy_role="metadata",
            session_id=self.session_id,
            subtitle_cues=self._cues_to_json(cues),
        )

    def _subtitles_from_info(self, info: dict[str, Any], video_id: str) -> tuple[SubtitleCue, ...]:
        ydl = self._ydl("metadata")
        with tempfile.TemporaryDirectory(prefix="edit20-youtube-subs-") as temp_dir:
            ydl.params["outtmpl"] = {"default": str(Path(temp_dir) / "%(id)s.%(ext)s")}
            ydl.process_ie_result(copy.deepcopy(info), download=True)
            return self._parse_subtitle_files(Path(temp_dir), video_id)

    def _parse_subtitle_files(self, directory: Path, video_id: str) -> tuple[SubtitleCue, ...]:
        subtitle_files = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".vtt", ".json3"}
            and path.name.startswith(f"{video_id}.")
        ]
        subtitle_files.sort(key=lambda path: self._subtitle_language_rank(path, video_id))
        for path in subtitle_files:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            if path.suffix.lower() == ".vtt":
                cues = self._parse_vtt(text)
            else:
                cues = self._parse_json3(text)
            if cues:
                unique = {
                    (cue.start_seconds, cue.end_seconds, cue.text): cue
                    for cue in cues
                    if cue.text
                }
                return tuple(sorted(unique.values(), key=lambda cue: (cue.start_seconds, cue.end_seconds)))
        return ()

    @staticmethod
    def _cues_to_json(cues: tuple[SubtitleCue, ...]) -> list[dict[str, Any]]:
        return [{"s": cue.start_seconds, "e": cue.end_seconds, "t": cue.text} for cue in cues]

    @staticmethod
    def _cues_from_json(items: list[dict[str, Any]]) -> tuple[SubtitleCue, ...]:
        cues: list[SubtitleCue] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                start = float(item["s"])
                end = float(item["e"])
            except (KeyError, TypeError, ValueError):
                continue
            text = str(item.get("t") or "")
            if math.isfinite(start) and math.isfinite(end) and end > start and text:
                cues.append(SubtitleCue(start, end, text))
        return tuple(cues)

    @classmethod
    def _parse_vtt(cls, content: str) -> list[SubtitleCue]:
        lines = content.lstrip("﻿").splitlines()
        cues: list[SubtitleCue] = []
        index = 0
        while index < len(lines):
            timing = re.match(r"^\s*(\S+)\s+-->\s+(\S+)", lines[index])
            if timing is None:
                index += 1
                continue
            start = cls._parse_timestamp(timing.group(1))
            end = cls._parse_timestamp(timing.group(2))
            index += 1
            text_lines: list[str] = []
            while index < len(lines) and lines[index].strip():
                if re.match(r"^\s*\S+\s+-->\s+\S+", lines[index]):
                    break
                text_lines.append(lines[index])
                index += 1
            text = cls._clean_subtitle_text(" ".join(text_lines))
            if start is not None and end is not None and end > start and text:
                cues.append(SubtitleCue(start, end, text))
            while index < len(lines) and not lines[index].strip():
                index += 1
        return cues

    @staticmethod
    def _subtitle_language_rank(path: Path, video_id: str) -> tuple[int, str]:
        suffix = path.name.removeprefix(f"{video_id}.")
        language = suffix.split(".", 1)[0].casefold()
        if language == "es" or language.startswith("es-"):
            rank = 0
        elif language == "en" or language.startswith("en-"):
            rank = 1
        else:
            rank = 2
        return rank, path.name.casefold()

    @classmethod
    def _parse_json3(cls, content: str) -> list[SubtitleCue]:
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return []
        cues: list[SubtitleCue] = []
        for event in payload.get("events", []) if isinstance(payload, dict) else []:
            if not isinstance(event, dict):
                continue
            try:
                start = float(event["tStartMs"]) / 1000
                end = start + float(event["dDurationMs"]) / 1000
            except (KeyError, TypeError, ValueError):
                continue
            segments = event.get("segs", [])
            text = cls._clean_subtitle_text(
                "".join(str(segment.get("utf8", "")) for segment in segments if isinstance(segment, dict))
            )
            if math.isfinite(start) and math.isfinite(end) and end > start and text:
                cues.append(SubtitleCue(start, end, text))
        return cues

    @staticmethod
    def _parse_timestamp(timestamp: str) -> float | None:
        normalized = timestamp.replace(",", ".")
        pieces = normalized.split(".", 1)
        clock = pieces[0].split(":")
        if len(clock) == 2:
            hours = 0
            minutes, seconds = clock
        elif len(clock) == 3:
            hours, minutes, seconds = clock
        else:
            return None
        try:
            fraction = float(f"0.{pieces[1]}") if len(pieces) == 2 else 0.0
            value = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + fraction
        except ValueError:
            return None
        return float(value) if math.isfinite(value) else None

    @classmethod
    def _clean_subtitle_text(cls, text: str) -> str:
        return " ".join(unescape(cls._TAG_RE.sub("", text)).split())

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

    # ------------------------------------------------------------- local media

    @staticmethod
    def _write_provenance_manifest(
        path: Path,
        candidate: YouTubeCandidate,
        *,
        requested_start: float,
        requested_end: float,
        clip_start: float,
        clip_end: float,
        source_height: int | None = None,
        reused_from_library: bool = False,
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
            "source_height": source_height,
            "reused_from_library": reused_from_library,
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
            env=scrub_proxy_env(),
        )
        if result.returncode != 0:
            raise YouTubeClientError(
                "FFmpeg could not encode the clip as silent H.264 MP4. Check the source media "
                "and your FFmpeg installation."
            )
        if not destination.is_file() or destination.stat().st_size == 0:
            raise YouTubeClientError("FFmpeg completed without producing a valid MP4 file.")

    @staticmethod
    def _validate_output_duration(path: Path, maximum_seconds: float) -> None:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=scrub_proxy_env(),
        )
        if result.returncode != 0:
            raise YouTubeClientError("ffprobe could not validate the downloaded clip.")
        try:
            duration = float(json.loads(result.stdout)["format"]["duration"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise YouTubeClientError("ffprobe returned an invalid clip duration.") from exc
        if not math.isfinite(duration) or duration <= 0 or duration > maximum_seconds + 1e-6:
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
