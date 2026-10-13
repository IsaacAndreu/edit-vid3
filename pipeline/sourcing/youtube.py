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
from .common import (USER_AGENT, HourlyBudget, Pacer, SharedPacer, SourceUnavailable, blocked_by_title, cached_json,
                     fuse_ranks, key, tokens)


_BLOCK_MARKERS = ("not a bot", "confirm you’re not", "confirm you're not")   # not «sign in to confirm your age»
# the video itself needs an account (age, members, private): the only case where cookies.mode=fallback uses one
_AUTH_MARKERS = ("confirm your age", "age-restricted", "age restricted", "inappropriate for some users", "members-only",
                 "join this channel", "private video", "this video is private", "login required", "use --cookies",
                 "sign in to view")


def error_kind(message: str) -> str:
    """What a yt-dlp error means, for the metrics: auth, bot, 403, 429, unavailable or other."""

    low = message.casefold()
    if any(marker in low for marker in _BLOCK_MARKERS):      # first: the bot check also says "use --cookies"
        return "bot"
    if any(marker in low for marker in _AUTH_MARKERS):
        return "auth"
    if "http error 403" in low or "403: forbidden" in low:
        return "403"
    if any(marker in low for marker in _RATE_MARKERS):
        return "429"
    if "video unavailable" in low or "not available" in low:
        return "unavailable"
    return "other"
_RATE_MARKERS = ("http error 429", "too many requests")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def proxy_list(env: str | None, many: Any, one: Any) -> list[str]:
    """The ways out to YouTube: YOUTUBE_PROXY (comma separated) wins; else `proxies` (a list) plus `proxy`."""

    if env and env.strip():
        items: list[Any] = env.split(",")
    else:
        items = [*(many if isinstance(many, (list, tuple)) else [many] if many else []), one]
    return list(dict.fromkeys(str(p).strip() for p in items if p and str(p).strip()))


def pacer_name(proxy: str) -> str:
    """The pace file of a way out: `.ritmo` for the direct one, one per proxy (shared by every process)."""

    import hashlib

    return f".ritmo-{hashlib.sha1(proxy.encode()).hexdigest()[:8]}" if proxy else ".ritmo"


QUARANTINE_SUFFIX = ".cuarentena"
BUDGET_SUFFIX = ".presupuesto"
# What one action costs out of the hourly budget, in HTTP requests to YouTube (estimated: yt-dlp does several per
# operation — the page, the player API, the PO token, the format manifests; a range download fetches many fragments)
REQUEST_UNITS = {"search": 2, "metadata": 4, "captions": 1, "download": 3, "download (HLS)": 3,
                 "download (completo)": 8, "get": 1}
# storyboard thumbnails come from the image CDN (i.ytimg.com), not from YouTube's pages or player: not counted
_FREE_HOSTS = ("ytimg.com",)
LAST_BLOCK = ".ultimo-bloqueo"           # cache/videos/: when YouTube last asked «are you a bot» (recovering())


def quarantine_file(cache_dir: Path, proxy: str) -> Path:
    """When a way out may talk to YouTube again (epoch seconds), shared by every process: the next video and the
    hourly probe of a paused queue respect it too."""

    return cache_dir / "videos" / (pacer_name(proxy) + QUARANTINE_SUFFIX)


def quarantined_until(cache_dir: Path, proxy: str) -> float:
    try:
        return float(quarantine_file(cache_dir, proxy).read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0.0


def all_quarantined(cache_dir: Path, proxies: list[str]) -> bool:
    now = time.time()
    return all(quarantined_until(cache_dir, p) > now for p in (proxies or [""]))


def proxy_reachable(proxy: str, timeout: float = 5.0) -> bool:
    """The proxy program answers on its port (a TCP connection; nothing goes to YouTube). A direct way is always up."""

    import socket
    from urllib.parse import urlsplit

    if not proxy:
        return True
    parts = urlsplit(proxy)
    try:
        with socket.create_connection((parts.hostname or "", parts.port or 80), timeout=timeout):
            return True
    except OSError:
        return False


def _proxy_down(low: str) -> bool:
    return any(m in low for m in ("unable to connect to proxy", "proxyerror", "tunnel connection failed",
                                  "proxy connection", "cannot connect to proxy")) or ("proxy" in low and any(
        m in low for m in ("connection refused", "timed out", "unreachable", "no route to host")))


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
        # Several ways out to YouTube (`proxies`: home, a laptop on mobile data…): each one is its own IP, so each
        # gets its own pace and its own `concurrency`, requests go to the least busy one, and one that stops
        # answering rests a while while the others carry on. One that YouTube asks «are you a bot» goes into
        # quarantine (bot_quarantine_minutes): nothing goes out through it, and what it was refused is never sent
        # through another way. With every way in quarantine, all YouTube stops (the fuse).
        self.proxies = proxy_list(os.environ.get("YOUTUBE_PROXY"), config.get("proxies"), config.get("proxy"))
        interval = float(config.get("min_interval", 1.0))
        self._pacers = [SharedPacer(interval, cache_dir / "videos" / pacer_name(p)) for p in (self.proxies or [""])]
        self.pacer = self._pacers[0]                # all processes, per way out
        self._busy = [0] * len(self._pacers)
        self._resting = [0.0] * len(self._pacers)
        self._quarantine_until = [0.0] * len(self._pacers)    # also in a file per way (quarantine_file)
        # One traffic budget per way out for the whole machine (every process, kept across restarts)
        per_hour = float(config.get("requests_per_hour", 1500) or 0)
        self._budgets = [HourlyBudget(cache_dir / "videos" / (pacer_name(p) + BUDGET_SUFFIX), per_hour)
                         for p in (self.proxies or [""])]
        self._proxy_turn = 0
        self._proxy_lock = threading.Lock()
        self.blocked: str | None = None
        # One or more accounts (cookies.txt contents, file they came from). Requests take turns
        # between them; one that YouTube blocks is set aside and the rest carry on.
        self._sets: list[tuple[str, Path | None]] = list(cookie_sets or ([(cookies_text, cookies_path)] if cookies_text else []))
        # cookies: rotate (every request with an account, by turns: home PC) | fallback (no account; one only
        # when a video needs it: age, members, private) | never. `cookies: false` in the config = fallback.
        mode = config.get("cookies", "rotate")
        self.cookies_mode = "fallback" if mode is False else "rotate" if mode is True else str(mode or "rotate").lower()
        if self.cookies_mode == "never":
            self._sets = []
        # A few concurrent requests at most; a 429 pauses every thread (the limit is per account/IP). With 3+
        # accounts the load is spread, so a couple more (`concurrency_with_accounts`) — back to the plain
        # number for the rest of the run at YouTube's first "too many requests".
        base = int(config.get("concurrency", 3))
        boosted = (int(config.get("concurrency_with_accounts", 5))
                   if len(self._sets) >= 3 and self.cookies_mode == "rotate" else base)
        self.concurrency = max(base, boosted)
        ways = len(self._pacers)
        self._extra_slots = (self.concurrency - base) * ways
        self._slots = threading.Semaphore(self.concurrency * ways)
        # each way never carries more than its own share, also when another one is in quarantine: its load is
        # not moved onto the others
        self._way_slots = [threading.Semaphore(self.concurrency) for _ in range(ways)]
        self._cooldown_until = 0.0
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
        self._sessions = []
        for way in (self.proxies or [""]):
            session = requests.Session()
            session.headers["User-Agent"] = USER_AGENT
            if way:
                session.proxies = {"http": way, "https": way}
            self._sessions.append(session)
        self.http = self._sessions[0]
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
        proxy = self.proxies[0] if self.proxies else ""
        if proxy:                                   # a server whose IP YouTube blocks: out through home (docs/VPS.md 3e)
            options["proxy"] = proxy                # yt-dlp, and ffmpeg via -http_proxy (so an http:// proxy)
        self.proxy = proxy
        if config.get("force_ipv4") and not proxy:
            options["source_address"] = "0.0.0.0"   # YouTube over IPv6 crawls with some providers
        if config.get("player_client"):
            options["extractor_args"] = {"youtube": {"player_client": list(config["player_client"])}}
        if config.get("cookies_from_browser"):
            options["cookiesfrombrowser"] = (str(config["cookies_from_browser"]),)
        if config.get("rate_limit"):
            options["ratelimit"] = _parse_rate(str(config["rate_limit"]))
        if config.get("sleep_requests"):
            options["sleep_interval_requests"] = float(config["sleep_requests"])
        self.pot = self._po_tokens(options)
        self.base_options = options
        self.clients = list((options.get("extractor_args") or {}).get("youtube", {}).get("player_client") or ["default"])
        self.metrics_path: Path | None = None       # work/<slug>/youtube_downloads.jsonl (set by youtube_source)
        self.stage = ""
        self._metrics_lock = threading.Lock()

    def _po_tokens(self, options: dict[str, Any]) -> bool:
        """PO Token Provider (bgutil-ytdlp-pot-provider: the yt-dlp plugin + its small server, see docs/VPS.md)
        with the mweb client, as yt-dlp's PO Token guide recommends for servers. `po_token: auto` (default) uses it
        when the plugin is installed and the server answers; `on` warns when it cannot; `off` never."""

        import importlib.util

        mode = str(self.cfg.get("po_token", "auto")).lower()
        if mode in ("off", "false", "no"):
            return False
        if self.proxy and mode != "force":       # through home: YouTube sees the home IP, which needs no PO Token
            return False                         # (and the provider would make it here, for the server's IP)
        url = str(self.cfg.get("pot_provider_url", "http://127.0.0.1:4416")).rstrip("/")
        try:
            plugin = importlib.util.find_spec("yt_dlp_plugins.extractor.getpot_bgutil_http") is not None
        except (ImportError, ValueError):
            plugin = False
        server = False
        if plugin:
            try:
                with requests.Session() as local:
                    local.trust_env = False             # the provider runs on this machine: never via a proxy
                    server = local.get(f"{url}/ping", timeout=3).ok
            except requests.RequestException:
                server = False
        if not (plugin and server):
            if mode in ("on", "true", "yes"):
                print(f"   AVISO PO Token: {'falta el plugin bgutil-ytdlp-pot-provider' if not plugin else 'el servidor no responde en ' + url}"
                      " (docs/VPS.md); sigo sin PO Token")
            return False
        args = options.setdefault("extractor_args", {})
        youtube = args.setdefault("youtube", {})
        clients = list(youtube.get("player_client") or ["default"])
        if "mweb" not in clients and not self.cfg.get("pot_keep_clients"):
            clients.append("mweb")
        youtube["player_client"] = clients
        args["youtubepot-bgutilhttp"] = {"base_url": [url]}
        return True

    def _metric(self, action: str, *, ok: bool, seconds: float, error: str = "", attempt: int = 0,
                cookies: bool = False, size: int | None = None) -> None:
        """One line per request to YouTube in work/<slug>/youtube_downloads.jsonl: what was asked, how it went,
        with or without an account, client and PO Token (python main.py --youtube-stats sums them up)."""

        if self.metrics_path is None:
            return
        import json

        row: dict[str, Any] = {"ts": round(time.time(), 1), "stage": self.stage, "action": action,
                               "video": getattr(self._local, "video_id", None), "ok": ok, "error": error,
                               "attempt": attempt, "cookies": cookies, "clients": self.clients, "pot": self.pot,
                               "seconds": round(seconds, 2), "wait": round(getattr(self._local, "waited", 0.0), 2)}
        if len(self.proxies) > 1:
            row["proxy"] = self.way_name(getattr(self._local, "way", 0) or 0)
        if size is not None:
            row["bytes"] = size
            row["mbps"] = round(size / 1e6 / max(seconds, 0.01), 2)
        with self._metrics_lock:
            self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with self.metrics_path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(row) + "\n")

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

    def _extract(self, url: str, extra: dict[str, Any]) -> Any:
        """extract_info with the YoutubeDL closed afterwards: an open one keeps its connections (and cookie file),
        and a few hundred of them in the analysis stage ran the process out of files («Too many open files»)."""

        ydl = self._ydl(extra)
        try:
            return ydl.extract_info(url, download=False)
        finally:
            close = getattr(ydl, "close", None)
            if close:
                close()

    def _ydl(self, extra: dict[str, Any] | None = None) -> Any:
        import yt_dlp

        options = {**self.base_options, **(extra or {})}
        if len(self.proxies) > 1:
            options["proxy"] = self.proxies[getattr(self._local, "way", 0) or 0]
        cookie_file = self._cookie_file()
        if cookie_file:
            options["cookiefile"] = cookie_file
        return yt_dlp.YoutubeDL(options)

    def _calm_down(self) -> None:
        """Back to `concurrency` requests at a time: the extra slots are taken and never given back."""

        with self._turn_lock:
            extra, self._extra_slots = self._extra_slots, 0
        if extra:
            print(f"   YouTube pide calma: vuelvo a {self.concurrency * len(self._pacers) - extra} descargas a la vez")
            threading.Thread(target=lambda: [self._slots.acquire() for _ in range(extra)], daemon=True).start()

    def _call(self, action: str, fn: Any, *, rate_retries: int = 2) -> Any:
        if self.blocked:
            raise SourceUnavailable(self.blocked)
        attempt = 0
        tries = 0
        with_account = self.cookies_mode == "rotate"
        tried_ways: set[int] = set()
        while True:
            if self._all_in_quarantine():
                self._blocked_everywhere()
            self._local.account = self._next_account() if with_account else None
            if with_account and self._sets and self._local.account is None:
                self._blocked_everywhere()
            tries += 1
            began = queued = time.monotonic()
            self._local.waited = 0.0
            try:
                with self._slots:
                    way = self._local.way = self._pick_way(tried_ways)
                    with self._proxy_lock:
                        self._busy[way] += 1
                    self._way_slots[way].acquire()
                    try:
                        delay = self._cooldown_until - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                            self._count("espera por límite", delay)
                        self._pacers[way].wait()
                        held = self._budget_take(way, REQUEST_UNITS.get(action, 2))
                        if held:
                            self._count("espera por presupuesto/hora", held)
                        began = time.monotonic()
                        self._local.waited = began - queued     # our own queue (slots + 1 req/s), not YouTube
                        try:
                            result = fn()
                        finally:
                            self._count(action, time.monotonic() - began)
                    finally:
                        self._way_slots[way].release()
                        with self._proxy_lock:
                            self._busy[way] -= 1
                self._metric(action, ok=True, seconds=time.monotonic() - began, attempt=tries,
                             cookies=self._local.account is not None)
                return result
            except Exception as error:
                message = str(error)
                lowered = message.casefold()
                kind = error_kind(message)
                self._metric(action, ok=False, seconds=time.monotonic() - began, error=kind, attempt=tries,
                             cookies=self._local.account is not None)
                way = getattr(self._local, "way", 0) or 0
                # A request that hangs until it times out: is it YouTube being slow, or the proxy program stopped
                # (home PC asleep, proxy window closed)? One look at its port says which.
                if self.proxies and kind == "other" and ("timed out" in lowered or "timeout" in lowered) \
                        and not proxy_reachable(self.proxies[way]):
                    lowered += " proxy connection refused"
                if self.proxies and _proxy_down(lowered) and len(tried_ways) >= len(self.proxies) - 1:
                    from ..budget import ProxyDown

                    raise ProxyDown(f"El proxy {self.way_name(way)} no responde: ¿está abierto proxy-youtube en ese PC "
                                    "y conectado Tailscale? El vídeo se reintenta solo en 15 min") from None
                if len(self.proxies) > 1 and len(tried_ways) < len(self.proxies) - 1:
                    if _proxy_down(lowered):         # that way out is off (laptop asleep…): the others, and it rests
                        self._rest(way, float(self.cfg.get("proxy_rest_minutes", 10)) * 60, "no responde")
                        tried_ways.add(way)
                        continue
                if kind == "auth" and self.cookies_mode == "fallback" and self._sets and not with_account:
                    with_account = True          # this video needs an account: try it once with one
                    continue
                if (kind == "bot" and self.cookies_mode == "fallback" and self._sets and not with_account
                        and self.cfg.get("cookies_on_bot", False)):       # off by default: an account is no way round it
                    with_account = True          # this IP gets the bot check (a server's): the request again with an account
                    continue
                if kind == "auth":
                    raise RuntimeError(f"yt-dlp {action}: el vídeo necesita una cuenta ({message[:160]})") from None
                if kind == "bot" and self._local.account is None:
                    # Some videos ask «are you a bot» to everyone (XKOukqWTbKs, Big Buck Bunny: refused by hand too
                    # while other videos passed on the same connection): that video is dropped, never retried another
                    # way or with an account. The same answer for `bot_breaker_videos` (3) different videos within
                    # `bot_breaker_minutes` (10), or for a search, is the connection: quarantine; all of them: stop.
                    video = getattr(self._local, "video_id", None) if action != "search" else None
                    if video is None or self._bot_strikes(way, video) >= int(self.cfg.get("bot_breaker_videos", 3)):
                        self._quarantine(way)
                        if self._all_in_quarantine():
                            self._blocked_everywhere()
                        raise RuntimeError(f"yt-dlp {action}: YouTube pide «no eres un bot»; esa conexión queda en "
                                           "cuarentena y esta petición se descarta") from None
                    self._refuse(video)
                    print(f"   YouTube pide «no eres un bot» para el vídeo {video}: se descarta ese vídeo y sigo")
                    raise RuntimeError(f"yt-dlp {action}: YouTube pide «no eres un bot» para este vídeo; se descarta") from None
                if any(marker in lowered for marker in _BLOCK_MARKERS):
                    index = self._local.account
                    video = getattr(self._local, "video_id", None) if action != "search" else None
                    if index is not None and kind == "bot" and video is not None and \
                            self._bot_strikes(way, video) < int(self.cfg.get("bot_breaker_videos", 3)):
                        # the same as without an account: some videos ask everyone, even a signed-in one (pati12:
                        # 56 of 59 passed with the account, 3 videos did not). That video is dropped; the account is
                        # only taken as blocked when several different videos are refused within a few minutes.
                        self._refuse(video)
                        print(f"   YouTube pide «no eres un bot» para el vídeo {video} también con cuenta: "
                              "se descarta ese vídeo y sigo")
                        raise RuntimeError(f"yt-dlp {action}: YouTube pide «no eres un bot» para este vídeo; "
                                           "se descarta") from None
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
                    # «too many requests» is YouTube's other «stop»: the same quarantine as a bot check, no retry
                    self._quarantine(way, "YouTube responde 429 (demasiadas peticiones)")
                    if self._all_in_quarantine():
                        self._blocked_everywhere()
                    raise RateLimited(f"yt-dlp {action}: YouTube limita peticiones (429); esa conexión queda en "
                                      "cuarentena") from None
                raise RuntimeError(f"yt-dlp {action}: {message[:200]}") from None

    def way_name(self, way: int) -> str:
        from urllib.parse import urlsplit

        return (urlsplit(self.proxies[way]).hostname or self.proxies[way]) if self.proxies else "directo"

    def _refused_path(self) -> Path:
        return self.cache_dir / "videos" / ".rechazados.json"

    def _refuse(self, video: str) -> None:
        """A video that asked «are you a bot»: never asked for again for refused_days (7), by any shot or process."""

        import json

        with self._turn_lock:
            try:
                data = json.loads(self._refused_path().read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            data[video] = time.time()
            try:
                self._refused_path().parent.mkdir(parents=True, exist_ok=True)
                self._refused_path().write_text(json.dumps(data), encoding="utf-8")
            except OSError:
                pass
            self._refused_cache = data

    def refused(self, video: str) -> bool:
        import json

        data = getattr(self, "_refused_cache", None)
        if data is None:
            try:
                data = json.loads(self._refused_path().read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            self._refused_cache = data
        when = data.get(video)
        return when is not None and time.time() - float(when) < 86400 * float(self.cfg.get("refused_days", 7))

    def _bot_strikes(self, way: int, video: str) -> int:
        """Different videos refused with «are you a bot» on that way within bot_breaker_minutes, this one included;
        kept in a file per way (every process, across restarts)."""

        import json

        window = 60 * float(self.cfg.get("bot_breaker_minutes", 10))
        path = self.cache_dir / "videos" / (pacer_name((self.proxies or [""])[way]) + ".bots")
        now = time.time()
        with self._turn_lock:
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                rows = []
            rows = [r for r in rows if now - float(r[0]) < window] + [[now, video]]
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(rows), encoding="utf-8")
            except OSError:
                pass
        return len({r[1] for r in rows})

    def _budget_take(self, way: int, units: float) -> float:
        """The hourly budget of that way out; says so (once a while) when the hour is full and requests wait."""

        budget = self._budgets[way]
        if budget._per_hour and budget.used() + units > budget._per_hour:
            now = time.monotonic()
            if now - getattr(self, "_budget_said", 0.0) > 300:
                self._budget_said = now
                print(f"   Límite de {budget._per_hour:.0f} peticiones/hora a YouTube alcanzado en {self.way_name(way)}: "
                      "espero a que pase la hora (requests_per_hour en config.local.yaml)")
        return budget.take(units)

    def _quarantine(self, way: int, why: str = "YouTube pide «no eres un bot»") -> None:
        minutes = float(self.cfg.get("bot_quarantine_minutes", 120))
        proxy = (self.proxies or [""])[way]
        fresh = not self._in_quarantine(way)
        until = time.time() + minutes * 60
        with self._proxy_lock:
            self._quarantine_until[way] = max(self._quarantine_until[way], until)
        try:
            path = quarantine_file(self.cache_dir, proxy)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{until:.0f}", encoding="utf-8")
        except OSError:
            pass
        self._remember_block()
        if fresh:
            print(f"   {why} a {self.way_name(way)}: cuarentena de {minutes:.0f} min; "
                  "lo que se le negó no se pide por otra conexión")

    def _in_quarantine(self, way: int) -> bool:
        until = max(self._quarantine_until[way], quarantined_until(self.cache_dir, (self.proxies or [""])[way]))
        return until > time.time()

    def _all_in_quarantine(self) -> bool:
        return all(self._in_quarantine(w) for w in range(len(self._pacers)))

    def _pick_way(self, avoid: set[int] = frozenset()) -> int:
        """The way out for the next request: the least busy one that is not resting (by turns on a tie); one in
        quarantine never."""

        if len(self._pacers) == 1:
            return 0
        now = time.monotonic()
        healthy = [w for w in range(len(self._pacers)) if not self._in_quarantine(w)] or list(range(len(self._pacers)))
        with self._proxy_lock:
            ways = [w for w in healthy if w not in avoid] or healthy
            awake = [w for w in ways if self._resting[w] <= now]
            if not awake:                            # all resting: the one that wakes first
                return min(ways, key=lambda w: self._resting[w])
            self._proxy_turn += 1
            return min(awake, key=lambda w: (self._busy[w], (w - self._proxy_turn) % len(self._pacers)))

    def _rest(self, way: int, seconds: float, why: str) -> None:
        with self._proxy_lock:
            fresh = self._resting[way] <= time.monotonic()
            self._resting[way] = max(self._resting[way], time.monotonic() + seconds)
        if fresh:
            print(f"   Proxy {self.way_name(way)}: {why}; descansa {seconds / 60:.0f} min y sigo por los otros")

    def _get(self, url: str, timeout: float = 30) -> requests.Response:
        """A plain HTTP GET (storyboards, captions) through the least busy way out."""

        if self.blocked or self._all_in_quarantine():
            raise SourceUnavailable(self.blocked or "YouTube: todas las conexiones en cuarentena")
        way = self._pick_way()
        if not any(host in url for host in _FREE_HOSTS):
            self._budget_take(way, REQUEST_UNITS["get"])
        try:
            return self._sessions[way].get(url, timeout=timeout)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            if len(self._sessions) == 1:
                raise
            self._rest(way, float(self.cfg.get("proxy_rest_minutes", 10)) * 60, "no responde")
            return self._sessions[self._pick_way({way})].get(url, timeout=timeout)

    def _blocked_everywhere(self) -> None:
        self._remember_block()
        if self.cookies_mode == "rotate" and self._sets:     # every request had an account: they are what failed
            self.blocked = (f"YouTube bloquea este equipo y las {len(self._sets)} cuentas de cookies (\"Sign in to confirm "
                            "you're not a bot\"). Renueva las cookies en ~/.config/edit-vid3/cookies/.")
        else:                 # the connections: no account was tried, and renewing cookies is no answer to this
            self.blocked = ("YouTube bloquea este equipo (\"Sign in to confirm you're not a bot\"): todas las conexiones en "
                            "cuarentena. No se usan cuentas para saltarlo: la cola se pausa y espera.")
        raise SourceUnavailable(self.blocked) from None

    def _remember_block(self) -> None:
        try:
            path = self.cache_dir / "videos" / LAST_BLOCK
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{time.time():.0f}", encoding="utf-8")
        except OSError:
            pass

    def recovering(self) -> bool:
        """Within `bot_recovery_hours` (72) of the last «are you a bot»: searches go only through the API. With no
        API search left, the video waits for the quota instead of searching with yt-dlp on a connection that YouTube
        has just flagged (details and downloads still need yt-dlp once the queue is running again)."""

        hours = float(self.cfg.get("bot_recovery_hours", 72) or 0)
        try:
            last = float((self.cache_dir / "videos" / LAST_BLOCK).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        return hours > 0 and time.time() - last < hours * 3600

    def _no_search_now(self, why: str) -> None:
        from ..budget import ApiSearchesShort
        from ..ytapi import next_reset, reset_text

        raise ApiSearchesShort(f"{why}; este vídeo espera a la cuota nueva de la API, {reset_text()}, en vez de buscar "
                               "con yt-dlp", next_reset().timestamp())

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
            if getattr(self, "api_exhausted", False) and \
                    str(self.cfg.get("api_overflow", "esperar")).lower() == "esperar":   # keys, but no quota left
                self._no_search_now("La API de YouTube no tiene búsquedas hoy en ninguna clave")
            if self.recovering():         # YouTube flagged this connection lately: no yt-dlp searches on it
                self._no_search_now("YouTube pidió «no eres un bot» hace menos de "
                                    f"{float(self.cfg.get('bot_recovery_hours', 72)):.0f} h y la API no tiene búsquedas")
            if days:
                from urllib.parse import quote_plus

                target = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={_upload_filter(days)}"
                extra = {"extract_flat": "in_playlist", "skip_download": True, "playlistend": limit}
            else:
                target = f"ytsearch{limit}:{query}"
                extra = {"extract_flat": "in_playlist", "skip_download": True}
            info = self._call("search", lambda: self._extract(target, extra))
            keep = ("id", "title", "channel", "uploader", "duration", "url", "live_status", "view_count")
            return [{k: entry.get(k) for k in keep} for entry in (info or {}).get("entries") or [] if isinstance(entry, dict)]

        name = key(query, limit) if not days else f"{key(query, limit, days)}-{time.strftime('%Y%m%d')}"   # recent: one per day
        return cached_json(self.cache_dir / "search" / "youtube" / f"{name}.json", produce)

    def search_cached(self, query: str) -> bool:
        """This search's answer is already on disk (search() would not ask anyone)."""

        limit = int(self.cfg.get("results_per_query", 8))
        days = int(self.cfg.get("recent_days", 0) or 0)
        name = key(query, limit) if not days else f"{key(query, limit, days)}-{time.strftime('%Y%m%d')}"
        return (self.cache_dir / "search" / "youtube" / f"{name}.json").is_file()

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
            from ..ytapi import NoKeysLeft, next_reset, reset_text

            strict = str(self.cfg.get("api_overflow", "esperar")).lower() == "esperar"
            if isinstance(error, NoKeysLeft) and (strict or self.recovering()):
                from ..budget import ApiSearchesShort

                raise ApiSearchesShort(f"La API de YouTube no tiene más búsquedas hoy ({error}); este vídeo espera "
                                       f"a la cuota nueva, {reset_text()}, en vez de seguir con yt-dlp",
                                       next_reset().timestamp()) from None
            if strict:                    # an API error is that search's error, never a reason to scrape instead
                raise RuntimeError(f"API de YouTube: {str(error)[:160]}") from None
            with self._api_lock:
                self._api_failures = getattr(self, "_api_failures", 0) + 1
                if self.api is not None and (isinstance(error, NoKeysLeft) or self._api_failures >= 3):
                    print(f"   API de YouTube: {str(error)[:120]} → sigo buscando con yt-dlp")
                    self.api = None
            return None                 # just this search goes through yt-dlp
        return [{"id": i, "title": details[i]["title"], "channel": details[i]["channel"],
                 "uploader": details[i]["channel"], "duration": details[i]["duration"],
                 "url": f"https://www.youtube.com/watch?v={i}",
                 "live_status": "is_live" if details[i].get("live") == "live" else
                                "is_upcoming" if details[i].get("live") == "upcoming" else None,
                 "definition": details[i].get("definition"),
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
        if entry.get("definition") == "sd" and int(self.cfg.get("min_height", 720)) >= 720:
            return False        # the API already says it is under 720p: no need to ask yt-dlp for its details
        return "/shorts/" not in str(entry.get("url") or "")

    def _info_path(self, video_id: str) -> Path:
        return self.cache_dir / "videos" / video_id / "info.json"

    def info(self, video_id: str) -> dict[str, Any]:
        self._local.video_id = video_id
        if self.refused(video_id) and not self._info_path(video_id).is_file():
            raise RuntimeError(f"{video_id}: descartado (pidió «no eres un bot»); no se vuelve a pedir")
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
                lambda: self._extract(f"https://www.youtube.com/watch?v={video_id}", {"skip_download": True}),
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
            response = self._get(url, timeout=30)
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
            response = self._get(url, timeout=30)
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
        """See _download_range; also records the file's size and speed in the metrics."""

        self._local.video_id = video_id
        began = time.monotonic()
        before = getattr(self._local, "fetched", 0)
        try:
            path = self._download_range(video_id, start, end, fmt=fmt, prefix=prefix, audio=audio, audio_only=audio_only)
        except Exception as error:
            self._metric(f"archivo {prefix}", ok=False, seconds=time.monotonic() - began, error=error_kind(str(error)))
            raise
        if getattr(self._local, "fetched", 0) != before:      # downloaded now, not taken from the cache
            size = path.stat().st_size if path.is_file() else 0
            self._metric(f"archivo {prefix}", ok=True, seconds=time.monotonic() - began, size=size)
        return path

    def _download_range(self, video_id: str, start: float, end: float, *, fmt: str, prefix: str,
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
        self._local.fetched = getattr(self._local, "fetched", 0) + 1     # not in the cache: a real download
        # Resolve (maybe re-extract) the info *before* taking a connection slot: _fresh_full_info
        # may itself call _call(), and nesting slots deadlocks when all of them are taken.
        whole = next((p for p in sorted(target_dir.glob(f"full_{prefix}.*")) if p.suffix in (".mp4", ".mkv", ".webm")), None)
        if whole is not None and not audio_only:          # already downloaded whole (prefetch_sections)
            return self._cut(whole, video_id, start, end, prefix, audio)
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

        self._local.video_id = video_id
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

    SECTION_FORMAT = "bv*[height<=360][vcodec^=avc1]/bv*[height<=360]/b[height<=360]/wv*"

    def download_section(self, video_id: str, start: float, end: float) -> Path:
        """360p video-only file covering [start, end] (source seconds are in its name)."""

        return self.download_range(video_id, start, end, fmt=self.SECTION_FORMAT, prefix="a360")

    def prefetch_sections(self, video_id: str) -> bool:
        """The whole video at 360p (a few MB), when several windows of it will be analysed: one download instead
        of one request per window; download_section then cuts them from it. False when it was not possible."""

        try:
            return self._fetch_whole(video_id, self.SECTION_FORMAT, "a360", self._fresh_full_info(video_id)) is not None
        except SourceUnavailable:
            raise
        except Exception:
            return False

    # --- per shot ---------------------------------------------------------------------

    def queries_for(self, broll: BrollSpec) -> list[str]:
        queries = [
            *broll.queries[: int(self.cfg.get("queries_en", 2))],
            *broll.queriesLocal[: int(self.cfg.get("queries_local", 1))],
        ]
        if self.api is not None:   # API quota: the event search + one more (~30k units a video instead of ~46k)
            queries = queries[: int(self.cfg.get("api_queries_per_shot", 2))]
        return queries

    def search_pool(self, queries: list[str], notes: list[str]) -> tuple[list[list[str]], dict[str, dict[str, Any]]]:
        """Every query's results that pass the search filters: (ids per query, entry per id)."""

        per_query: list[list[str]] = []
        entries: dict[str, dict[str, Any]] = {}
        from ..budget import BudgetReached

        for query in queries:
            try:
                results = self.search(query)
            except (SourceUnavailable, BudgetReached):
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
        return per_query, entries

    def candidate(self, video_id: str, entry: dict[str, Any], score: float, notes: list[str]) -> Candidate | None:
        """The video's details (one extraction, cached) → a Candidate, or None when it fails the filters."""

        try:
            info = self.info(video_id)
            if not self.passes_metadata_filters(info):
                return None
            board = self.storyboard(info)
        except SourceUnavailable:
            raise
        except Exception as error:
            notes.append(f"yt:{video_id}: {str(error)[:160]}")
            return None
        channel = info["channel"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        return Candidate(
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
            query=entry["query"],
            rankScore=round(score, 4),
            storyboard=board,
        )

    def candidates(self, broll: BrollSpec, notes: list[str], max_queries: int | None = None) -> list[Candidate]:
        queries = self.queries_for(broll)[:max_queries] if max_queries else self.queries_for(broll)
        per_query, entries = self.search_pool(queries, notes)
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
            found = self.candidate(video_id, entries[video_id], scores.get(video_id, 0.0), notes)
            if found is not None:
                result.append(found)
        return result


def _parse_rate(value: str) -> int:
    match = re.fullmatch(r"\s*([\d.]+)\s*([kKmM]?)\s*", value)
    if not match:
        raise ValueError(f"youtube.rate_limit inválido: {value!r} (usa p. ej. '2M' o '500K')")
    number = float(match.group(1))
    factor = {"": 1, "k": 1024, "m": 1024 * 1024}[match.group(2).lower()]
    return int(math.floor(number * factor))
