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
from .common import USER_AGENT, Pacer, SourceUnavailable, blocked_by_title, cached_json, fuse_ranks, key, tokens


_BLOCK_MARKERS = ("sign in to confirm", "not a bot")
_RATE_MARKERS = ("http error 429", "too many requests")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class RateLimited(RuntimeError):
    pass


# yt-dlp warnings that explain slow or failing downloads: shown once each (the rest stays quiet).
_WARNINGS = (
    (("challenge", "javascript runtime", "js runtime", "n function", "nsig", "ejs"),
     "yt-dlp no puede resolver los retos de YouTube → descargas lentas o formatos que faltan. "
     "Arréglalo con: pip install -U \"yt-dlp[default]\" deno"),
    (("po token", "some formats may be missing", "sabr"), "YouTube esconde formatos a este cliente (PO token/SABR)"),
    (("http error 429", "too many requests"), "YouTube limita peticiones (429): el programa espera y reintenta"),
    (("http error 403", "forbidden"), "YouTube rechaza una descarga (403): se reintenta con enlaces nuevos"),
    (("timed out", "timeout", "retrying"), "descargas que se cortan o tardan en responder (red lenta): se reintentan"),
)
WARNING_COUNTS: dict[str, int] = {}
_warning_lock = threading.Lock()


def hls_format(fmt: str, *, audio: bool = False, audio_only: bool = False) -> str:
    """The same request limited to YouTube's HLS formats (muxed video+audio, served in small segments)."""

    height = re.search(r"height<=(\d+)", fmt)
    limit = f"[height<={height.group(1)}]" if height else ""
    if audio_only:
        return "worst[protocol^=m3u8][acodec!=none]"          # the sound only: the lightest muxed stream
    if audio:
        return f"b{limit}[protocol^=m3u8][acodec!=none][vcodec^=avc1]/b{limit}[protocol^=m3u8][acodec!=none]"
    parts = [alt.split("+")[0] for alt in fmt.split("/") if alt.strip()]
    return "/".join(f"{alt}[protocol^=m3u8]" for alt in dict.fromkeys(parts))


def whole_format(fmt: str) -> str:
    """The same request over plain HTTPS (fetched in 10 MB pieces), video+audio pairs included: YouTube hardly
    offers files with both any more, and dropping the pairs sent every clip with sound to the slow per-range
    path (~4 min each in the cold open)."""

    return "/".join("+".join(f"{part}[protocol=https]" for part in alt.split("+")) for alt in fmt.split("/") if alt.strip())


def _has_hls(info_path: Path) -> bool:
    import json

    try:
        formats = json.loads(info_path.read_text(encoding="utf-8")).get("formats") or []
    except (OSError, ValueError):
        return False
    return any(str(f.get("protocol") or "").startswith("m3u8") for f in formats)


def _upload_filter(days: int) -> str:
    """YouTube's search filter (the `sp` parameter) for videos uploaded in the last hour/day/week/month/year."""

    for limit, code in ((0, "EgQIARAB"), (1, "EgQIAhAB"), (7, "EgQIAxAB"), (31, "EgQIBBAB")):
        if days <= limit:
            return code
    return "EgQIBRAB"


class _QuietLogger:
    """yt-dlp prints errors itself even with quiet=True; we raise and report them instead. Warnings that
    explain slowness are shown once each and counted (WARNING_COUNTS)."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...

    def warning(self, msg: str) -> None:
        lowered = msg.casefold()
        for markers, text in _WARNINGS:
            if any(m in lowered for m in markers):
                with _warning_lock:
                    first = text not in WARNING_COUNTS
                    WARNING_COUNTS[text] = WARNING_COUNTS.get(text, 0) + 1
                if first:
                    print(f"   AVISO yt-dlp: {text}")
                return

    def error(self, msg: str) -> None: ...


class YouTubeSource:
    def __init__(
        self, *, root: Path, cache_dir: Path, config: dict[str, Any], cookies_text: str | None = None,
        cookies_path: Path | None = None, cookie_sets: list[tuple[str, Path | None]] | None = None,
    ) -> None:
        self.root = root
        self.cache_dir = cache_dir
        self.cfg = config
        self.pacer = Pacer(float(config.get("min_interval", 1.0)))
        self.blocked: str | None = None
        # A few concurrent requests at most; a 429 pauses every thread (the limit is per account/IP).
        self._slots = threading.Semaphore(int(config.get("concurrency", 3)))
        self._cooldown_until = 0.0
        # One or more accounts (cookies.txt contents, file they came from). Requests take turns
        # between them; one that YouTube blocks is set aside and the rest carry on.
        self._sets: list[tuple[str, Path | None]] = list(cookie_sets or ([(cookies_text, cookies_path)] if cookies_text else []))
        self._bad: set[int] = set()
        self._turn = 0
        self._turn_lock = threading.Lock()
        self._cookie_copies: dict[int, list[str]] = {}
        self._local = threading.local()
        self.api: Any = None                        # YouTube Data API client (searches) when keys exist
        self._api_lock = threading.Lock()
        self.stats: dict[str, list[float]] = {}   # action → [count, seconds], for tuning
        self._stats_lock = threading.Lock()
        self._whole_locks: dict[str, threading.Lock] = {}
        self._whole_locks_guard = threading.Lock()
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": False,     # warnings go to _QuietLogger: the ones that explain slowness are shown once
            "noprogress": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "retries": 3,
            "logger": _QuietLogger(),
        }
        if shutil.which("deno") is None and shutil.which("node") is not None:
            options["js_runtimes"] = {"node": {}}
        if config.get("force_ipv4"):
            options["source_address"] = "0.0.0.0"   # YouTube over IPv6 crawls with some providers
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

    def _next_account(self) -> int | None:
        """The next account in turn that YouTube has not blocked (None without cookies)."""

        with self._turn_lock:
            good = [i for i in range(len(self._sets)) if i not in self._bad]
            if not good:
                return None
            index = good[self._turn % len(good)]
            self._turn += 1
            return index

    def _account_name(self, index: int) -> str:
        path = self._sets[index][1]
        return path.name if path else f"cuenta {index + 1}"

    def _cookie_file(self) -> str | None:
        """Per-thread private copy of the account in use: yt-dlp saves rotated cookies back into it."""

        index = getattr(self._local, "account", None)
        if index is None or not self._sets:
            return None
        paths = getattr(self._local, "cookie_paths", None)
        if paths is None:
            paths = self._local.cookie_paths = {}
        if index not in paths:
            handle, path = tempfile.mkstemp(prefix="yt-cookies-", suffix=".txt")
            with os.fdopen(handle, "w", encoding="utf-8") as cookie_file:
                cookie_file.write(self._sets[index][0])
            paths[index] = path
            with self._turn_lock:
                self._cookie_copies.setdefault(index, []).append(path)
        return paths[index]

    def close(self) -> None:
        """Persist cookies YouTube rotated during the run (newest private copy of each account) and
        drop the copies. A stale copy makes the next run look like a replayed session."""

        for index, names in self._cookie_copies.items():
            copies = [Path(p) for p in names if Path(p).is_file()]
            text, origin = self._sets[index]
            if copies and origin is not None:
                newest = max(copies, key=lambda p: p.stat().st_mtime).read_text(encoding="utf-8")
                if "youtube.com" in newest and newest != text:
                    tmp = origin.with_name(origin.name + ".tmp")
                    tmp.write_text(newest, encoding="utf-8")
                    os.chmod(tmp, 0o600)
                    tmp.replace(origin)
            for path in copies:
                path.unlink(missing_ok=True)
        self._cookie_copies.clear()

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
        attempt = 0
        while True:
            self._local.account = self._next_account()
            if self._sets and self._local.account is None:
                self._blocked_everywhere()
            try:
                with self._slots:
                    delay = self._cooldown_until - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                        self._count("espera por límite", delay)
                    self.pacer.wait()
                    began = time.monotonic()
                    try:
                        return fn()
                    finally:
                        self._count(action, time.monotonic() - began)
            except Exception as error:
                message = str(error)
                lowered = message.casefold()
                if any(marker in lowered for marker in _BLOCK_MARKERS):
                    index = self._local.account
                    if index is not None:
                        with self._turn_lock:
                            fresh = index not in self._bad
                            self._bad.add(index)
                            left = len(self._sets) - len(self._bad)
                        if fresh:
                            print(f"   YouTube bloqueó {self._account_name(index)}; "
                                  + (f"sigo con las otras {left} cuentas" if left else "no quedan cuentas"))
                        if left:
                            pause = float(self.cfg.get("account_switch_pause", 15))
                            self._cooldown_until = max(self._cooldown_until, time.monotonic() + pause)
                            continue
                    self._blocked_everywhere()
                if any(marker in lowered for marker in _RATE_MARKERS):
                    if attempt < rate_retries:
                        pause = float(self.cfg.get("rate_backoff", 20)) * 3**attempt
                        self._cooldown_until = max(self._cooldown_until, time.monotonic() + pause)
                        attempt += 1
                        continue
                    raise RateLimited(f"yt-dlp {action}: YouTube limita peticiones (429)") from None
                raise RuntimeError(f"yt-dlp {action}: {message[:200]}") from None

    def _blocked_everywhere(self) -> None:
        self.blocked = (
            "YouTube bloquea este equipo (\"Sign in to confirm you're not a bot\")"
            + (f" y las {len(self._sets)} cuentas de cookies" if self._sets else "")
            + ". Añade o renueva cookies en ~/.config/edit-vid3/cookies/ (un .txt por cuenta)."
        )
        raise SourceUnavailable(self.blocked) from None

    def _count(self, action: str, seconds: float) -> None:
        with self._stats_lock:
            entry = self.stats.setdefault(action, [0, 0.0])
            entry[0] += 1
            entry[1] += seconds

    def stats_line(self) -> str:
        return " · ".join(f"{action} {int(n)}× {total / max(n, 1):.1f} s" for action, (n, total) in sorted(self.stats.items()))

    # --- search & metadata ----------------------------------------------------------

    def search(self, query: str) -> list[dict[str, Any]]:
        limit = int(self.cfg.get("results_per_query", 8))
        days = int(self.cfg.get("recent_days", 0) or 0)     # news videos: only footage uploaded lately

        def produce() -> list[dict[str, Any]]:
            found = self._api_search(query, limit, days)
            if found is not None:
                return found
            if days:
                from urllib.parse import quote_plus

                target = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={_upload_filter(days)}"
                extra = {"extract_flat": "in_playlist", "skip_download": True, "playlistend": limit}
            else:
                target = f"ytsearch{limit}:{query}"
                extra = {"extract_flat": "in_playlist", "skip_download": True}
            info = self._call("search", lambda: self._ydl(extra).extract_info(target, download=False))
            keep = ("id", "title", "channel", "uploader", "duration", "url", "live_status", "view_count")
            return [{k: entry.get(k) for k in keep} for entry in (info or {}).get("entries") or [] if isinstance(entry, dict)]

        name = key(query, limit) if not days else f"{key(query, limit, days)}-{time.strftime('%Y%m%d')}"   # recent: one per day
        return cached_json(self.cache_dir / "search" / "youtube" / f"{name}.json", produce)

    def _api_search(self, query: str, limit: int, days: int = 0) -> list[dict[str, Any]] | None:
        """The same entries as a yt-dlp search, from the official API (never bot-checked). None when
        there are no keys or the day's quota ran out: then yt-dlp searches as before."""

        api = self.api
        if api is None:
            return None
        try:
            began = time.monotonic()
            ids = api.search(query, order="relevance", max_results=limit, **({"days": days} if days else {}))
            details = {v["id"]: v for v in api.videos(ids)} if ids else {}
            self._count("search-api", time.monotonic() - began)
        except Exception as error:  # no quota left or the API keeps failing: yt-dlp for the rest of the run
            from ..ytapi import NoKeysLeft

            with self._api_lock:
                self._api_failures = getattr(self, "_api_failures", 0) + 1
                if self.api is not None and (isinstance(error, NoKeysLeft) or self._api_failures >= 3):
                    print(f"   API de YouTube: {str(error)[:120]} → sigo buscando con yt-dlp")
                    self.api = None
            return None                 # just this search goes through yt-dlp
        return [{"id": i, "title": details[i]["title"], "channel": details[i]["channel"],
                 "uploader": details[i]["channel"], "duration": details[i]["duration"],
                 "url": f"https://www.youtube.com/watch?v={i}", "live_status": None,
                 "view_count": details[i]["views"]} for i in ids if i in details]

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
        if blocked_by_title(str(entry.get("title") or ""), str(entry.get("channel") or ""), self.cfg.get("title_blocklist")):
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
            self._save_full_info(video_id, data)
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
        began = time.monotonic()
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
            self._count("storyboard", time.monotonic() - began)
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

    # --- downloads without re-extraction ------------------------------------------------

    def _clients(self) -> list[str]:
        return [str(c) for c in (self.cfg.get("player_client") or [])]

    def _full_info_path(self, video_id: str) -> Path:
        return self.cache_dir / "videos" / video_id / "ytdlp-info.json"

    def _save_full_info(self, video_id: str, data: dict[str, Any]) -> None:
        """yt-dlp's own info dict (minus bulky fields) so downloads can skip the ~4 s extraction."""

        import json

        slim = {k: v for k, v in data.items() if k not in ("automatic_captions", "subtitles", "thumbnails", "heatmap")}
        slim["_edit_vid3_clients"] = self._clients()     # re-extract when the player clients change
        path = self._full_info_path(video_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with self._ydl() as ydl:
            tmp.write_text(json.dumps(ydl.sanitize_info(slim)), encoding="utf-8")
        tmp.replace(path)

    def _fresh_full_info(self, video_id: str) -> Path:
        """Path to a full info JSON whose stream URLs are still valid (re-extracting if needed)."""

        import json

        path = self._full_info_path(video_id)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                formats = data.get("formats") or []
                expiries = [
                    int(found.group(1)) for f in formats if f.get("vcodec") not in (None, "none") and f.get("url")
                    # stream URLs carry ?expire=…, HLS manifests /expire/…/
                    for found in [re.search(r"[/?&]expire[/=](\d+)", f["url"])] if found
                ]
                if expiries and min(expiries) - time.time() > 600 and data.get("_edit_vid3_clients") == self._clients():
                    return path
            except (OSError, ValueError, KeyError):
                pass
        self._info_path(video_id).unlink(missing_ok=True)
        self.info(video_id)  # re-extracts and re-saves the full info
        return path

    def download_range(self, video_id: str, start: float, end: float, *, fmt: str, prefix: str,
                       audio: bool = False, audio_only: bool = False) -> Path:
        """[start, end] of the source → <prefix>_<realStart>_<realEnd>.mp4 (source seconds in the name).

        HLS first (sourcing.youtube.hls_ranges): the range comes as a few small segment requests and is
        cut exactly (re-encoding just those seconds). The HTTPS formats are fetched by ffmpeg as ONE open
        request, which YouTube throttles to a crawl once it is bigger than ~10 MB (yt-dlp issues #17612,
        #15036) — the 70 s per clip at home. HTTPS stays as the fallback, stream-copied: the file then
        begins at the keyframe before `start` and the real start is measured (timestamps kept, -copyts).
        """

        target_dir = self.cache_dir / "videos" / video_id
        suffix = ".m4a" if audio_only else ".mp4"       # audio_only: just the sound of the range (sound bites)
        for existing in target_dir.glob(f"{prefix}_*{suffix}"):
            try:
                _, a, b = existing.stem.split("_")
                if float(a) <= start + 1e-3 and float(b) >= end - 1e-3:
                    return existing
            except ValueError:
                continue
        # Resolve (maybe re-extract) the info *before* taking a connection slot: _fresh_full_info
        # may itself call _call(), and nesting slots deadlocks when all of them are taken.
        info_path = self._fresh_full_info(video_id)
        hls = hls_format(fmt, audio=audio, audio_only=audio_only) if self.cfg.get("hls_ranges", True) else None
        if hls and _has_hls(info_path):
            try:
                return self._fetch_range(video_id, start, end, hls, prefix, audio, audio_only, info_path, exact=True)
            except (RuntimeError, SourceUnavailable) as error:
                if isinstance(error, SourceUnavailable) or "format is not available" not in str(error).lower():
                    raise
        if not audio_only and self.cfg.get("whole_fallback", True):
            try:
                whole = self._fetch_whole(video_id, fmt, prefix, info_path)
            except SourceUnavailable:
                raise
            except Exception as error:     # the old way still works, only slower
                print(f"   yt:{video_id}: descarga completa no disponible ({str(error)[:120]}); voy por tramo")
                whole = None
            if whole is not None:
                return self._cut(whole, video_id, start, end, prefix, audio)
        return self._fetch_range(video_id, start, end, fmt, prefix, audio, audio_only, info_path, exact=False)

    def _fetch_whole(self, video_id: str, fmt: str, prefix: str, info_path: Path) -> Path | None:
        """The whole source, fetched by yt-dlp itself in 10 MB pieces (each one a separate request, which YouTube
        does not throttle like ffmpeg's single open request), kept in the cache for the next clips of the same
        video. None when the video is too long or too big for it (sourcing.youtube.whole_max_minutes/_mb)."""

        import json

        target_dir = self.cache_dir / "videos" / video_id
        done = next(iter(sorted(target_dir.glob(f"full_{prefix}.*"))), None)
        if done is not None and done.suffix in (".mp4", ".mkv", ".webm"):
            return done
        data = json.loads(info_path.read_text(encoding="utf-8"))
        if float(data.get("duration") or 0) > 60 * float(self.cfg.get("whole_max_minutes", 30)):
            return None
        fmt = whole_format(fmt)
        with self._ydl({"format": fmt, "simulate": True, "quiet": True}) as ydl:
            chosen = ydl.process_ie_result(dict(data), download=False)
        pieces = chosen.get("requested_formats") or [chosen]
        if any(str(f.get("protocol") or "").startswith(("m3u8", "http_dash")) for f in pieces):
            return None
        size = sum(float(f.get("filesize") or f.get("filesize_approx") or 0) for f in pieces)
        if size > 1e6 * float(self.cfg.get("whole_max_mb", 600)):
            return None
        with self._whole_locks_guard:
            lock = self._whole_locks.setdefault(video_id, threading.Lock())
        with lock:                                     # two clips of one video: one download
            done = next(iter(sorted(target_dir.glob(f"full_{prefix}.*"))), None)
            if done is not None and done.suffix in (".mp4", ".mkv", ".webm"):
                return done
            target_dir.mkdir(parents=True, exist_ok=True)
            options = {"format": fmt, "outtmpl": str(target_dir / f"wip_{prefix}.%(ext)s"), "overwrites": True,
                       "http_chunk_size": 10 * 1024 * 1024, "merge_output_format": "mp4", "concurrent_fragment_downloads": 1}

            def fetch() -> None:
                with self._ydl(options) as ydl:
                    ydl.download_with_info_file(str(info_path))

            self._call("download (completo)", fetch)
            produced = [p for p in target_dir.glob(f"wip_{prefix}.*") if p.stem == f"wip_{prefix}" and p.suffix in (".mp4", ".mkv", ".webm")]
            if not produced:
                return None
            final = target_dir / f"full_{prefix}{produced[0].suffix}"
            produced[0].replace(final)
            return final

    def _cut(self, whole: Path, video_id: str, start: float, end: float, prefix: str, audio: bool) -> Path:
        """[start, end] of the downloaded source, cut exactly (re-encoding only those seconds)."""

        import subprocess

        target = self.cache_dir / "videos" / video_id / f"{prefix}_{start:.3f}_{end:.3f}.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-i", str(whole),
             "-t", f"{end - start:.3f}", "-map", "0:v:0", *(["-map", "0:a:0?", "-c:a", "aac"] if audio else ["-an"]),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(target)],
            check=True,
        )
        return target

    def _fetch_range(self, video_id: str, start: float, end: float, fmt: str, prefix: str, audio: bool,
                     audio_only: bool, info_path: Path, *, exact: bool) -> Path:
        import json
        import subprocess

        from yt_dlp.utils import download_range_func

        target_dir = self.cache_dir / "videos" / video_id
        suffix = ".m4a" if audio_only else ".mp4"
        stream = "a:0" if audio_only else "v:0"
        raw = target_dir / f"dl_{prefix}_{start:.2f}_{end:.2f}.mp4"
        options: dict[str, Any] = {
            "format": fmt,
            "outtmpl": str(raw.with_suffix(".%(ext)s")),
            "overwrites": True,
            "nopart": True,
            "download_ranges": download_range_func(None, [(start, end)]),
            "force_keyframes_at_cuts": exact,             # exact: the file starts right at `start`
        }
        if not exact:
            options["external_downloader_args"] = {"ffmpeg_o": ["-copyts"]}
        info_file = str(info_path)

        def fetch() -> None:
            with self._ydl(options) as ydl:
                ydl.download_with_info_file(info_file)

        def attempt() -> tuple[Path, dict[str, Any]] | None:
            self._call("download (HLS)" if exact else "download", fetch)
            produced = [p for p in target_dir.glob(f"dl_{prefix}_{start:.2f}_{end:.2f}.*")
                        if p.suffix in (".mp4", ".webm", ".mkv", ".m4a", ".opus", ".weba", ".ts")]
            if not produced:
                return None
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", "stream=start_time:format=duration",
                 "-of", "json", str(produced[0])],
                capture_output=True, text=True,
            )
            try:
                info = json.loads(probe.stdout or "{}")
            except ValueError:
                info = {}
            if probe.returncode != 0 or not info.get("streams") or not (info.get("format") or {}).get("duration"):
                produced[0].unlink(missing_ok=True)          # an empty or broken piece (no picture): not usable
                return None
            return produced[0], info

        got = attempt()
        if got is None:                                       # usually stale stream links: fresh ones, once more
            self._full_info_path(video_id).unlink(missing_ok=True)
            info_file = str(self._fresh_full_info(video_id))
            got = attempt()
        if got is None:
            raise RuntimeError(f"YouTube devolvió un tramo vacío ({start:.1f}-{end:.1f} s de {video_id})")
        produced, info = [got[0]], got[1]
        real_start = start if exact else float(info["streams"][0].get("start_time") or start)
        real_end = real_start + float(info["format"]["duration"])
        target = target_dir / f"{prefix}_{real_start:.3f}_{real_end:.3f}{suffix}"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(produced[0]), "-map", f"0:{stream}",
             *(["-map", "0:a:0?"] if audio and not audio_only else []),
             "-c", "copy", "-avoid_negative_ts", "make_zero", str(target)],
            check=True,
        )
        produced[0].unlink(missing_ok=True)
        return target

    def subtitle_file(self, video_id: str, language: str = "en") -> Path | None:
        """The video's subtitles in `language` as WebVTT (uploaded ones, else YouTube's automatic ones), cached."""

        target_dir = self.cache_dir / "videos" / video_id
        for found in sorted(target_dir.glob(f"subs.{language}*.vtt")):
            return found
        target_dir.mkdir(parents=True, exist_ok=True)
        options = {"skip_download": True, "writesubtitles": True, "writeautomaticsub": True,
                   "subtitleslangs": [language, f"{language}-orig", f"{language}.*"], "subtitlesformat": "vtt",
                   "outtmpl": str(target_dir / "subs.%(ext)s")}
        try:
            info_file = str(self._fresh_full_info(video_id))

            def fetch() -> None:
                with self._ydl(options) as ydl:
                    ydl.download_with_info_file(info_file)

            self._call("captions", fetch)
        except SourceUnavailable:
            raise
        except Exception as error:   # no subtitles: the caller may transcribe the audio instead
            print(f"   yt:{video_id}: sin subtítulos ({str(error)[:80]})")
            return None
        return next(iter(sorted(target_dir.glob(f"subs.{language}*.vtt"))), None)

    def download_section(self, video_id: str, start: float, end: float) -> Path:
        """360p video-only file covering [start, end] (source seconds are in its name)."""

        return self.download_range(
            video_id, start, end,
            fmt="bv*[height<=360][vcodec^=avc1]/bv*[height<=360]/b[height<=360]/wv*",
            prefix="a360",
        )

    # --- per shot ---------------------------------------------------------------------

    def queries_for(self, broll: BrollSpec) -> list[str]:
        queries = [
            *broll.queries[: int(self.cfg.get("queries_en", 2))],
            *broll.queriesLocal[: int(self.cfg.get("queries_local", 1))],
        ]
        if self.api is not None:   # API quota: the event search + one more (~30k units a video instead of ~46k)
            queries = queries[: int(self.cfg.get("api_queries_per_shot", 2))]
        return queries

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
