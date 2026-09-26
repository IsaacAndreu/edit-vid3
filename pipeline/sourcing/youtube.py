"""Third-party footage from YouTube via yt-dlp (stage 3).

Search → metadata filters → low-res (360p) analysis media. Everything is cached globally:
cache/search/youtube/ for searches, cache/videos/<id>/ for metadata, subtitles and the
360p analysis files, so a second video about a similar topic reuses the work.

Long videos are not downloaded whole: only sections around subtitle hits for the shot's
terms (or a few sampled windows when there are no subtitles). The HD download of the
chosen fragment happens later, in stage 6 (ingest).
"""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from ..clients.youtube_client import YouTubeClient as _LegacyParsers
from ..schemas import AnalysisRange, BrollSpec, Candidate
from .common import Pacer, SourceUnavailable, cached_json, fuse_ranks, key, tokens


_BLOCK_MARKERS = ("sign in to confirm", "not a bot")
_RATE_MARKERS = ("http error 429", "too many requests")


class RateLimited(RuntimeError):
    pass
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class _QuietLogger:
    """yt-dlp prints errors itself even with quiet=True; we raise and report them instead."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


class YouTubeSource:
    def __init__(
        self, *, root: Path, cache_dir: Path, config: dict[str, Any], cookies_text: str | None = None
    ) -> None:
        self.root = root
        self.cache_dir = cache_dir
        self.cfg = config
        self.pacer = Pacer(float(config.get("min_interval", 1.5)))
        self.blocked: str | None = None
        # A couple of concurrent requests at most; a 429 pauses every thread (the limit is per account/IP).
        self._slots = threading.Semaphore(int(config.get("concurrency", 2)))
        self._cooldown_until = 0.0
        self._cookies_text = cookies_text
        self._local = threading.local()
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "retries": 3,
            "logger": _QuietLogger(),
        }
        if shutil.which("deno") is None and shutil.which("node") is not None:
            options["js_runtimes"] = {"node": {}}
        if config.get("player_client"):
            options["extractor_args"] = {"youtube": {"player_client": list(config["player_client"])}}
        if config.get("cookies_from_browser"):
            options["cookiesfrombrowser"] = (str(config["cookies_from_browser"]),)
        if config.get("rate_limit"):
            options["ratelimit"] = _parse_rate(str(config["rate_limit"]))
        if config.get("sleep_requests"):
            options["sleep_interval_requests"] = float(config["sleep_requests"])
        self.base_options = options

    # --- yt-dlp plumbing ------------------------------------------------------------

    def _cookie_file(self) -> str | None:
        """Per-thread private copy: yt-dlp saves rotated cookies back into the file it was given."""

        if not self._cookies_text:
            return None
        path = getattr(self._local, "cookie_path", None)
        if path is None:
            handle, path = tempfile.mkstemp(prefix="yt-cookies-", suffix=".txt")
            with os.fdopen(handle, "w", encoding="utf-8") as cookie_file:
                cookie_file.write(self._cookies_text)
            self._local.cookie_path = path
        return path

    def _ydl(self, extra: dict[str, Any] | None = None) -> Any:
        import yt_dlp

        options = {**self.base_options, **(extra or {})}
        cookie_file = self._cookie_file()
        if cookie_file:
            options["cookiefile"] = cookie_file
        return yt_dlp.YoutubeDL(options)

    def _call(self, action: str, fn: Any, *, rate_retries: int = 2) -> Any:
        if self.blocked:
            raise SourceUnavailable(self.blocked)
        for attempt in range(rate_retries + 1):
            try:
                with self._slots:
                    delay = self._cooldown_until - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    self.pacer.wait()
                    return fn()
            except Exception as error:
                message = str(error)
                lowered = message.casefold()
                if any(marker in lowered for marker in _BLOCK_MARKERS):
                    self.blocked = (
                        "YouTube bloquea este equipo (\"Sign in to confirm you're not a bot\"). "
                        "Ejecuta el sourcing en local o configura cookies (youtube.cookies_file / YOUTUBE_COOKIES_B64)."
                    )
                    raise SourceUnavailable(self.blocked) from None
                if any(marker in lowered for marker in _RATE_MARKERS):
                    if attempt < rate_retries:
                        pause = float(self.cfg.get("rate_backoff", 20)) * 3**attempt
                        self._cooldown_until = max(self._cooldown_until, time.monotonic() + pause)
                        continue
                    raise RateLimited(f"yt-dlp {action}: YouTube limita peticiones (429)") from None
                raise RuntimeError(f"yt-dlp {action}: {message[:200]}") from None
        raise AssertionError("unreachable")

    # --- search & metadata ----------------------------------------------------------

    def search(self, query: str) -> list[dict[str, Any]]:
        limit = int(self.cfg.get("results_per_query", 8))

        def produce() -> list[dict[str, Any]]:
            info = self._call(
                "search",
                lambda: self._ydl({"extract_flat": "in_playlist", "skip_download": True}).extract_info(
                    f"ytsearch{limit}:{query}", download=False
                ),
            )
            keep = ("id", "title", "channel", "uploader", "duration", "url", "live_status", "view_count")
            return [{k: entry.get(k) for k in keep} for entry in (info or {}).get("entries") or [] if isinstance(entry, dict)]

        return cached_json(self.cache_dir / "search" / "youtube" / f"{key(query, limit)}.json", produce)

    def passes_search_filters(self, entry: dict[str, Any]) -> bool:
        duration = entry.get("duration")
        if not isinstance(entry.get("id"), str) or not _VIDEO_ID.match(entry["id"]):
            return False
        if not isinstance(duration, (int, float)):
            return False
        if not float(self.cfg.get("min_duration", 30)) <= duration <= float(self.cfg.get("max_duration", 3600)):
            return False
        if entry.get("live_status") in ("is_live", "is_upcoming", "post_live"):
            return False
        return "/shorts/" not in str(entry.get("url") or "")

    def info(self, video_id: str) -> dict[str, Any]:
        def produce() -> dict[str, Any]:
            data = self._call(
                "metadata",
                lambda: self._ydl({"skip_download": True}).extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                ),
            )
            heights = [f.get("height") or 0 for f in data.get("formats") or [] if f.get("vcodec") not in (None, "none")]
            return {
                "id": video_id,
                "title": data.get("title") or "",
                "channel": data.get("channel") or data.get("uploader") or "",
                "uploader": data.get("uploader"),
                "license": data.get("license") or "youtube-standard",
                "duration": data.get("duration"),
                "width": data.get("width"),
                "height": data.get("height"),
                "maxHeight": max(heights or [0]),
                "liveStatus": data.get("live_status"),
                "subtitleLangs": sorted(data.get("subtitles") or {}),
                "autoCaptionLangs": sorted(
                    lang for lang in (data.get("automatic_captions") or {}) if lang.split("-")[0] in ("en", "es")
                ),
            }

        return cached_json(self.cache_dir / "videos" / video_id / "info.json", produce)

    def passes_metadata_filters(self, info: dict[str, Any]) -> bool:
        if info.get("maxHeight", 0) < int(self.cfg.get("min_height", 720)):
            return False
        width, height = info.get("width") or 16, info.get("height") or 9
        if height > width:  # vertical = shorts-style footage
            return False
        return bool(info.get("channel"))

    def subtitles(self, info: dict[str, Any]) -> list[tuple[float, float, str]]:
        video_id = info["id"]
        langs = [lang for lang in ("en", "es") if lang in info["subtitleLangs"]] or [
            lang for lang in info["autoCaptionLangs"] if lang in ("en", "es", "en-orig", "es-orig")
        ]
        if not langs:
            return []
        lang = langs[0]
        target_dir = self.cache_dir / "videos" / video_id

        def produce() -> list[list[Any]]:
            options = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": [lang],
                "subtitlesformat": "vtt",
                "outtmpl": str(target_dir / "subs.%(ext)s"),
            }
            self._call(
                "subtitles", lambda: self._ydl(options).download([f"https://www.youtube.com/watch?v={video_id}"]), rate_retries=0
            )
            files = sorted(target_dir.glob("subs*.vtt"))
            if not files:
                return []
            cues = _LegacyParsers._parse_vtt(files[0].read_text(encoding="utf-8-sig", errors="replace"))
            return [[c.start_seconds, c.end_seconds, c.text] for c in cues]

        return [tuple(c) for c in cached_json(target_dir / f"subs.{lang}.json", produce)]  # type: ignore[misc]

    # --- analysis sections ----------------------------------------------------------

    def plan_sections(self, info: dict[str, Any], terms: set[str], entity_terms: set[str]) -> list[tuple[float, float, str]]:
        duration = float(info.get("duration") or 0)
        if duration <= float(self.cfg.get("full_download_max_seconds", 480)):
            return [(0.0, duration, "full")]
        margin = duration * 0.05
        pad = float(self.cfg.get("section_padding", 15))
        max_len = float(self.cfg.get("section_max_seconds", 60))
        max_sections = int(self.cfg.get("max_sections", 3))
        try:
            cues = self.subtitles(info)
        except SourceUnavailable:
            raise
        except Exception:
            cues = []  # no subtitles → sampled windows below
        hits: list[tuple[float, float, float, str]] = []
        for start, end, text in cues:
            words = tokens(text)
            score = len(words & terms) + 2 * len(words & entity_terms)
            if score >= 2 and margin <= start <= duration - margin:
                hits.append((score, start, end, text))
        windows: list[list[Any]] = []
        for _, start, end, text in sorted(hits, key=lambda h: (-h[0], h[1])):
            window = [max(margin, start - pad), min(duration - margin, end + pad), f"subtítulo: {text[:60]}"]
            window[1] = min(window[1], window[0] + max_len)
            if any(w[0] - pad <= window[0] <= w[1] + pad for w in windows):
                continue
            windows.append(window)
            if len(windows) >= max_sections:
                break
        if not windows:
            length = min(max_len / 2, 30.0)
            windows = [
                [max(margin, duration * f - length / 2), min(duration - margin, duration * f + length / 2), "muestreo"]
                for f in (0.25, 0.5, 0.75)
            ][:max_sections]
        return [(round(a, 2), round(b, 2), reason) for a, b, reason in sorted(windows) if b - a >= 3]

    def download_section(self, video_id: str, start: float, end: float) -> Path:
        target_dir = self.cache_dir / "videos" / video_id
        target = target_dir / f"a360_{start:.2f}_{end:.2f}.mp4"
        if target.is_file() and target.stat().st_size > 0:
            return target
        # Reuse any already-downloaded file that covers this range.
        for existing in target_dir.glob("a360_*.mp4"):
            _, a, b = existing.stem.split("_")
            if float(a) <= start and float(b) >= end:
                return existing
        from yt_dlp.utils import download_range_func

        options: dict[str, Any] = {
            "format": "bv*[height<=360][vcodec^=avc1]/bv*[height<=360]/b[height<=360]/wv*",
            "outtmpl": str(target_dir / f"dl_{start:.2f}_{end:.2f}.%(ext)s"),
            "overwrites": True,
            "nopart": True,
        }
        info_duration = self.info(video_id).get("duration") or 0
        is_full = start <= 0.01 and end >= float(info_duration) - 0.5
        if not is_full:
            options["download_ranges"] = download_range_func(None, [(start, end)])
            options["force_keyframes_at_cuts"] = True  # exact timestamps: later stages cut by them
        self._call("download", lambda: self._ydl(options).download([f"https://www.youtube.com/watch?v={video_id}"]))
        produced = [p for p in target_dir.glob(f"dl_{start:.2f}_{end:.2f}*") if p.suffix in (".mp4", ".webm", ".mkv")]
        if not produced:
            raise RuntimeError(f"yt-dlp no produjo el tramo {start}-{end} de {video_id}")
        produced[0].replace(target)
        return target

    # --- per shot ---------------------------------------------------------------------

    def queries_for(self, broll: BrollSpec) -> list[str]:
        return [
            *broll.queries[: int(self.cfg.get("queries_en", 2))],
            *broll.queriesLocal[: int(self.cfg.get("queries_local", 1))],
        ]

    def candidates(self, broll: BrollSpec, notes: list[str]) -> list[Candidate]:
        queries = self.queries_for(broll)
        per_query: list[list[str]] = []
        entries: dict[str, dict[str, Any]] = {}
        for query in queries:
            try:
                results = self.search(query)
            except SourceUnavailable:
                raise
            except RuntimeError as error:
                notes.append(f"youtube búsqueda {query!r}: {error}")
                continue
            ids = []
            for entry in results:
                if self.passes_search_filters(entry):
                    entries.setdefault(entry["id"], {**entry, "query": query})
                    ids.append(entry["id"])
            per_query.append(ids)
        scores = fuse_ranks(per_query)
        entity_terms = tokens(" ".join(broll.entities))
        for video_id, entry in entries.items():
            if entity_terms and entity_terms & tokens(f"{entry.get('title')} {entry.get('channel')}"):
                scores[video_id] = scores.get(video_id, 0.0) + 0.3

        terms = tokens(" ".join([*broll.queries, *broll.queriesLocal, *broll.mustContain]))
        wanted = int(self.cfg.get("videos_per_shot", 4))
        result: list[Candidate] = []
        for video_id in sorted(entries, key=lambda v: -scores.get(v, 0.0)):
            if len(result) >= wanted:
                break
            try:
                info = self.info(video_id)
                if not self.passes_metadata_filters(info):
                    continue
                ranges = []
                for start, end, reason in self.plan_sections(info, terms, entity_terms):
                    path = self.download_section(video_id, start, end)
                    ranges.append(AnalysisRange(path=str(path.relative_to(self.root)), start=start, end=end, reason=reason))
            except SourceUnavailable:
                raise
            except Exception as error:
                notes.append(f"yt:{video_id}: {error}")
                continue
            if not ranges:
                continue
            channel = info["channel"]
            url = f"https://www.youtube.com/watch?v={video_id}"
            result.append(
                Candidate(
                    id=f"yt:{video_id}",
                    source="youtube",
                    kind="video",
                    url=url,
                    title=info["title"],
                    channel=channel,
                    uploader=info.get("uploader"),
                    license=info["license"],
                    credit=f"Fuente: {channel}",
                    attribution=f"{channel} — \"{info['title']}\": {url}",
                    durationSeconds=float(info["duration"]),
                    width=info.get("width"),
                    height=info.get("height"),
                    query=entries[video_id]["query"],
                    rankScore=round(scores.get(video_id, 0.0), 4),
                    analysis=ranges,
                )
            )
        return result


def _parse_rate(value: str) -> int:
    match = re.fullmatch(r"\s*([\d.]+)\s*([kKmM]?)\s*", value)
    if not match:
        raise ValueError(f"youtube.rate_limit inválido: {value!r} (usa p. ej. '2M' o '500K')")
    number = float(match.group(1))
    factor = {"": 1, "k": 1024, "m": 1024 * 1024}[match.group(2).lower()]
    return int(math.floor(number * factor))
