"""Third-party footage from YouTube via yt-dlp (stage 3), storyboard-first.

Per candidate video only two cheap things are fetched here: its metadata (one yt-dlp
call) and its storyboard — the seek-bar thumbnails, ~100 frames of the whole video in a
few hundred KB. Stage 4 scores those thumbnails and only then downloads short 360p
windows around the best moments (`download_section`); stage 6 downloads the chosen
≤5 s fragment in HD. Everything is cached globally in cache/search/youtube/ and
cache/videos/<id>/, so later videos on similar topics reuse the work.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

from ..clients.youtube_client import YouTubeClient as _LegacyParsers
from ..schemas import BrollSpec, Candidate, Storyboard
from .common import USER_AGENT, Pacer, SourceUnavailable, cached_json, fuse_ranks, key, tokens


_BLOCK_MARKERS = ("sign in to confirm", "not a bot")
_RATE_MARKERS = ("http error 429", "too many requests")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class RateLimited(RuntimeError):
    pass


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
        self.pacer = Pacer(float(config.get("min_interval", 1.0)))
        self.blocked: str | None = None
        # A few concurrent requests at most; a 429 pauses every thread (the limit is per account/IP).
        self._slots = threading.Semaphore(int(config.get("concurrency", 3)))
        self._cooldown_until = 0.0
        self._cookies_text = cookies_text
        self._local = threading.local()
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
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

    def _info_path(self, video_id: str) -> Path:
        return self.cache_dir / "videos" / video_id / "info.json"

    def info(self, video_id: str) -> dict[str, Any]:
        path = self._info_path(video_id)
        if path.is_file():
            try:
                import json

                cached = json.loads(path.read_text(encoding="utf-8"))
                if "storyboard" not in cached:  # written by the older, download-first sourcing
                    path.unlink()
            except (OSError, ValueError):
                path.unlink(missing_ok=True)

        def produce() -> dict[str, Any]:
            data = self._call(
                "metadata",
                lambda: self._ydl({"skip_download": True}).extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                ),
            )
            formats = data.get("formats") or []
            heights = [f.get("height") or 0 for f in formats if f.get("vcodec") not in (None, "none")]
            boards = [f for f in formats if str(f.get("format_id", "")).startswith("sb") and f.get("fragments")]
            board = max(boards, key=lambda f: f.get("width") or 0, default=None)
            captions: dict[str, str] = {}
            for field in ("subtitles", "automatic_captions"):  # manual subtitles win
                for lang, tracks in (data.get(field) or {}).items():
                    base = lang.split("-")[0]
                    if base in ("en", "es") and base not in captions:
                        json3 = next((t.get("url") for t in tracks if t.get("ext") == "json3"), None)
                        if json3:
                            captions[base] = json3
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
                "fetchedAt": time.time(),
                "storyboard": None if board is None else {
                    "urls": [frag["url"] for frag in board["fragments"]],
                    "columns": board.get("columns") or 1,
                    "rows": board.get("rows") or 1,
                    "width": board.get("width") or 0,
                    "height": board.get("height") or 0,
                    "fps": board.get("fps") or 0,
                },
                "captions": captions,
            }

        return cached_json(path, produce)

    def passes_metadata_filters(self, info: dict[str, Any]) -> bool:
        if info.get("maxHeight", 0) < int(self.cfg.get("min_height", 720)):
            return False
        width, height = info.get("width") or 16, info.get("height") or 9
        if height > width:  # vertical = shorts-style footage
            return False
        board = info.get("storyboard")
        return bool(info.get("channel")) and bool(board and board.get("fps") and board.get("width"))

    # --- storyboard -----------------------------------------------------------------

    def storyboard(self, info: dict[str, Any]) -> Storyboard:
        video_id = info["id"]
        board = info["storyboard"]
        target_dir = self.cache_dir / "videos" / video_id / "sb"
        paths = [target_dir / f"{index:03d}.jpg" for index in range(len(board["urls"]))]

        def fetch(item: tuple[str, Path]) -> None:
            url, path = item
            response = self.http.get(url, timeout=30)
            response.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)

        missing = [(url, path) for url, path in zip(board["urls"], paths) if not path.is_file()]
        if missing:
            try:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(fetch, missing))
            except requests.HTTPError:
                # Signed thumbnail URLs expire: refresh the metadata once and retry.
                self._info_path(video_id).unlink(missing_ok=True)
                board = self.info(video_id)["storyboard"]
                missing = [(url, path) for url, path in zip(board["urls"], paths) if not path.is_file()]
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(fetch, missing))
        duration = float(info.get("duration") or 0)
        per_sheet = int(board["columns"]) * int(board["rows"])
        frames = min(len(paths) * per_sheet, max(1, int(duration * float(board["fps"])) + 1))
        return Storyboard(
            sheets=[str(p.relative_to(self.root)) for p in paths],
            columns=int(board["columns"]),
            rows=int(board["rows"]),
            tileWidth=int(board["width"]),
            tileHeight=int(board["height"]),
            interval=1.0 / float(board["fps"]),
            frames=frames,
        )

    # --- used by stage 4 ------------------------------------------------------------

    def captions(self, video_id: str) -> list[tuple[float, float, str]]:
        """Subtitle cues (en/es) — best effort: [] when there are none or YouTube refuses."""

        def produce() -> list[list[Any]]:
            info = self.info(video_id)
            url = info.get("captions", {}).get("en") or info.get("captions", {}).get("es")
            if not url:
                return []
            response = self.http.get(url, timeout=30)
            if response.status_code == 429:
                raise RateLimited("subtítulos: 429")
            response.raise_for_status()
            cues = _LegacyParsers._parse_json3(response.text)
            return [[c.start_seconds, c.end_seconds, c.text] for c in cues]

        try:
            cues = cached_json(self.cache_dir / "videos" / video_id / "captions.json", produce)
        except Exception:
            return []
        return [tuple(c) for c in cues]  # type: ignore[misc]

    def download_section(self, video_id: str, start: float, end: float) -> Path:
        """360p (video-only) file covering [start, end] of the source, exact timestamps."""

        target_dir = self.cache_dir / "videos" / video_id
        target = target_dir / f"a360_{start:.2f}_{end:.2f}.mp4"
        if target.is_file() and target.stat().st_size > 0:
            return target
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
            "download_ranges": download_range_func(None, [(start, end)]),
            "force_keyframes_at_cuts": True,  # exact timestamps: later stages cut by them
        }
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

        wanted = int(self.cfg.get("videos_per_shot", 3))
        result: list[Candidate] = []
        for video_id in sorted(entries, key=lambda v: -scores.get(v, 0.0)):
            if len(result) >= wanted:
                break
            try:
                info = self.info(video_id)
                if not self.passes_metadata_filters(info):
                    continue
                board = self.storyboard(info)
            except SourceUnavailable:
                raise
            except Exception as error:
                notes.append(f"yt:{video_id}: {str(error)[:160]}")
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
                    storyboard=board,
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
