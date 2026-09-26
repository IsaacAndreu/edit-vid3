from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


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


class YouTubeClientError(RuntimeError):
    """Actionable failure from YouTube discovery or clip preparation."""


class YouTubeClient:
    """Bounded, unauthenticated YouTube search and short-clip downloader."""

    MAX_SEARCH_RESULTS = 5
    MAX_CLIP_SECONDS = 5.0
    MIN_VIDEO_SECONDS = 5.0
    _VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
    _TAG_RE = re.compile(r"<[^>]*>")

    def __init__(
        self,
        *,
        max_duration_seconds: float = 1800,
        socket_timeout_seconds: float = 20,
    ) -> None:
        if not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be a finite positive number.")
        if not math.isfinite(socket_timeout_seconds) or socket_timeout_seconds <= 0:
            raise ValueError("socket_timeout_seconds must be a finite positive number.")
        self.max_duration_seconds = float(max_duration_seconds)
        self.socket_timeout_seconds = float(socket_timeout_seconds)
        self._subtitle_cache: dict[str, tuple[SubtitleCue, ...]] = {}

    def search(self, query: str, *, limit: int = 5) -> list[YouTubeCandidate]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_SEARCH_RESULTS:
            raise ValueError(f"limit must be an integer between 1 and {self.MAX_SEARCH_RESULTS}.")

        query = query.strip()
        options = self._base_options()
        try:
            ydl = self._create_ydl(options)
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
        try:
            with tempfile.TemporaryDirectory(prefix="edit20-youtube-", dir=destination) as temp_dir:
                options["outtmpl"] = str(Path(temp_dir) / "source.%(ext)s")
                ydl = self._create_ydl(options)
                ydl.download([candidate.url])
                source_files = [
                    path
                    for path in Path(temp_dir).glob("source.*")
                    if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
                ]
                if not source_files:
                    raise YouTubeClientError(
                        "yt-dlp returned no video file. Check that the public video is still available."
                    )
                source_path = source_files[0]
                self._transcode_clip(source_path, output_path, allowed_duration)
                self._validate_output_duration(output_path, allowed_duration)
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
                f"YouTube clip preparation failed ({type(exc).__name__}). Check network access "
                "and that FFmpeg is installed and available on PATH."
            ) from exc
        return output_path

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
        try:
            with tempfile.TemporaryDirectory(prefix="edit20-youtube-subs-") as temp_dir:
                options = {
                    **self._base_options(),
                    "skip_download": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": ["es", "es-419", "en", "en-US"],
                    "subtitlesformat": "vtt/json3/best",
                    "outtmpl": str(Path(temp_dir) / "%(id)s.%(ext)s"),
                }
                ydl = self._create_ydl(options)
                # yt-dlp's skip_download prevents media retrieval; only available captions are written.
                ydl.download([url])
                subtitle_files = [
                    path
                    for path in Path(temp_dir).iterdir()
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
        except Exception:
            # Captions are optional and must never make otherwise valid search results disappear.
            return ()

    @classmethod
    def _parse_vtt(cls, content: str) -> list[SubtitleCue]:
        lines = content.lstrip("\ufeff").splitlines()
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
