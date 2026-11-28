"""Third-party footage from YouTube via yt-dlp (stage 3), storyboard-first.

Per candidate video only two cheap things are fetched here: its metadata (one yt-dlp
call) and its storyboard — the seek-bar thumbnails, ~100 frames of the whole video in a
few hundred KB. Stage 4 scores those thumbnails and only then downloads short 360p
windows around the best moments (`download_section`); stage 6 downloads the chosen
≤5 s fragment in HD. Everything is cached globally in cache/search/youtube/ and
cache/videos/<id>/, so later videos on similar topics reuse the work.
"""

from __future__ import annotations

import contextlib
import json
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
from ..fileio import (atomic_write_text, clean_parts, file_lock, media_problem, part_for, publish, read_json,
                      update_json)
from .common import (USER_AGENT, HourlyBudget, Pacer, ProcessSlots, SharedPacer, SourceUnavailable, blocked_by_title, cached_json,
                     fuse_ranks, key, tokens)
from .byteranges import NoIndex, Plan, needed_head, plan
from .byteranges import pieces as byte_pieces
from .proxy_sessions import SESSION_SUFFIX, ProxySessions, is_residential, with_sticky_session


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
    if "video unavailable" in low or "not available" in low or "with a vpn or proxy" in low \
            or "available in your country" in low:
        return "unavailable"
    if "timed out" in low or "timeout" in low:
        return "timeout"
    return "other"
_RATE_MARKERS = ("http error 429", "too many requests")
# the video itself is gone for everyone (never «Requested format is not available», which is our request)
_GONE_MARKERS = ("video unavailable. this video has been removed", "this video has been removed",
                 "this video is no longer available", "account associated with this video has been terminated",
                 "this video is private", "private video. sign in", "video unavailable. this video is not available",
                 "this live event has ended", "this video has been removed by the uploader")

# What a failure was, finer than error_kind (which drives the retry logic and stays as it was): the request log keeps
# it as «cause», so «otros» — 1/3 of every failure on 17-11, most rows without a word — can be told apart.
_CAUSES = (
    # descargas-rango-fallo.md: 884 range failures and 1 376 whole-over-cap discards counted as «other»
    ("rango-sin-indice", ("faltan moov o sidx", "sin sidx", "sidx vacío", "sidx jerárquico", "cajas inesperadas",
                          "índice demasiado grande", "webm (matroska)", "sin formato mp4 por https",
                          "no atiende peticiones range")),
    ("sin-hls-tope", ("entero supera el tope",)),
    ("proxy-túnel", ("unable to connect to proxy", "tunnel connection failed")),
    ("proxy-407", ("407", "proxy authentication required")),
    ("proxy-sin-respuesta", ("no responde", "proxy connection refused", "connection refused", "proxyerror")),
    ("formato-no-disponible", ("requested format is not available", "no hls stream")),
    ("tramo-vacío", ("tramo vacío", "empty media playlist", "no segment covers", "salió incompleto")),
    ("ffmpeg", ("ffmpeg", "corte local", "remux")),
    ("conexión-cortada", ("connection reset", "connection aborted", "remote end closed", "broken pipe",
                          "incompleteread", "connection broken", "eof occurred")),
    ("http-5xx", ("http error 500", "http error 502", "http error 503", "http error 504", " 502 ", " 503 ")),
    ("http-404", ("http error 404", "http error 410")),
    ("plazo", ("se corta", "tardó más de")),
    ("dns", ("name or service not known", "temporary failure in name resolution", "getaddrinfo")),
    ("yt-dlp-roto", ("nonetype", "keyerror", "typeerror", "indexerror", "attributeerror", "expected str instance")),
)


ONCE_PER_VIDEO = ("sin-hls-tope", "rango-sin-indice")     # causes logged once per video and process


def range_diagnosis(piece: dict[str, Any], status: int | None, content_type: str | None, head: bytes) -> str:
    """What a byte-range attempt got, in one line: the format chosen (itag, ext, codec, container, protocol), the
    answer (HTTP code and Content-Type) and its first 16 bytes in hex. On 22-11 every range came back starting with
    what looks like a Matroska header (1A 45 DF A3 …) although an mp4 was asked for: this says why."""

    return (f"itag {piece.get('format_id')} ext {piece.get('ext')} vcodec {piece.get('vcodec')} "
            f"container {piece.get('container')} protocol {piece.get('protocol')} · HTTP {status} "
            f"{content_type or '-'} · {head[:16].hex(' ')}")


EBML_MAGIC = b"\x1a\x45\xdf\xa3"         # Matroska / WebM

# what an extraction saves of its OWN format pick (bestvideo+bestaudio) next to the list of formats: left in the
# details, yt-dlp hands that pick back whatever is asked. sonda_rango 22-11: «HLS» or «mp4 avc1» came back as AV1 4K
# (701) + opus webm (251), so HLS looked unavailable (4 HLS downloads in a day, 2 134 «ningún formato HLS encaja»),
# the whole file looked too big (479 «entero supera el tope») and every byte range read AV1 then failed on the webm
STALE_PICK = ("requested_formats", "requested_downloads", "format_id", "format", "format_note", "url", "manifest_url",
              "ext", "protocol", "vcodec", "acodec", "http_headers", "filesize", "filesize_approx", "width", "height",
              "fps", "tbr", "vbr", "abr", "resolution", "dynamic_range", "container")


# a passing failure of the connection or of the proxy's tunnel: the same request again usually works
TRANSIENT_ERRORS = (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.Timeout)
TRANSIENT_STATUS = (500, 502, 503, 504)


def selectable(data: dict[str, Any]) -> dict[str, Any]:
    """The saved details without the extraction's own pick: a format request chooses from `formats` again."""

    return {k: v for k, v in data.items() if k not in STALE_PICK}


def error_cause(message: str) -> str:
    """The cause of a failure for the request log: error_kind's answer, or for «other» a finer name (proxy tunnel,
    proxy not answering, format not available, ffmpeg, empty piece, connection cut, 5xx…)."""

    kind = error_kind(message)
    low = message.casefold()
    if kind == "unavailable" and ("requested format is not available" in low or "no hls stream" in low):
        return "formato-no-disponible"         # error_kind calls it «unavailable» («not available»): it is not the video
    if kind not in ("other", "timeout"):
        return kind
    for cause, markers in _CAUSES:
        if any(marker in low for marker in markers):
            return cause
    return kind if low.strip() else "sin-texto"


class Refused(RuntimeError):
    """A video this machine already refused (bot through several IPs, no HLS and too big, VPN, region): nothing was
    asked, so it is not a failed request in the log — the next candidate, at once."""


def error_detail(message: str, limit: int = 320) -> str:
    """An error's words for the request log: one line, proxy credentials masked (//****@), video ids kept."""

    text = re.sub(r"//[^/@\s]+@", "//****@", " ".join(str(message).split()))
    text = re.sub(r"^(ERROR:\s*)+", "", text)
    return text[:limit]
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


_PLAYER_JS_RE = re.compile(r"/s/player/([A-Za-z0-9_-]+)/[^?]*\.js(?:$|\?)")


def _local_response(url: str, data: bytes) -> Any:
    """A yt-dlp Response built from bytes on disk, as if the server had answered."""

    import io

    from yt_dlp.networking.common import Response

    return Response(io.BytesIO(data), url, {"Content-Type": "application/javascript; charset=utf-8",
                                            "Content-Length": str(len(data))}, 200)


def traffic_key(url: str) -> str:
    """Where a response came from, for the proxy's accounting: «googlevideo» (streams, whatever the edge host),
    «youtube.com/watch» (the page), «youtube.com/youtubei» (the player API), «youtube.com/s/player» (the player
    JS), «ytimg» (storyboards)… so an extraction's MB can be told apart later."""

    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return "?"
    host = (parts.hostname or "?").lower()
    if host.endswith("googlevideo.com"):
        return "googlevideo"
    if host.endswith("ytimg.com"):
        return "ytimg"
    if host.endswith("youtube.com"):
        head = "/".join(parts.path.split("/")[:3]) if parts.path.startswith("/s/player") else "/" + parts.path.strip("/").split("/")[0]
        return f"youtube.com{head}"
    return host


_PROXY_ENV = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def local_env() -> dict[str, str]:
    """The environment for ffmpeg/ffprobe working on files already on disk: without proxy variables, so a globally
    exported HTTPS_PROXY can never route (or bill) a local cut through the residential proxy. The ffmpeg that
    yt-dlp drives for a range is another matter: yt-dlp hands it the proxy itself, session included."""

    return {k: v for k, v in os.environ.items() if k not in _PROXY_ENV}


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
REQUEST_UNITS = {"search": 2, "metadata": 4, "captions": 1, "download": 3, "download (HLS)": 3, "download (rango)": 3,
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


def proxy_down_text(proxy: str, name: str) -> str:
    """What to check when a proxy does not answer: a home PC (proxy-youtube + Tailscale) or a paid residential proxy
    (its balance, credentials, the provider's status) — 2 722 notes on 17-11 spoke of Tailscale and «that PC» about
    gw.dataimpulse.com. Both keep «no responde»: sourcing takes such notes as not final (STALE_NOTES)."""

    from .proxy_sessions import is_residential

    if is_residential(proxy):
        return (f"El proxy residencial {name} no responde: mira en el panel del proveedor el saldo (GB), el usuario y "
                "la contraseña, y su estado. El vídeo se reintenta solo en 15 min")
    return (f"El proxy {name} no responde: ¿está abierto proxy-youtube en ese PC y conectado Tailscale? "
            "El vídeo se reintenta solo en 15 min")


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


def tunnel_failure(lowered: str) -> str | None:
    """The HTTP status a proxy answered to the CONNECT («Tunnel connection failed: 502 Bad Gateway»), or None. Through
    a residential proxy a 5xx there is the exit node of this session failing to reach YouTube, not the proxy being
    down; a 407 is the credentials and is left to the usual handling."""

    found = re.search(r"tunnel connection failed: (\d{3})", lowered)
    if found:
        return None if found.group(1) == "407" else found.group(1)
    # «Unable to connect to proxy … Tunnel …» without a status (4 442 metadata failures): the exit node dropped the
    # CONNECT — transient, like a 5xx; another session before the video is given up
    if "unable to connect to proxy" in lowered and "407" not in lowered and "authentication" not in lowered:
        return "sin respuesta"
    return None


# yt-dlp warnings that explain slow or failing downloads: shown once each (the rest stays quiet).
_WARNINGS = (
    (("challenge", "javascript runtime", "js runtime", "n function", "nsig", "ejs"),
     "yt-dlp no puede resolver los retos de YouTube → descargas lentas o formatos que faltan. "
     "Arréglalo con: pip install -U \"yt-dlp[default]\" deno"),
    (("po token", "some formats may be missing", "sabr"),
     "YouTube esconde algunos formatos a este cliente (PO token/SABR): se usan los que quedan (HLS); solo es un "
     "problema si además fallan las descargas"),
    (("http error 429", "too many requests"), "YouTube limita peticiones (429): el programa espera y reintenta"),
    (("http error 403", "forbidden"), "YouTube rechaza una descarga (403): se reintenta con enlaces nuevos"),
    (("timed out", "timeout", "retrying"), "descargas que se cortan o tardan en responder (red lenta): se reintentan"),
)
WARNING_COUNTS: dict[str, int] = {}
_warning_lock = threading.Lock()
_POT_WARNED = False          # the PO Token provider missing with a residential proxy: said once per process


def hls_format(fmt: str, *, audio: bool = False, audio_only: bool = False) -> str:
    """The same request limited to YouTube's HLS formats (served in small segments).

    With sound: a muxed HLS stream if there is one, else the HLS video track + the HLS audio track (233/234), fetched
    separately and joined locally. Since November 2026 YouTube serves almost no muxed HLS (389 of 398 extractions on
    the server had only the split ones), so without the second form every clip with sound went whole."""

    height = re.search(r"height<=(\d+)", fmt)
    limit = f"[height<={height.group(1)}]" if height else ""
    if audio_only:
        # the sound only: the lightest muxed stream, else the lightest audio-only HLS track
        return "worst[protocol^=m3u8][acodec!=none]/wa[protocol^=m3u8]"
    if audio:
        # 30 fps first, as cap_fps does for the video-only request: the 60 fps HLS stream is twice the bytes
        found = re.search(r"fps<=(\d+)", fmt)
        fps = f"[fps<={found.group(1)}]" if found else ""
        alts = [f"b{limit}{fps}[protocol^=m3u8][acodec!=none][vcodec^=avc1]", f"b{limit}{fps}[protocol^=m3u8][acodec!=none]",
                f"b{limit}[protocol^=m3u8][acodec!=none][vcodec^=avc1]", f"b{limit}[protocol^=m3u8][acodec!=none]",
                f"bv*{limit}{fps}[protocol^=m3u8][vcodec^=avc1]+ba[protocol^=m3u8]",
                f"bv*{limit}{fps}[protocol^=m3u8]+ba[protocol^=m3u8]",
                f"bv*{limit}[protocol^=m3u8]+ba[protocol^=m3u8]"]
        return "/".join(dict.fromkeys(alts))
    parts = [alt.split("+")[0] for alt in fmt.split("/") if alt.strip()]
    return "/".join(f"{alt}[protocol^=m3u8]" for alt in dict.fromkeys(parts))


def cap_height(fmt: str, max_height: Any) -> str:
    """Every height<=N of a yt-dlp format lowered to `max_height` (720): the clip is scaled to 1920x1080 anyway and
    nothing above 720p is visible after it. None/0 = as requested."""

    if not max_height:
        return fmt
    limit = int(max_height)
    return re.sub(r"height<=(\d+)", lambda m: f"height<={min(int(m.group(1)), limit)}", fmt)


def cap_fps(fmt: str, max_fps: Any) -> str:
    """Each video alternative first at `max_fps` (30) or less, then as it was: a 720p60 stream is twice the bytes of
    the 720p30 one and the clip is rendered at 30 fps. The resolution still wins over the frame rate (720p60 before
    480p30). Audio-only alternatives are left alone."""

    if not max_fps:
        return fmt
    out: list[str] = []
    for alt in (a.strip() for a in fmt.split("/") if a.strip()):
        parts = alt.split("+")
        video = parts[0]
        if video.startswith("ba") or "acodec!=none" in video or "fps" in video or "[vcodec=none]" in video:
            out.append(alt)
            continue
        capped = "+".join([f"{video}[fps<={int(max_fps)}]", *parts[1:]])
        out.extend([capped, alt])
    return "/".join(dict.fromkeys(out))


def requested_height(fmt: str) -> int | None:
    """The largest height<=N a format asks for (None without one)."""

    heights = [int(h) for h in re.findall(r"height<=(\d+)", fmt)]
    return max(heights) if heights else None


# Which other ranges already on disk can stand in for a request: an HD range serves the 360p analysis of the same
# seconds, and one with sound serves a silent request (ffmpeg maps the video only)
RANGE_FAMILY = {"a360": ("a360", "hd", "hdav"), "hd": ("hd", "hdav"), "hdav": ("hdav",), "au": ("au",)}


def cut_codec(prefix: str) -> list[str]:
    """The codec of a range cut here. The clips that end up in the video (hd, hdav…) keep x264 crf 16; the 360p windows
    the analysis only looks at (a360) go with crf 26 and the fastest preset: they were cut at the final clips'
    quality, a wasted encode on CPU and disk nobody ever sees."""

    if prefix == "a360":
        return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16"]


def join_segments(paths: list[Path], init: Path | None, target: Path) -> Path:
    """The downloaded segments of one track as ONE local file: the init segment (fragmented mp4), then each segment's
    bytes in order. MPEG-TS and fMP4 fragments are made to be joined like this; their timestamps run on."""

    with target.open("wb") as out:
        for piece in ([init] if init is not None else []) + list(paths):
            with piece.open("rb") as handle:
                shutil.copyfileobj(handle, out, 1024 * 1024)
    return target


def local_cut_command(inputs: list[tuple[float, Path]], start: float, end: float, prefix: str, audio: bool,
                      audio_only: bool, part: Path) -> list[str]:
    """ffmpeg cutting [start, end] out of the joined segments: `inputs` = [(source second where the file begins,
    file)], one per track (each input's timeline starts at 0 at its first timestamp).

    The seek is on the OUTPUT side: every frame is decoded from the file's start (a few segments of 720p) and the
    cut is exact. An input seek on MPEG-TS (no index) lands on an estimated byte inside a GOP, and with one keyframe
    per ~6 s segment nothing decodes until the next one: 1.3 s of 3.7, or no picture at all (22-11, escapadapolicial).
    A second track (the sound) is shifted by its own start so both line up with the first."""

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    base = inputs[0][0] if inputs else start
    for first_start, path in inputs:              # each track from its own first segment (their edges differ)
        shift = first_start - base
        command += [*(["-itsoffset", f"{shift:.3f}"] if abs(shift) > 1e-3 else []), "-i", str(path)]
    command += ["-ss", f"{max(0.0, start - base):.3f}", "-t", f"{end - start:.3f}"]
    if audio_only:
        return command + ["-vn", "-c:a", "aac", "-b:a", "160k", str(part)]
    # split tracks: the video from the first input, the sound from the second
    sound = (["-map", "1:a:0", "-c:a", "aac"] if len(inputs) > 1 else ["-map", "0:a:0?", "-c:a", "aac"]) if audio else ["-an"]
    return command + ["-map", "0:v:0", *sound, *cut_codec(prefix), "-pix_fmt", "yuv420p", str(part)]


def parse_media_playlist(text: str, base_url: str = "") -> tuple[list[tuple[str, float, float]], str | None]:
    """An HLS media playlist → ([(segment url, start s, end s)…], init segment url or None). Only what YouTube's
    VOD playlists use: #EXTINF durations, #EXT-X-MAP and plain URL lines (relative ones resolved against base_url)."""

    from urllib.parse import urljoin

    segments: list[tuple[str, float, float]] = []
    init_url: str | None = None
    clock = 0.0
    duration: float | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MAP:"):
            found = re.search(r'URI="([^"]+)"', line)
            if found:
                init_url = urljoin(base_url, found.group(1)) if base_url else found.group(1)
        elif line.startswith("#EXTINF:"):
            try:
                duration = float(line[len("#EXTINF:"):].split(",", 1)[0])
            except ValueError:
                duration = None
        elif not line.startswith("#"):
            if duration is None:
                continue
            url = urljoin(base_url, line) if base_url else line
            segments.append((url, clock, clock + duration))
            clock += duration
            duration = None
    return segments, init_url


def whole_format(fmt: str) -> str:
    """The same request over plain HTTPS (fetched in 10 MB pieces), video+audio pairs included: YouTube hardly
    offers files with both any more, and dropping the pairs sent every clip with sound to the slow per-range
    path (~4 min each in the cold open)."""

    return "/".join("+".join(f"{part}[protocol=https]" for part in alt.split("+")) for alt in fmt.split("/") if alt.strip())


def unplayable(details: dict[str, Any], region: str = "ES") -> str:
    """Why the player will refuse this video, from the Data API's videos.list (already asked, no extra unit): blocked
    or not allowed in our country (the proxy's), age-restricted (it needs an account: an account is not spent on
    footage), not public, not processed. "" when nothing says so (it may still refuse it, but far fewer go to yt-dlp)."""

    region = (region or "").upper()
    if region and region in [str(c).upper() for c in details.get("regionBlocked") or []]:
        return f"bloqueado en {region}"
    allowed = details.get("regionAllowed")
    if region and isinstance(allowed, list) and region not in [str(c).upper() for c in allowed]:
        return f"no disponible en {region}"
    if details.get("ageRestricted"):
        return "restringido por edad"
    if details.get("privacy") and details["privacy"] != "public":
        return f"no público ({details['privacy']})"
    if details.get("uploadStatus") and details["uploadStatus"] not in ("processed", "uploaded"):
        return f"no procesado ({details['uploadStatus']})"
    return ""


WHOLE_ESTIMATE_VERSION = 2      # «wholeMb» of an info cached with another version is worked out again


def whole_estimate_mb(formats: list[dict[str, Any]], max_height: int = 720) -> float | None:
    """What the video would weigh downloaded whole for its HD clip: the stream the HD download takes (the tallest at
    `max_height` or less, H.264 and 30 fps first, as ingest's format), plus the smallest audio when it has none, from
    yt-dlp's filesize / filesize_approx. None when unknown. Version 1 took the SMALLEST stream (a 144p of a few MB):
    elcrimendepazos (13/11) let through dozens of videos whose 720p weighed 85-325 MB, analysed and chosen for nothing."""

    def size(f: dict[str, Any]) -> float | None:
        value = f.get("filesize") or f.get("filesize_approx")
        return float(value) / 1e6 if value else None

    videos = [f for f in formats if f.get("vcodec") not in (None, "none") and (f.get("height") or 0) <= max_height
              and not str(f.get("format_id", "")).startswith("sb") and size(f) is not None]
    if not videos:
        return None
    best = max(videos, key=lambda f: (f.get("height") or 0, str(f.get("vcodec") or "").startswith("avc1"),
                                      float(f.get("fps") or 30) <= 30, -(size(f) or 0)))
    total = size(best) or 0.0
    if best.get("acodec") in (None, "none"):
        audios = [size(f) for f in formats if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")
                  and size(f) is not None]
        total += min(audios) if audios else 0.0
    return round(total, 1)


def unreachable_videos(cache_dir: Path, days: float = 7, without_hls: bool = True) -> set[str]:
    """YouTube ids no clip can come from now (refused «sin-hls», «vpn» or «geo» in the last `days`): the judge leaves
    them out, so a shot takes a clip that can be downloaded instead of failing at «Descargar en HD». `without_hls`
    False (sourcing.youtube.byte_ranges on): a video without HLS can come by byte ranges, so «sin-hls» is not one."""

    import json

    try:
        data = json.loads((cache_dir / "videos" / ".rechazados.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    now = time.time()
    return {video for video, entry in data.items() if isinstance(entry, dict)
            and entry.get("why") in ("sin-hls", "vpn", "geo", "no-disponible") and (without_hls or entry.get("why") != "sin-hls")
            and now - float(entry.get("at") or 0) < 86400 * days}


def _untested_hls(info_path: Path) -> bool:
    """The extraction's HLS formats are «to be tested» (yt-dlp's `__needs_testing`: a video uploaded ≤ 2 days before
    it was extracted); read from disk, no request."""

    import json

    try:
        formats = json.loads(info_path.read_text(encoding="utf-8")).get("formats") or []
    except (OSError, ValueError):
        return False
    return any(f.get("__needs_testing") for f in formats if str(f.get("protocol") or "").startswith("m3u8"))


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
                if first:                  # yt-dlp's own words once (a proxy's password hidden)
                    said = re.sub(r"//[^/@\s]+@", "//***@", " ".join(msg.split()))[:240]
                    print(f"   AVISO yt-dlp: {text}\n      yt-dlp dice: {said}")
                return

    def error(self, msg: str) -> None: ...


_CLEANED: set[str] = set()


def _clean_leftovers(videos: Path) -> None:
    """Once per process: the half-written files of a process that died (killed by a restart after `git pull`, a
    power cut): `.part<pid>-…` whose process is gone, and the old fixed-name leftovers (wip_, dl_, hls_ work)."""

    if str(videos) in _CLEANED or not videos.is_dir():
        return
    _CLEANED.add(str(videos))
    removed = clean_parts(videos)
    for pattern in ("*/wip_*", "*/dl_*", "*/hls_*"):          # the names used before 11-2026
        removed += _remove_old(videos, pattern, 6.0)
    if removed:
        print(f"   Caché de YouTube: {removed} archivo(s) a medias de procesos que murieron, borrados")


def _remove_old(folder: Path, pattern: str, older_hours: float) -> int:
    import shutil

    removed, now = 0, time.time()
    for path in folder.glob(pattern):
        try:
            if now - path.stat().st_mtime < older_hours * 3600:
                continue
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


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
        # A rotating residential proxy for the metadata request only (metadata_proxy, or YOUTUBE_METADATA_PROXY in
        # the environment, so the password stays out of git): every request leaves from another IP, with no account.
        # Downloads keep going out the usual way: stream URLs belong to the IP that asked for them, so a video to be
        # downloaded is extracted again that way first (_fresh_full_info), and the proxy's paid GB are only JSON.
        self.metadata_proxy = str(os.environ.get("YOUTUBE_METADATA_PROXY") or config.get("metadata_proxy") or "").strip()
        # A paid residential proxy (a user in its URL) changes IP on every connection unless the username carries the
        # provider's session suffix: one session per video (proxy_session_minutes, 30) so its metadata, storyboard
        # and ranges all leave from the IP its stream URLs belong to. Home proxies (no user) are one fixed IP: untouched.
        self.sessions = ProxySessions(cache_dir / "videos", minutes=float(config.get("proxy_session_minutes", 30)),
                                      max_rotations=int(config.get("proxy_session_rotations", 2)))
        self.residential = any(is_residential(p) for p in self.proxies)
        # «modo sin YouTube» (pipeline/sin_youtube.py, while the queue's YouTube pause lasts): what is on disk is still
        # read, but nothing goes out — every request stops here before the network, with this reason
        from ..sin_youtube import REASON, active

        self.offline: str | None = REASON if active() else None
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
        self._direct = requests.Session()            # the CDN (i.ytimg.com) without any proxy, explicit or inherited
        self._direct.trust_env = False
        self._direct.headers["User-Agent"] = USER_AGENT
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
        # Each player client is its own player request (and connection) per extraction, so through a residential
        # proxy (paid per GB and per connection) `player_client_residential` can name fewer. Not web_safari alone:
        # on 2026-11-05 every extraction with it failed «Requested format is not available» (no usable video
        # format came back), so the default is the same list as everywhere (`player_client`).
        chosen = config.get("player_client_residential") if self.residential else None
        chosen = chosen or config.get("player_client")
        self._configured_clients = [str(c) for c in (chosen or [])]
        if self._configured_clients:
            options["extractor_args"] = {"youtube": {"player_client": list(self._configured_clients)}}
        # `player_skip` (none by default): yt-dlp's own «skip these requests». With [default, web_safari] every
        # extraction also downloads www.youtube.com (~0.9 MB) only for web_safari's client config: the
        # «youtube.com/» line of --youtube-stats, 8.3 GB a week. [configs] skips it; whether the formats stay the
        # same is for `python -m pipeline.sonda_ytcfg` to say on the server before switching it on.
        skip = [str(x) for x in (config.get("player_skip") or [])]
        if skip:
            args = dict(options.get("extractor_args") or {})
            args["youtube"] = {**(args.get("youtube") or {}), "player_skip": skip}
            options["extractor_args"] = args
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
        _clean_leftovers(cache_dir / "videos")

    def _po_tokens(self, options: dict[str, Any]) -> bool:
        """PO Token Provider (bgutil-ytdlp-pot-provider: the yt-dlp plugin + its small server, see docs/VPS.md)
        for the configured clients (mweb is added only with pot_keep_clients: false). `po_token: auto` (default) uses it
        when the plugin is installed and the server answers; `on` warns when it cannot; `off` never."""

        import importlib.util

        mode = str(self.cfg.get("po_token", "auto")).lower()
        if mode in ("off", "false", "no"):
            return False
        if self.proxy and not self.residential and mode != "force":
            return False       # through home: YouTube sees the home IP, which needs no PO Token (and the provider
            #                    would make it here, for the server's IP). A residential proxy's IPs do need it: the
            #                    plugin hands the proxy (with its sticky session) to the provider, so the token is
            #                    minted for that exit IP, and talks to the provider itself without any proxy.
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
            global _POT_WARNED
            if mode in ("on", "true", "yes") or (self.residential and not _POT_WARNED):
                _POT_WARNED = True             # with a residential proxy it is what most avoids «are you a bot»: said once
                print(f"   AVISO PO Token: {'falta el plugin bgutil-ytdlp-pot-provider' if not plugin else 'el servidor no responde en ' + url}"
                      " (docs/VPS.md); sigo sin PO Token")
            return False
        args = options.setdefault("extractor_args", {})
        youtube = args.setdefault("youtube", {})
        clients = list(youtube.get("player_client") or ["default"])
        # mweb only when asked (pot_keep_clients: false): it gives no HLS formats, so every HD piece went through
        # ffmpeg and failed (pati12 14/10: 5 clips of 161); default + web_safari bring HLS and passed
        if "mweb" not in clients and not self.cfg.get("pot_keep_clients", True):
            clients.append("mweb")
        youtube["player_client"] = clients
        args["youtubepot-bgutilhttp"] = {"base_url": [url]}
        return True

    def _metric(self, action: str, *, ok: bool, seconds: float, error: str = "", attempt: int = 0,
                cookies: bool = False, size: int | None = None, span: tuple[float, float] | None = None,
                detail: str = "") -> None:
        """One line per request to YouTube in work/<slug>/youtube_downloads.jsonl: what was asked, how it went,
        with or without an account, client and PO Token (python main.py --youtube-stats sums them up). `detail` is
        the error's own words (proxy credentials masked), so «otros» can be told apart later."""

        if self.metrics_path is None:
            return
        import json

        row: dict[str, Any] = {"ts": round(time.time(), 1), "stage": self.stage, "action": action,
                               "video": getattr(self._local, "video_id", None), "ok": ok, "error": error,
                               "attempt": attempt, "cookies": cookies, "clients": self.clients, "pot": self.pot,
                               "seconds": round(seconds, 2), "wait": round(getattr(self._local, "waited", 0.0), 2)}
        if not ok:
            # every failure carries its words and a cause (20 524 metadata failures without a word on 17-11)
            row["detail"] = error_detail(detail) if detail else f"(sin texto; error {error or 'desconocido'})"
            row["cause"] = error_cause(detail) if detail else (error if error not in ("", "other") else "sin-texto")
            if row["cause"] in ONCE_PER_VIDEO:
                # the same video discarded for the same reason by every shot that picked it: one row, not one per shot
                seen = self.__dict__.setdefault("_logged_once", set())
                if (row["video"], row["cause"]) in seen:
                    return
                seen.add((row["video"], row["cause"]))
        if getattr(self._local, "via_metadata_proxy", False):
            row["proxy"] = "metadatos"
        elif self.proxies:
            row["proxy"] = self.way_name(getattr(self._local, "way", 0) or 0)
        session = self._session_in_use()
        if session:
            row["session"] = session
        if self._through_proxy():
            # what the proxy carried for this request: yt-dlp's own responses (and the HLS segments or the whole file
            # fetched in-process, already counted in the download's row), or the range's file when ffmpeg moved it
            if action.startswith("archivo"):
                row["proxy_bytes"] = int(size or 0) if getattr(self._local, "moved_unseen", True) else 0
            else:
                row["proxy_bytes"] = int(getattr(self._local, "proxy_bytes", 0) or 0)
                hosts = getattr(self._local, "proxy_hosts", None)
                if hosts:
                    row["hosts"] = dict(sorted(hosts.items(), key=lambda kv: -kv[1])[:8])
        if action.startswith("archivo") or action == "download (completo)":
            if getattr(self._local, "route", None):
                row["route"] = self._local.route
            if getattr(self._local, "not_hls", None):
                row["notHls"] = self._local.not_hls
        reused = getattr(self._local, "info_reused", None)
        if reused is not None and (action.startswith("archivo") or action.startswith("download") or action == "captions"):
            row["info_reused"] = bool(reused)
        if span is not None:             # the source seconds of a clip: overlapping downloads can be found later
            row["start"], row["end"] = round(span[0], 2), round(span[1], 2)
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
                    # two videos closing at once wrote the same «origin.tmp»: a lock and a temporary name of its own
                    with file_lock(origin.with_name(origin.name + ".lock")):
                        tmp = part_for(origin)
                        try:
                            tmp.write_text(newest, encoding="utf-8")
                            os.chmod(tmp, 0o600)
                            tmp.replace(origin)
                        finally:
                            tmp.unlink(missing_ok=True)
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
        if not self.cfg.get("hls_format_test", True) or getattr(self._local, "skip_format_test", False):
            # yt-dlp marks the HLS formats of videos uploaded ≤ 2 days before the extraction «to be tested» and, before
            # choosing a format, downloads a piece of each one; one whose test fails is dropped and the range falls to
            # the whole-file download. Off by default until `python -m pipeline.diag_hls` shows how many it affects
            options["check_formats"] = False
        if getattr(self._local, "via_metadata_proxy", False):
            options["proxy"] = self._proxy_for(self.metadata_proxy)   # no account through it, ever
            options.pop("cookiefile", None)
            options.pop("cookiesfrombrowser", None)
            if self.cfg.get("metadata_proxy_light", False) and not getattr(self._local, "mp_heavy", False):
                # Off by default: without the ~1 MB watch page (the visitor data in it) YouTube answered «are you a
                # bot» to 576 of 608 requests on pati7esc, against 15 % with it. Kept for trying again some day.
                args = dict(options.get("extractor_args") or {})
                youtube = dict(args.get("youtube") or {})
                youtube["player_skip"] = list(dict.fromkeys([*youtube.get("player_skip", []), "webpage"]))
                args["youtube"] = youtube
                options["extractor_args"] = args
            return self._metered(yt_dlp.YoutubeDL(options), True)
        if self.proxies:
            options["proxy"] = self._proxy_for(self.proxies[getattr(self._local, "way", 0) or 0])
        cookie_file = self._cookie_file()
        if cookie_file:
            options["cookiefile"] = cookie_file
        return self._metered(yt_dlp.YoutubeDL(options), bool(options.get("proxy")))

    def _player_js_path(self, url: str) -> Path | None:
        """Where the player JS of `url` lives on disk (cache/player_js/<version>-<hash>.js), or None for any other
        URL. The file is immutable per player version (the path carries it)."""

        import hashlib

        found = _PLAYER_JS_RE.search(url)
        if found is None:
            return None
        digest = hashlib.sha1(url.split("?", 1)[0].encode("utf-8")).hexdigest()[:12]
        return self.cache_dir / "player_js" / f"{found.group(1)}-{digest}.js"

    def _store_player_js(self, path: Path, data: bytes) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = part_for(path)
            tmp.write_bytes(data)
            tmp.replace(path)
            for old in path.parent.glob("*.js"):      # player versions change every few days: a handful stay
                if old != path and time.time() - old.stat().st_mtime > 7 * 86400:
                    old.unlink(missing_ok=True)
        except OSError:
            pass

    def _metered(self, ydl: Any, through_proxy: bool) -> Any:
        """Count the bytes of every HTTP response this YoutubeDL opens through a proxy (the page, the player API,
        the player JS, manifests, subtitles: all of yt-dlp's own requests go through `urlopen`) into the current
        request's `proxy_bytes`. Content-Length when the server sends it, else the body read (decompressed, an
        upper bound). What ffmpeg moves for a range is not seen here: the range's file size is counted instead."""

        if not through_proxy:
            return ydl
        original = ydl.urlopen
        local = self._local

        def add(amount: int, where: str = "") -> None:
            local.proxy_bytes = getattr(local, "proxy_bytes", 0) + max(0, int(amount))
            if where:                             # and by destination: what an extraction is made of
                hosts = getattr(local, "proxy_hosts", None)
                if hosts is None:
                    hosts = local.proxy_hosts = {}
                hosts[where] = hosts.get(where, 0) + max(0, int(amount))

        def counting(request: Any) -> Any:
            url = str(getattr(request, "url", None) or getattr(request, "full_url", "") or "")
            where = traffic_key(url)
            cached = self._player_js_path(url)
            if cached is not None:
                # yt-dlp keeps the player JS (~0.7 MB) only inside one YoutubeDL, and every extraction here is a
                # new one: 287 MB of the same file in a morning (21 % of the proxy). Once on disk per player version.
                if cached.is_file():
                    return _local_response(url, cached.read_bytes())
                response = original(request)
                data = response.read()
                add(len(data), where)
                self._store_player_js(cached, data)
                return _local_response(url, data)
            response = original(request)
            length = None
            try:
                length = int(response.headers.get("Content-Length"))
            except (TypeError, ValueError, AttributeError):
                length = None
            if length is not None:
                add(length, where)
                return response
            read = response.read

            def counting_read(amt: int | None = None) -> bytes:
                data = read(amt)
                add(len(data), where)
                return data

            try:
                response.read = counting_read
            except AttributeError:
                pass
            return response

        ydl.urlopen = counting
        return ydl

    def _through_proxy(self) -> bool:
        """Does the current request leave through a proxy (any kind), or directly from the server?"""

        return bool(getattr(self._local, "via_metadata_proxy", False)) or bool(self.proxies)

    def _session_key(self) -> str:
        """Whose sticky session a request uses: the video it is about, or the shared one for searches."""

        return getattr(self._local, "video_id", None) or "search"

    def _proxy_for(self, proxy: str) -> str:
        """`proxy` as yt-dlp (and the ffmpeg it drives) or requests must use it: a residential one gets this video's
        sticky session in its username; a home proxy (no user) is returned as it is."""

        if not is_residential(proxy):
            return proxy
        suffix = str(self.cfg.get("proxy_session_suffix") or "").strip() or SESSION_SUFFIX
        return with_sticky_session(proxy, self.sessions.session_id(self._session_key()), suffix=suffix)

    def _session_in_use(self) -> str | None:
        """The sticky session id the current request leaves with (None through a home proxy or directly)."""

        via_metadata = getattr(self._local, "via_metadata_proxy", False)
        proxy = self.metadata_proxy if via_metadata else (self.proxies[getattr(self._local, "way", 0) or 0] if self.proxies else "")
        return self.sessions.session_id(self._session_key()) if is_residential(proxy) else None

    def _paced_per_session(self, way: int, through: bool) -> bool:
        """`pace_per_session` (off by default): through a residential proxy each sticky session is its own exit IP,
        so the pace (`session_min_interval`) and the concurrency (`session_concurrency`) are per session (per YouTube
        video), with a cap on the connections open to the proxy for the whole machine (`proxy_connections_max`).
        The rule «never raise the pace to YouTube» was learnt with home proxies (one IP); here it has to be measured:
        python main.py --youtube-stats before and after (bot, 429, failed share per hour)."""

        return bool(self.cfg.get("pace_per_session", False)) and not through \
            and is_residential((self.proxies or [""])[way])

    def _session_pacer(self) -> Pacer:
        key = self.sessions.session_id(self._session_key())
        with self._turn_lock:
            pacers = self.__dict__.setdefault("_session_pacers", {})
            if key not in pacers:
                pacers[key] = Pacer(float(self.cfg.get("session_min_interval", self.cfg.get("min_interval", 1.0))))
            return pacers[key]

    @contextlib.contextmanager
    def _request_slots(self, way: int, per_session: bool):
        """The connection slots of one request: this process's and the way's (as always), or, paced per session, the
        session's own and one of the machine's `proxy_connections_max` connections to the proxy."""

        if not per_session:
            with self._slots:
                self._way_slots[way].acquire()
                try:
                    yield
                finally:
                    self._way_slots[way].release()
            return
        key = self.sessions.session_id(self._session_key())
        with self._turn_lock:
            gates = self.__dict__.setdefault("_session_gates", {})
            gate = gates.setdefault(key, threading.Semaphore(max(1, int(self.cfg.get("session_concurrency", 1)))))
            if not hasattr(self, "_proxy_slots"):
                self._proxy_slots = ProcessSlots(self.cache_dir / "videos" / ".conexiones-proxy",
                                                 int(self.cfg.get("proxy_connections_max", 6)))
        with gate, self._proxy_slots:
            yield

    def _calm_down(self) -> None:
        """Back to `concurrency` requests at a time: the extra slots are taken and never given back."""

        with self._turn_lock:
            extra, self._extra_slots = self._extra_slots, 0
        if extra:
            print(f"   YouTube pide calma: vuelvo a {self.concurrency * len(self._pacers) - extra} descargas a la vez")
            threading.Thread(target=lambda: [self._slots.acquire() for _ in range(extra)], daemon=True).start()

    def _call(self, action: str, fn: Any) -> Any:
        if self.offline:
            raise SourceUnavailable(self.offline)
        if self.blocked:
            raise SourceUnavailable(self.blocked)
        attempt = 0
        tries = 0
        through = bool(getattr(self._local, "via_metadata_proxy", False))     # metadata via the residential proxy
        with_account = self.cookies_mode == "rotate" and not through
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
            self._local.proxy_bytes = 0
            self._local.proxy_hosts = {}
            try:
                way = self._local.way = self._pick_way(tried_ways)
                # the waits that can be long (a 429's cooldown, the hourly budget: up to an hour) come BEFORE taking a
                # connection slot: holding one meanwhile stopped every other thread of the video for nothing
                delay = self._cooldown_until - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                    self._count("espera por límite", delay)
                held = 0.0 if through else self._budget_take(way, REQUEST_UNITS.get(action, 2))
                if held:
                    self._count("espera por presupuesto/hora", held)
                per_session = self._paced_per_session(way, through)
                with self._request_slots(way, per_session):
                    with self._proxy_lock:
                        self._busy[way] += 1
                    try:
                        if per_session:
                            self._session_pacer().wait()
                        else:
                            self._pacers[way].wait()
                        began = time.monotonic()
                        self._local.waited = began - queued     # our own queue (slots + pace + budget), not YouTube
                        try:
                            result = fn()
                        finally:
                            self._count(action, time.monotonic() - began)
                    finally:
                        with self._proxy_lock:
                            self._busy[way] -= 1
                self._metric(action, ok=True, seconds=time.monotonic() - began, attempt=tries,
                             cookies=self._local.account is not None)
                if not through:
                    self._bot_answered(way)     # the breaker weighs refusals against answers (of this connection)
                return result
            except Exception as error:
                message = str(error)
                lowered = message.casefold()
                kind = error_kind(message)
                self._metric(action, ok=False, seconds=time.monotonic() - began, error=kind, attempt=tries,
                             cookies=self._local.account is not None, detail=message)
                if isinstance(error, NoIndex):
                    # not a failure of the connection: the format cannot be cut by byte ranges. Passed on as it is so
                    # the caller goes to its next way; wrapped in RuntimeError it ended the shot's download (22-11:
                    # every one of 884 range failures lost its clip instead of trying the next route)
                    raise
                way = getattr(self._local, "way", 0) or 0
                if through:
                    retry = self._metadata_proxy_failed(kind, lowered, tries)
                    if retry == "again":
                        continue
                    if retry == "home":
                        through = self._local.via_metadata_proxy = False
                        with_account = self.cookies_mode == "rotate" or (kind == "auth" and bool(self._sets))
                        continue
                tunnel = tunnel_failure(lowered) if is_residential((self.proxies or [""])[way]) else None
                if tunnel is not None:
                    # the exit node of this sticky session cannot reach YouTube (502/503 on the CONNECT): another
                    # session, not a 15-minute pause of the whole proxy as with a home PC that is off
                    if self._rotate_after(f"túnel {tunnel}", action, tries):
                        continue
                    raise RuntimeError(f"yt-dlp {action}: el proxy residencial no pudo abrir el túnel ({tunnel}) en "
                                       f"{self.sessions.max_rotations + 1} sesiones; se descarta esta petición") from None
                # A request that hangs until it times out: is it YouTube being slow, or the proxy program stopped
                # (home PC asleep, proxy window closed)? One look at its port says which.
                if self.proxies and kind in ("other", "timeout") and ("timed out" in lowered or "timeout" in lowered) \
                        and not proxy_reachable(self.proxies[way]):
                    lowered += " proxy connection refused"
                if self.proxies and _proxy_down(lowered) and len(tried_ways) >= len(self.proxies) - 1:
                    from ..budget import ProxyDown

                    raise ProxyDown(proxy_down_text(self.proxies[way], self.way_name(way))) from None
                if len(self.proxies) > 1 and len(tried_ways) < len(self.proxies) - 1:
                    if _proxy_down(lowered):         # that way out is off (laptop asleep…): the others, and it rests
                        self._rest(way, float(self.cfg.get("proxy_rest_minutes", 10)) * 60, "no responde")
                        tried_ways.add(way)
                        continue
                if kind in ("bot", "429") and self._local.account is None and is_residential((self.proxies or [""])[way]):
                    # A residential proxy: «are you a bot» or 429 is this exit IP, not the line — the next connection
                    # can be another IP. A new sticky session for this video (a few times at most) instead of a two-hour
                    # quarantine of the whole proxy; after that it is the video, and it is dropped like before.
                    if self._rotate_after(kind, action, tries):
                        continue
                    video = getattr(self._local, "video_id", None) if action != "search" else None
                    rotations = self.sessions.max_rotations + 1
                    if kind == "bot":
                        if video is not None:
                            self._refuse(video)
                            print(f"   YouTube pide «no eres un bot» para el vídeo {video} desde {rotations} IPs del proxy: se descarta")
                        raise RuntimeError(f"yt-dlp {action}: YouTube pide «no eres un bot» desde {rotations} IPs del proxy "
                                           "residencial; se descarta esta petición") from None
                    raise RateLimited(f"yt-dlp {action}: YouTube limita peticiones (429) en {rotations} sesiones del proxy "
                                      "residencial; se descarta esta petición") from None
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
                    if video is None or self._bot_tripped(way, video):
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
                            not self._bot_tripped(way, video):
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
                if is_residential((self.proxies or [""])[way]):
                    video = getattr(self._local, "video_id", None) if action != "search" else None
                    if "with a vpn or proxy" in lowered and video is not None:
                        # YouTube refuses this video to any proxy IP (not age, not region): asking again from another
                        # session pays the same answer
                        self._refuse(video, "vpn")
                        raise RuntimeError(f"yt-dlp {action}: YouTube no sirve el vídeo {video} a la IP de un proxy; "
                                           "se descarta") from None
                    if "available in your country" in lowered and video is not None:
                        # geo-blocked for the proxy's country: 25 answers for one video in gimnasia1, one is enough
                        self._refuse(video, "geo")
                        raise RuntimeError(f"yt-dlp {action}: el vídeo {video} no está disponible en el país del proxy; "
                                           "se descarta") from None
                    if kind == "timeout" and tries <= int(self.cfg.get("timeout_retries_residential", 1)) \
                            and self._rotate_after("timeout", action, tries):
                        continue                 # a slow exit IP: the sticky session would keep it for 28 minutes
                    if isinstance(error, (TypeError, KeyError, IndexError, AttributeError)) and tries <= 1 \
                            and self._rotate_after("respuesta rota", action, tries):
                        # yt-dlp itself crashed on what this IP was served («sequence item 52: expected str
                        # instance, NoneType found», three times from one session on AMA4j3IcLWw; fine from
                        # another IP): once more from another session
                        continue
                video = getattr(self._local, "video_id", None) if action != "search" else None
                if video is not None and any(marker in lowered for marker in _GONE_MARKERS):
                    # removed, private, terminated: no stage asks for it again (coldopen asked 1 070 times)
                    self._refuse(video, "no-disponible")
                    raise Refused(f"yt-dlp {action}: {video} no está disponible ({message[:120]}); "
                                  "no se vuelve a pedir") from None
                if any(marker in lowered for marker in _RATE_MARKERS):
                    # «too many requests» is YouTube's other «stop»: the same quarantine as a bot check, no retry —
                    # and the extra slots of several accounts are given back for the rest of the run
                    self._calm_down()
                    self._quarantine(way, "YouTube responde 429 (demasiadas peticiones)")
                    if self._all_in_quarantine():
                        self._blocked_everywhere()
                    raise RateLimited(f"yt-dlp {action}: YouTube limita peticiones (429); esa conexión queda en "
                                      "cuarentena") from None
                # A passing failure at home or straight from the server (a timeout, a 5xx, a cut connection): two more
                # tries with a growing, random pause before the candidate is lost — the residential way already
                # retries from another session above. Never for «are you a bot» or a 429, which have their own rules.
                if not is_residential((self.proxies or [""])[way]) and kind not in ("bot", "429", "auth") \
                        and error_cause(message) in ("timeout", "conexión-cortada", "http-5xx") \
                        and tries <= int(self.cfg.get("transient_retries", 2)):
                    import random

                    pause = random.uniform(2.0, 6.0) * tries
                    time.sleep(pause)
                    self._count("espera por error pasajero", pause)
                    continue
                raise RuntimeError(f"yt-dlp {action}: {message[:200]}") from None

    def _rotate_after(self, kind: str, action: str, tries: int) -> bool:
        """A new sticky session (exit IP) for the current video or the shared search session after «are you a bot»
        or a 429 (with a pause, rate_backoff × try); False when this video already rotated its share."""

        key = self._session_key()
        fresh = self.sessions.rotate(key)
        if fresh is None:
            return False
        if kind == "429":
            pause = min(120.0, float(self.cfg.get("rate_backoff", 20)) * max(1, tries))
            time.sleep(pause)
            self._count("espera por límite", pause)
        now = time.monotonic()
        if now - getattr(self, "_rotation_said", 0.0) > 120:
            self._rotation_said = now
            what = ("YouTube pide «no eres un bot»" if kind == "bot" else "YouTube responde 429" if kind == "429"
                    else "YouTube no responde a tiempo" if kind == "timeout"
                    else "YouTube sirve una respuesta que yt-dlp no entiende" if kind == "respuesta rota"
                    else f"el proxy no abre el túnel ({kind})")
            whose = f"el vídeo {key}" if key != "search" else "las búsquedas"
            print(f"   {what} con una IP del proxy residencial ({action}): sesión nueva para {whose} "
                  f"(sesiones rotadas en esta ejecución: {self.sessions.rotated})")
        return True

    def _metadata_proxy_failed(self, kind: str, lowered: str, tries: int) -> str:
        """A metadata request through the residential proxy failed: «again» (the next request leaves from another IP),
        «home» (the usual way, as before the proxy: it does not answer, or the video needs an account) or «drop»."""

        video = getattr(self._local, "video_id", None)
        retries = int(self.cfg.get("metadata_proxy_retries", 2))   # every failed try is paid too (~1 MB)
        refused = kind == "bot" or any(marker in lowered for marker in _RATE_MARKERS)
        unreachable = _proxy_down(lowered) or "timed out" in lowered
        light = bool(self.cfg.get("metadata_proxy_light", False)) and not getattr(self._local, "mp_heavy", False)
        if light and kind != "auth" and not unreachable:
            self._local.mp_heavy = True         # without the watch page it did not work: again, with it
            return "again"
        if (refused or unreachable) and tries <= retries:
            # a residential metadata proxy with sticky sessions: «again» must mean another IP, so the session rotates
            # (bounded per video); with none left, this video is refused from several IPs below
            if not (refused and is_residential(self.metadata_proxy)) or self.sessions.rotate(self._session_key()) is not None:
                return "again"
        if kind == "auth" or unreachable:
            if unreachable and time.monotonic() - getattr(self, "_mp_said", 0.0) > 300:
                self._mp_said = time.monotonic()
                why = ("rechaza el usuario o la contraseña, o no le queda saldo (407)" if "407" in lowered
                       else "no responde")
                print(f"   El proxy de metadatos {why}: esas peticiones salen por la vía de siempre")
            return "home"
        if refused and video:
            self._refuse(video)                 # refused from several residential IPs: that video, not a connection
            print(f"   YouTube pide «no eres un bot» para el vídeo {video} desde {tries} IPs del proxy: se descarta")
            raise RuntimeError("yt-dlp metadata: YouTube pide «no eres un bot» para este vídeo; se descarta") from None
        return "drop"

    def way_name(self, way: int) -> str:
        from urllib.parse import urlsplit

        return (urlsplit(self.proxies[way]).hostname or self.proxies[way]) if self.proxies else "directo"

    def _refused_path(self) -> Path:
        return self.cache_dir / "videos" / ".rechazados.json"

    def _refuse(self, video: str, why: str = "bot") -> None:
        """A video not asked for again by any shot or process: `why` is «bot» (it asked «are you a bot»: refused_days,
        7, or refused_hours_residential through a paid proxy), «sin-hls» (no HLS and too big to come whole through
        the residential proxy: every shot that picked it again paid another extraction, 12 times one night) or «vpn»
        (YouTube does not serve it to a proxy's IP). The last two hold for refused_days whatever the proxy."""

        entry = time.time() if why == "bot" else {"at": time.time(), "why": why}
        try:
            # every video's process writes here: read-modify-write under an flock (a plain write lost the refusals
            # another process had just added) and an atomic write
            data = update_json(self._refused_path(), lambda d: {**(d if isinstance(d, dict) else {}), video: entry}, {})
        except OSError:
            data = {**self._refusals(), video: entry}
        with self._turn_lock:
            self._refused_cache = data
            self._refused_mtime = self._refused_stamp()

    def _refused_stamp(self) -> tuple[int, int] | None:
        try:
            stat = self._refused_path().stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _refusals(self) -> dict[str, Any]:
        """Reloaded when the file changes (another video's process refused something): the refusals of every process."""

        stamp = self._refused_stamp()
        data = getattr(self, "_refused_cache", None)
        if data is None or stamp != getattr(self, "_refused_mtime", None):
            data = read_json(self._refused_path(), {})
            data = data if isinstance(data, dict) else {}
            with self._turn_lock:
                self._refused_cache, self._refused_mtime = data, stamp
        return data

    def _blocking_refusals(self) -> tuple[str, ...]:
        """What keeps a video from being downloaded at all: with byte ranges on, «sin-hls» no longer does (its
        ranges come from the DASH mp4) — the videos refused that way before can be used again at once."""

        return ("vpn", "geo") if self.cfg.get("byte_ranges", False) else ("sin-hls", "vpn", "geo")

    def refused(self, video: str) -> bool:
        return self.refused_why(video) is not None

    def refused_why(self, video: str) -> str | None:
        """«bot», «sin-hls» or «vpn» while the refusal of `video` holds; None when it may be asked for again."""

        entry = self._refusals().get(video)
        if entry is None:
            return None
        when, why = (float(entry["at"]), str(entry.get("why") or "bot")) if isinstance(entry, dict) else (float(entry), "bot")
        # Through a residential proxy «are you a bot» was the exit IP that asked, not the video: a few hours
        # (refused_hours_residential, 3) and it may be asked again from another session, not refused for a week.
        ttl = 3600 * float(self.cfg.get("refused_hours_residential", 3)) if self.residential and why == "bot" \
            else 86400 * float(self.cfg.get("refused_days", 7))
        return why if time.time() - when < ttl else None

    @staticmethod
    def _refusal_text(why: str) -> str:
        return {"sin-hls": "sin HLS y entero supera el tope del proxy residencial",
                "no-disponible": "YouTube dice que el vídeo no está disponible (borrado, privado o retirado)",
                "vpn": "YouTube no lo sirve a la IP de un proxy",
                "geo": "no está disponible en el país del proxy"}.get(why, "pidió «no eres un bot»")

    def _bots_path(self, way: int) -> Path:
        return self.cache_dir / "videos" / (pacer_name((self.proxies or [""])[way]) + ".bots")

    def _bots_rows(self, way: int, add: list[Any]) -> list[list[Any]]:
        """[time, video, refused 1/0] of the last bot_breaker_minutes on that way, plus `add`; kept in a file per way
        (every process, across restarts)."""

        window = 60 * float(self.cfg.get("bot_breaker_minutes", 10))
        path = self._bots_path(way)
        now = time.time()

        def change(rows: Any) -> list[list[Any]]:
            rows = [r for r in (rows if isinstance(rows, list) else [])
                    if isinstance(r, list) and len(r) == 3 and now - float(r[0]) < window]
            return (rows + [[now, *add]])[-500:]

        try:
            return update_json(path, change, [])            # every process: an flock and an atomic write
        except OSError:
            return change([])

    def _bot_answered(self, way: int) -> None:
        self._bots_rows(way, ["", 0])

    def _bot_tripped(self, way: int, video: str) -> bool:
        """Is this «are you a bot» the connection (or account) and not that video? Some videos ask everyone while
        the rest pass (home 13/10: 3 of 59 refused, a good line). A flagged line refuses most: pati12 14/10 from
        work, 3 of 6 and then ~100 in a row — while a famous video still passed, so no «control video» can tell.
        Blocked when, within bot_breaker_minutes, `bot_breaker_videos` (3) different videos were refused AND they
        are at least half of what was asked (`bot_breaker_share`, 0.5)."""

        rows = self._bots_rows(way, [video, 1])
        refused = {r[1] for r in rows if r[2]}
        refusals = sum(1 for r in rows if r[2])
        share = refusals / len(rows)
        return len(refused) >= int(self.cfg.get("bot_breaker_videos", 3)) and \
            share >= float(self.cfg.get("bot_breaker_share", 0.5))

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
            with file_lock(path.with_name(path.name + ".lock")):      # never shortens another process's quarantine
                atomic_write_text(path, f"{max(until, quarantined_until(self.cache_dir, proxy)):.0f}")
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

        if self.offline:
            raise SourceUnavailable(self.offline)
        if self.blocked or self._all_in_quarantine():
            raise SourceUnavailable(self.blocked or "YouTube: todas las conexiones en cuarentena")
        way = self._pick_way()
        free = any(host in url for host in _FREE_HOSTS)
        if not free:
            self._budget_take(way, REQUEST_UNITS["get"])
        if free and is_residential((self.proxies or [""])[way]):
            # storyboard thumbnails are not bound to an IP: paid GB for nothing — direct, the proxy only if that fails
            try:
                response = self._direct.get(url, timeout=timeout)
                if response.status_code < 500:
                    return response
            except requests.RequestException:
                pass
        self._local.way = way
        began = time.monotonic()
        try:
            response = self._session_get(way, url, timeout)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as error:
            if len(self._sessions) == 1:
                if is_residential((self.proxies or [""])[way]):
                    self._metric("get", ok=False, seconds=time.monotonic() - began, error=error_kind(str(error)),
                                 detail=str(error))
                raise
            self._rest(way, float(self.cfg.get("proxy_rest_minutes", 10)) * 60, "no responde")
            way = self._local.way = self._pick_way({way})
            response = self._session_get(way, url, timeout)
        if is_residential((self.proxies or [""])[way]):      # paid per GB: every GET through it is in the log
            self._local.proxy_bytes = len(response.content or b"")
            from urllib.parse import urlsplit

            self._metric("get", ok=response.status_code < 400, seconds=time.monotonic() - began,
                         error="" if response.status_code < 400 else ("429" if response.status_code == 429 else
                                                                       "403" if response.status_code == 403 else "other"),
                         detail=f"HTTP Error {response.status_code} en {urlsplit(url).hostname}")
        return response

    def _session_get(self, way: int, url: str, timeout: float) -> requests.Response:
        proxies = self._requests_proxies(way)
        if proxies is None:                   # home proxy or direct: the session's own settings, as always
            return self._sessions[way].get(url, timeout=timeout)
        return self._sessions[way].get(url, timeout=timeout, proxies=proxies)

    def _requests_proxies(self, way: int) -> dict[str, str] | None:
        """Per-request proxies for `requests`: the way's proxy with this video's sticky session when residential;
        None keeps the session's own (fixed) proxy, or none at all."""

        proxy = self.proxies[way] if self.proxies else ""
        if not is_residential(proxy):
            return None
        sticky = self._proxy_for(proxy)
        return {"http": sticky, "https": sticky}

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
        if self.api is not None:
            # an API search costs 100 units whether it brings 8 or 50: more to rank by title and description before
            # paying any extraction (api_results_per_query, 30); the yt-dlp search keeps results_per_query
            limit = int(self.cfg.get("api_results_per_query", 30))
        scrape_limit = min(limit, int(self.cfg.get("results_per_query", 8)))
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
                extra = {"extract_flat": "in_playlist", "skip_download": True, "playlistend": scrape_limit}
            else:
                target = f"ytsearch{scrape_limit}:{query}"
                extra = {"extract_flat": "in_playlist", "skip_download": True}
            self._local.video_id = None             # a search is nobody's video: the shared sticky session
            if str(self.cfg.get("api_overflow", "esperar")).lower() == "mixto":
                # api_overflow: mixto — the quota ran out: the searches left go by yt-dlp through the proxy's search
                # session instead of waiting for tomorrow, but never more than overflow_searches_per_hour (60) for the
                # whole machine, on top of the usual pace and hourly budget
                with self._turn_lock:
                    if not hasattr(self, "_overflow_budget"):
                        self._overflow_budget = HourlyBudget(self.cache_dir / "videos" / ".busquedas-ytdlp",
                                                             float(self.cfg.get("overflow_searches_per_hour", 60)))
                waited = self._overflow_budget.take(1)
                if waited:
                    self._count("espera por tope de búsquedas yt-dlp", waited)
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

        if self.offline:
            raise SourceUnavailable(self.offline)
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
                 "description": str(details[i].get("description") or "")[:500],   # ranks before any extraction
                 "unplayable": unplayable(details[i], str(self.cfg.get("region", "ES"))),
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
        if blocked_by_title(str(entry.get("title") or ""), str(entry.get("channel") or ""), self.cfg.get("title_blocklist"),
                            self.cfg.get("official_channels")):
            return False
        if entry.get("unplayable"):
            return False        # the API already says the player will refuse it: no yt-dlp request for it
        if entry.get("definition") == "sd" and int(self.cfg.get("min_height", 720)) >= 720:
            return False        # the API already says it is under 720p: no need to ask yt-dlp for its details
        return "/shorts/" not in str(entry.get("url") or "")

    def _info_path(self, video_id: str) -> Path:
        return self.cache_dir / "videos" / video_id / "info.json"

    def info(self, video_id: str) -> dict[str, Any]:
        # one request per video at a time: two shots asking for the same one at once both got refused (pati12 14/10)
        with self._turn_lock:
            lock = self.__dict__.setdefault("_video_locks", {}).setdefault(video_id, threading.Lock())
        with lock:
            return self._info(video_id)

    def _info(self, video_id: str) -> dict[str, Any]:
        self._local.video_id = video_id
        why = self.refused_why(video_id)
        if why == "sin-hls" and self.cfg.get("byte_ranges", False):
            why = None                     # its ranges come by byte ranges now: not a reason to skip it
        if why is not None and (why != "bot" or not self._info_path(video_id).is_file()):
            raise Refused(f"{video_id}: descartado ({self._refusal_text(why)}); no se vuelve a pedir")
        path = self._info_path(video_id)
        refresh = getattr(self._local, "refresh_links", False)
        if refresh and self._full_info_usable(video_id) and path.is_file():
            # another shot of this video re-extracted while this one waited for the video's lock: its links serve
            refresh = False
        if path.is_file() and not refresh:
            try:
                import json

                cached = json.loads(path.read_text(encoding="utf-8"))
                if "storyboard" not in cached:  # written by the older, download-first sourcing
                    path.unlink()
                elif "hls" not in cached or cached.get("wholeMbV") != WHOLE_ESTIMATE_VERSION:
                    self._backfill_hls(video_id, cached, path)
            except (OSError, ValueError):
                path.unlink(missing_ok=True)

        def produce() -> dict[str, Any]:
            # Through the metadata proxy, unless this extraction is for a download (its stream URLs must be ours) or
            # the usual way is itself a residential proxy with sticky sessions: then one extraction, by this video's
            # session, serves the metadata AND every range of the video (no second, «ours», extraction later).
            self._local.via_metadata_proxy = bool(self.metadata_proxy) and not getattr(self._local, "for_download", False) \
                and not self.residential
            try:
                data = self._call(
                    "metadata",
                    lambda: self._extract(f"https://www.youtube.com/watch?v={video_id}", {"skip_download": True}),
                )
                via = "metadata_proxy" if self._local.via_metadata_proxy else ""
                session = self._session_in_use()
            finally:
                self._local.via_metadata_proxy = self._local.mp_heavy = False
            self._save_full_info(video_id, data, via, session)
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
                "hls": any(str(f.get("protocol") or "").startswith("m3u8") for f in formats),
                "wholeMb": whole_estimate_mb(formats),
                "wholeMbV": WHOLE_ESTIMATE_VERSION,
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

        if refresh:
            # only the stream links expired (fase 3.2): the metadata is rewritten in place, never deleted first — a
            # failed extraction keeps it, and nothing else of the video is worked out again
            import json

            value = produce()
            atomic_write_text(path, json.dumps(value, ensure_ascii=False) + "\n")
            return value
        return cached_json(path, produce)

    def _backfill_hls(self, video_id: str, cached: dict[str, Any], path: Path) -> None:
        """An info cached before «hls»/«wholeMb» existed: both from the full yt-dlp info already on disk (no request),
        when the same player clients extracted it (another client set may have had no HLS where today's has). Without
        them the search-time filter let through, video after video, the same unbuildable candidates of the shared
        gymnastics pool: gimnasia2, 23 shots on sZuVQzbIjuc alone, all refused at the download."""

        import json

        try:
            full = json.loads(self._full_info_path(video_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if full.get("_edit_vid3_clients") != self._clients():
            return
        formats = full.get("formats") or []
        if not formats:
            return
        cached["hls"] = any(str(f.get("protocol") or "").startswith("m3u8") for f in formats)
        cached["wholeMb"] = whole_estimate_mb(formats)
        cached["wholeMbV"] = WHOLE_ESTIMATE_VERSION
        try:
            atomic_write_text(path, json.dumps(cached))
        except OSError:
            pass

    def _undownloadable(self, info: dict[str, Any]) -> str | None:
        """Why this video could not be downloaded through the residential proxy (no HLS and over the whole-download
        caps), or None. Older cached infos without the `hls` field are left alone."""

        if not self.residential or info.get("hls") is not False or self.cfg.get("byte_ranges", False):
            return None
        max_minutes, max_mb = self._whole_caps()
        duration = float(info.get("duration") or 0)
        if duration > 60 * max_minutes:
            return f"sin HLS y dura {duration / 60:.0f} min (> {max_minutes:g} min)"
        size = info.get("wholeMb")
        if size is not None and float(size) > max_mb:
            return f"sin HLS y pesa {float(size):.0f} MB (> {max_mb:g} MB)"
        return None

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

        folder = self.cache_dir / "videos" / video_id
        failed = folder / "captions.fallo.json"
        known = read_json(failed, {}) if failed.is_file() else {}
        if isinstance(known, dict) and time.time() < float(known.get("until") or 0):
            return []                 # failed a moment ago (any process): not asked again per option and per shot

        def produce() -> list[list[Any]]:
            info = self.info(video_id)
            url = info.get("captions", {}).get("en") or info.get("captions", {}).get("es")
            if not url:
                return []
            # YouTube's subtitles answer 429 to bursts (1 108 in the analysis stage, half of every GET): their own
            # pace for the whole machine (captions_min_interval, 3 s), through the video's session as before
            self._captions_pacer().wait()
            response = self._get(url, timeout=30)
            if response.status_code == 429:
                raise RateLimited("subtítulos: 429")
            response.raise_for_status()
            cues = _LegacyParsers._parse_json3(response.text)
            return [[c.start_seconds, c.end_seconds, c.text] for c in cues]

        try:
            cues = cached_json(folder / "captions.json", produce)
        except SourceUnavailable:
            return []                 # no YouTube now (pause, quarantine): nothing asked, nothing remembered
        except Exception as error:
            # 429 or a passing error: a short rest (captions_retry_minutes, 30); anything else for a day
            minutes = float(self.cfg.get("captions_retry_minutes", 30)) if isinstance(error, RateLimited) \
                or error_kind(str(error)) in ("429", "timeout") else 24 * 60.0
            try:
                atomic_write_text(failed, json.dumps({"until": time.time() + 60 * minutes,
                                                      "error": error_detail(f"{type(error).__name__}: {error}")}))
            except OSError:
                pass
            print(f"   yt:{video_id}: subtítulos no disponibles ({error_detail(str(error), 100) or type(error).__name__}); "
                  f"no se piden otra vez en {minutes:.0f} min")
            return []
        return [tuple(c) for c in cues]  # type: ignore[misc]

    def _captions_pacer(self) -> Pacer:
        with self._turn_lock:
            if not hasattr(self, "_captions_pace"):
                self._captions_pace = SharedPacer(float(self.cfg.get("captions_min_interval", 3.0)),
                                                  self.cache_dir / "videos" / ".ritmo-subtitulos")
            return self._captions_pace

    # --- downloads without re-extraction ------------------------------------------------

    def _clients(self) -> list[str]:
        """The player clients the info dicts are stamped with (re-extracted when they change)."""

        return list(self._configured_clients)

    def _full_info_path(self, video_id: str) -> Path:
        return self.cache_dir / "videos" / video_id / "ytdlp-info.json"

    def _save_full_info(self, video_id: str, data: dict[str, Any], via: str = "", session: str | None = None) -> None:
        """yt-dlp's own info dict (minus bulky fields) so downloads can skip the ~4 s extraction."""

        import json

        slim = {k: v for k, v in data.items() if k not in ("automatic_captions", "subtitles", "thumbnails", "heatmap")}
        slim["_edit_vid3_clients"] = self._clients()     # re-extract when the player clients change
        slim["_edit_vid3_via"] = via                     # metadata_proxy: its stream URLs are another IP's
        slim["_edit_vid3_session"] = session             # residential proxy: the sticky session (IP) they belong to
        path = self._full_info_path(video_id)
        with self._ydl() as ydl:
            atomic_write_text(path, json.dumps(ydl.sanitize_info(slim)))

    def _fresh_full_info(self, video_id: str) -> Path:
        """Path to a full info JSON whose stream URLs are still valid (re-extracting if needed).

        Valid: extracted the way the download leaves (never the metadata proxy), by the same player clients, with
        every stream URL at least `info_expiry_margin_minutes` (15) from its `expire`, and — through a residential
        proxy — by this video's sticky session while it is still alive (the IP the URLs are bound to). Otherwise one
        extraction, the same price as before, and the result is cached for the next ranges of the video."""

        self._local.info_reused = False
        path = self._full_info_path(video_id)
        if self._full_info_usable(video_id):
            self._local.info_reused = True
            return path
        self._local.for_download = True     # extracted the way the download goes out (never the metadata proxy)
        self._local.refresh_links = True    # info.json stays until the new extraction replaces it
        try:
            self.info(video_id)  # re-extracts and re-saves the full info
        finally:
            self._local.for_download = False
            self._local.refresh_links = False
        return path

    def _full_info_usable(self, video_id: str) -> bool:
        """The full info on disk has stream links this download can still use (see _fresh_full_info)."""

        import json

        try:
            data = json.loads(self._full_info_path(video_id).read_text(encoding="utf-8"))
            formats = data.get("formats") or []
            expiries = [
                int(found.group(1)) for f in formats if f.get("vcodec") not in (None, "none") and f.get("url")
                # stream URLs carry ?expire=…, HLS manifests /expire/…/
                for found in [re.search(r"[/?&]expire[/=](\d+)", f["url"])] if found
            ]
            margin = 60 * float(self.cfg.get("info_expiry_margin_minutes", 15))
            ours = not data.get("_edit_vid3_via") and (
                not self.residential or self.sessions.matches(video_id, data.get("_edit_vid3_session")))
            return bool(expiries) and min(expiries) - time.time() > margin \
                and data.get("_edit_vid3_clients") == self._clients() and bool(ours)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def download_range(self, video_id: str, start: float, end: float, *, fmt: str, prefix: str,
                       audio: bool = False, audio_only: bool = False) -> Path:
        """See _download_range; also records the file's size and speed in the metrics."""

        self._local.video_id = video_id
        self._local.info_reused = None
        began = time.monotonic()
        before = getattr(self._local, "fetched", 0)
        self._local.moved_unseen = False       # True once ffmpeg itself moves the bytes (the meter cannot see them)
        try:
            path = self._download_range(video_id, start, end, fmt=fmt, prefix=prefix, audio=audio, audio_only=audio_only)
        except Exception as error:
            # never asked (no YouTube now, or a video already refused): not a failed download
            if not (self.offline and str(error) == self.offline) and not isinstance(error, Refused):
                self._metric(f"archivo {prefix}", ok=False, seconds=time.monotonic() - began,
                             error=error_kind(str(error)), span=(start, end), detail=str(error))
            raise
        if getattr(self._local, "fetched", 0) != before:      # downloaded now, not taken from the cache
            size = path.stat().st_size if path.is_file() else 0
            self._metric(f"archivo {prefix}", ok=True, seconds=time.monotonic() - began, size=size, span=(start, end))
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
        if not audio_only:
            # 720p/30fps at most (sourcing.youtube.max_height/max_fps): the final 1920x1080 at 30 fps shows no more
            fmt = cap_fps(cap_height(fmt, self.cfg.get("max_height", 720)), self.cfg.get("max_fps", 30))
        wanted = requested_height(fmt)
        self._local.route, self._local.not_hls = "biblioteca", None
        existing = self._library_range(target_dir, prefix, suffix, start, end, wanted)
        if existing is not None:
            return existing
        self._local.route = None
        if (self.residential and self.refused_why(video_id) in self._blocking_refusals()) \
                or self.refused_why(video_id) == "no-disponible":
            raise Refused(f"yt-dlp download: {video_id} descartado ({self._refusal_text(self.refused_why(video_id) or '')}); "
                          "se pasa al siguiente candidato")
        self._local.fetched = getattr(self._local, "fetched", 0) + 1     # not in the cache: a real download
        # Resolve (maybe re-extract) the info *before* taking a connection slot: _fresh_full_info
        # may itself call _call(), and nesting slots deadlocks when all of them are taken.
        whole = next((p for p in sorted(target_dir.glob(f"full_{prefix}.*")) if p.suffix in (".mp4", ".mkv", ".webm")), None)
        if whole is not None and not audio_only:          # already downloaded whole (prefetch_sections)
            self._local.route = "corte-de-entero-en-caché"
            return self._cut(whole, video_id, start, end, prefix, audio)
        if self.offline:                                  # not on disk: without YouTube this clip cannot come
            raise SourceUnavailable(self.offline)
        info_path = self._fresh_full_info(video_id)
        if prefix == "a360":
            self._check_hd_reachable(video_id, info_path)     # not worth analysing a clip that cannot come in HD
        hls = hls_format(fmt, audio=audio, audio_only=audio_only) if self.cfg.get("hls_ranges", True) else None
        # why a range does not come by HLS, in its log row (2/3 of the residential downloads were whole files on
        # 17-11 although almost every video has HLS: this says which branch sends them there)
        self._local.not_hls = None if hls else "hls_ranges apagado"
        if hls and not _has_hls(info_path):
            self._local.not_hls = self._why_no_hls(video_id, info_path)
        missed = self.__dict__.setdefault("_hls_missed", set())
        if hls and (video_id, hls) in missed:       # this request found no HLS stream of this video a moment ago
            self._local.not_hls = f"ningún formato HLS encaja con «{hls[:120]}» (ya visto)"
        elif hls and _has_hls(info_path):
            self._local.route = "hls-local" if self.residential else "hls-ffmpeg"
            try:
                if self.residential:
                    # ffmpeg cannot authenticate against this proxy (it answers the CONNECT with a lowercase
                    # «proxy-authenticate: basic» that ffmpeg does not parse): the segments come down here, through
                    # the sticky session, and ffmpeg only cuts local files
                    return self._fetch_hls_locally(video_id, start, end, hls, prefix, audio, audio_only, info_path)
                return self._fetch_range(video_id, start, end, hls, prefix, audio, audio_only, info_path, exact=True)
            except (RuntimeError, SourceUnavailable) as error:
                if isinstance(error, SourceUnavailable) or "format is not available" not in str(error).lower():
                    raise
                untested = _untested_hls(info_path)
                # sourcing.youtube.hls_retry_untested (off): the HLS formats of a video uploaded ≤ 2 days before
                # the extraction are «to be tested» and yt-dlp drops the ones whose test piece fails; the same
                # selection is tried again once without the test (no request: the extraction on disk), and only
                # if that fails too does the range go whole
                if untested and self.cfg.get("hls_retry_untested", False) and self.cfg.get("hls_format_test", True):
                    self._local.skip_format_test = True
                    try:
                        if self.residential:
                            result = self._fetch_hls_locally(video_id, start, end, hls, prefix, audio, audio_only, info_path)
                        else:
                            result = self._fetch_range(video_id, start, end, hls, prefix, audio, audio_only, info_path,
                                                       exact=True)
                        self._local.route = f"{self._local.route}-sin-prueba"
                        return result
                    except (RuntimeError, SourceUnavailable) as again:
                        if isinstance(again, SourceUnavailable) or "format is not available" not in str(again).lower():
                            raise
                    finally:
                        self._local.skip_format_test = False
                why = " (HLS por probar)" if untested else ""
                self._local.not_hls = f"ningún formato HLS encaja con «{hls[:120]}»{why}"
                missed.add((video_id, hls))
        no_range = self.__dict__.setdefault("_no_range", set())
        if self.cfg.get("byte_ranges", False) and video_id not in no_range:
            # opt-in: the DASH mp4's own index says which bytes hold these seconds; only those come (byteranges.py)
            try:
                self._local.route = "rango-bytes"
                return self._fetch_byte_range(video_id, start, end, fmt, prefix, audio, audio_only, info_path)
            except NoIndex as error:
                no_range.add(video_id)          # its formats will not change: the next shots do not ask again (884 rows)
                self._local.route = None
                self._local.not_hls = f"{self._local.not_hls or 'sin HLS'}; sin rango de bytes: {error}"
        # two 403s in a row on whole downloads: this client/connection does not get them today (pati12 14/10: 403 on
        # every one, each a wasted request before the piece that works); straight to the piece for the rest of the run
        whole_off = getattr(self, "_whole_403", 0) >= 2
        if not audio_only and self.cfg.get("whole_fallback", True) and not whole_off:
            try:
                whole = self._fetch_whole(video_id, fmt, prefix, info_path)
                self._whole_403 = 0
            except SourceUnavailable:
                raise
            except Exception as error:     # the old way still works, only slower
                if "403" in str(error):
                    self._whole_403 = getattr(self, "_whole_403", 0) + 1
                    if self._whole_403 == 2:
                        print("   YouTube niega las descargas completas (403): el resto, solo el tramo que hace falta")
                print(f"   yt:{video_id}: descarga completa no disponible ({str(error)[:120]}); voy por tramo")
                whole = None
            if whole is not None:
                self._local.route = "entero"
                return self._cut(whole, video_id, start, end, prefix, audio)
        if self.residential:
            # the HTTPS range goes through ffmpeg, which cannot authenticate against this proxy: nothing left to try
            raise RuntimeError(f"yt-dlp download: {video_id} no tiene HLS y entero supera el tope del proxy residencial "
                               f"({self._whole_caps()[1]:g} MB / {self._whole_caps()[0]:g} min, whole_max_*_residential); "
                               "se pasa al siguiente candidato")
        self._local.route = "https-ffmpeg"
        return self._fetch_range(video_id, start, end, fmt, prefix, audio, audio_only, info_path, exact=False)

    def _why_no_hls(self, video_id: str, info_path: Path) -> str:
        """Why this extraction has no m3u8 format, from what is on disk (no request)."""

        import json

        try:
            data = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "sin ytdlp-info.json legible"
        formats = data.get("formats") or []
        protocols = sorted({str(f.get("protocol") or "?") for f in formats})
        cached = {}
        try:
            cached = json.loads(self._info_path(video_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        said = " (info.json decía que sí)" if cached.get("hls") else ""
        return (f"la extracción no trae m3u8{said}: {len(formats)} formatos, protocolos {', '.join(protocols) or '—'}, "
                f"clientes {','.join(data.get('_edit_vid3_clients') or []) or 'por defecto'}")

    def _whole_caps(self) -> tuple[float, float]:
        """(minutes, MB) a video may have to be downloaded whole for one clip: sourcing.youtube.whole_max_minutes (30)
        and whole_max_mb (600) at home; whole_max_minutes_residential (10) and whole_max_mb_residential (80) through a
        paid proxy."""

        if self.residential:
            return (float(self.cfg.get("whole_max_minutes_residential", 10)), float(self.cfg.get("whole_max_mb_residential", 80)))
        return (float(self.cfg.get("whole_max_minutes", 30)), float(self.cfg.get("whole_max_mb", 600)))

    HD_FORMAT = "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/b[height<=1080]"   # = ingest's default

    def hd_unreachable(self, video_id: str, info_path: Path) -> str | None:
        """Why the HD clip of this video could never come through the residential proxy (no HLS, and the whole file
        over whole_max_*_residential), or None. Asked before the 360p analysis: elcrimendepazos (13/11) analysed and
        chose dozens of clips of such videos for 113 min, and every one was refused at «Descargar en HD»."""

        import json

        if not self.residential or _has_hls(info_path):
            return None
        if self.cfg.get("byte_ranges", False) and self._has_dash_mp4(info_path):
            return None                          # its ranges come by byte ranges, whatever its length
        max_minutes, max_mb = self._whole_caps()
        data = json.loads(info_path.read_text(encoding="utf-8"))
        duration = float(data.get("duration") or 0)
        if duration > 60 * max_minutes:
            return f"dura {duration / 60:.0f} min (> {max_minutes:g} min)"
        fmt = cap_fps(cap_height(self.HD_FORMAT, self.cfg.get("max_height", 720)), self.cfg.get("max_fps", 30))
        try:
            with self._ydl({"format": whole_format(fmt), "simulate": True, "quiet": True}) as ydl:
                chosen = ydl.process_ie_result(selectable(data), download=False)
        except Exception as error:
            print(f"   yt:{video_id}: no se pudo estimar el tamaño en HD ({type(error).__name__}: {str(error)[:100]})")
            return None                          # yt-dlp cannot tell: let the download find out, as before
        pieces = chosen.get("requested_formats") or [chosen]
        size = sum(float(f.get("filesize") or f.get("filesize_approx") or 0) for f in pieces)
        return f"pesa {size / 1e6:.0f} MB en HD (> {max_mb:g} MB)" if size > 1e6 * max_mb else None

    @staticmethod
    def _has_dash_mp4(info_path: Path) -> bool:
        import json

        try:
            formats = json.loads(info_path.read_text(encoding="utf-8")).get("formats") or []
        except (OSError, ValueError):
            return False
        return any(f.get("protocol") == "https" and f.get("ext") == "mp4" and f.get("vcodec") not in (None, "none")
                   for f in formats)

    def _check_hd_reachable(self, video_id: str, info_path: Path) -> None:
        why = self.hd_unreachable(video_id, info_path)
        if why:
            self._whole_skipped(video_id, why)
            raise RuntimeError(f"yt-dlp download: {video_id} descartado antes de analizarlo ({self._refusal_text('sin-hls')}); "
                               "se pasa al siguiente candidato")

    def _whole_skipped(self, video_id: str, why: str) -> None:
        if self.residential:
            self._refuse(video_id, "sin-hls")        # the formats will not change: no shot asks for it again
            print(f"   yt:{video_id}: sin HLS y {why}: no se baja entero por el proxy residencial; siguiente candidato "
                  "(y no se vuelve a pedir)")

    def _library_range(self, target_dir: Path, prefix: str, suffix: str, start: float, end: float,
                       wanted: int | None) -> Path | None:
        """A range already on disk that covers [start, end]: of this prefix, or a richer one of the same video
        (RANGE_FAMILY), as long as it is at least as tall as asked for — or was downloaded under the same or a higher
        cap, so the source has no more to give. Legacy ranges without a sidecar count as before. The cache is shared
        by every video of the machine: a range another project already paid for never crosses the proxy again."""

        candidates: list[tuple[int, Path]] = []
        for rank, family in enumerate(RANGE_FAMILY.get(prefix, (prefix,))):
            for existing in target_dir.glob(f"{family}_*{suffix}"):
                try:
                    _, a, b = existing.stem.split("_")
                    if not (float(a) <= start + 1e-3 and float(b) >= end - 1e-3):
                        continue
                except ValueError:
                    continue
                side = self._range_sidecar(existing)
                if not side and not self._legacy_range_ok(existing, suffix):
                    continue
                height, cap = side.get("height"), side.get("cap")
                tall_enough = wanted is None or height is None or int(height) >= wanted or (cap is not None and int(cap) >= wanted)
                if tall_enough:
                    candidates.append((rank, existing))
        return min(candidates, key=lambda c: (c[0], c[1].name))[1] if candidates else None

    def _legacy_range_ok(self, path: Path, suffix: str) -> bool:
        """A range from before the atomic writes (no sidecar): it may be the truncated output of an ffmpeg killed half
        way. Checked once with ffprobe; a good one gets a neutral sidecar (same library behaviour as before), a bad
        one is deleted so it is downloaded again."""

        try:
            _, a, b = path.stem.split("_")
            span = float(b) - float(a)
        except ValueError:
            span = None
        problem = media_problem(path, video=suffix != ".m4a", seconds=span, tolerance=max(1.0, 0.2 * (span or 0)))
        if problem:
            print(f"   {path.parent.name}/{path.name}: tramo de la caché roto ({problem}); se borra y se vuelve a bajar")
            path.unlink(missing_ok=True)
            return False
        try:
            path.with_suffix(path.suffix + ".json").write_text('{"height": null, "cap": null, "checked": true}',
                                                               encoding="utf-8")
        except OSError:
            pass
        return True

    @staticmethod
    def _range_sidecar(path: Path) -> dict[str, Any]:
        import json

        try:
            data = json.loads(path.with_suffix(path.suffix + ".json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write_range_sidecar(path: Path, *, height: int | None, cap: int | None) -> None:
        """<range>.mp4.json: the source height of the range and the cap it was asked with (the library's key)."""

        import json

        try:
            path.with_suffix(path.suffix + ".json").write_text(json.dumps({"height": height, "cap": cap}), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _probe_height(path: Path) -> int | None:
        import json
        import subprocess

        try:
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height",
                                    "-of", "json", str(path)], capture_output=True, text=True, env=local_env(), timeout=60)
            return int((json.loads(probe.stdout or "{}").get("streams") or [{}])[0].get("height") or 0) or None
        except (OSError, ValueError, TypeError, IndexError, subprocess.SubprocessError):
            return None

    def _fetch_hls_locally(self, video_id: str, start: float, end: float, fmt: str, prefix: str, audio: bool,
                           audio_only: bool, info_path: Path) -> Path:
        """[start, end] from the HLS stream yt-dlp would choose, without ffmpeg ever touching the network: the media
        playlist and only the segments covering the range are fetched here (requests, through this video's sticky
        session, so the proxy authenticates and the IP matches the URLs), written as a local playlist, and ffmpeg
        cuts those seconds exactly. Stale links (403/410) are refreshed once, like the ffmpeg path.

        Segments come `hls_segment_workers` (3) at a time, each retried `hls_segment_retries` (2) times on a passing
        error, streamed to disk; those already down are kept for the retry with fresh links."""

        import json
        import shutil
        import subprocess
        from urllib.parse import urljoin

        target_dir = self.cache_dir / "videos" / video_id
        suffix = ".m4a" if audio_only else ".mp4"
        work = part_for(target_dir / f"hls_{prefix}_{start:.2f}_{end:.2f}")      # this process's own folder

        def choose(path: Path) -> list[dict[str, Any]]:
            """The HLS pieces yt-dlp would take: one (muxed, or video/audio only) or two (video track + audio track)."""

            data = json.loads(path.read_text(encoding="utf-8"))
            with self._ydl({"format": fmt, "simulate": True, "quiet": True}) as ydl:
                chosen = ydl.process_ie_result(selectable(data), download=False)
            pieces = list(chosen.get("requested_formats") or [chosen])[:2]
            if not pieces or not all(str(p.get("protocol") or "").startswith("m3u8") for p in pieces):
                raise RuntimeError("yt-dlp download (HLS): Requested format is not available (no HLS stream)")
            return pieces

        stale = object()                     # the session (exit IP) changed since the links were extracted
        workers = max(1, int(self.cfg.get("hls_segment_workers", 3)))
        retries = max(0, int(self.cfg.get("hls_segment_retries", 2)))

        def session_now() -> str | None:
            return self.sessions.session_id(self._session_key()) if self.residential else None

        def fetch(pieces: list[dict[str, Any]], session_at: str | None) -> Any:
            if session_now() != session_at:
                # a rotation (bot, 429, tunnel) moved this video to another IP: its URLs belong to the old one, and
                # trying them from the new IP is a paid 403 for sure — extract again first (outside this request)
                return stale
            return [fetch_piece(piece) for piece in pieces]      # [(start of its first segment, local playlist)]

        def fetch_piece(piece: dict[str, Any]) -> tuple[float, Path]:
            way = getattr(self._local, "way", 0) or 0
            headers = {k: str(v) for k, v in (piece.get("http_headers") or {}).items()}
            proxies = self._requests_proxies(way)
            moved = [0]
            moved_lock = threading.Lock()

            def fail(response: requests.Response) -> None:
                raise RuntimeError(f"yt-dlp download (HLS): HTTP Error {response.status_code}: {response.reason}")

            def get(url: str) -> bytes:
                """The media playlist or the init segment: a passing error (a 502 of the proxy's tunnel, a cut
                connection) is asked again in the same session, like the segments (27-11: one 502 lost the clip)."""

                for attempt in range(retries + 1):
                    try:
                        response = self._sessions[way].get(url, headers=headers, timeout=60, proxies=proxies)
                        content = response.content
                    except TRANSIENT_ERRORS as error:
                        if attempt >= retries:
                            raise RuntimeError(f"yt-dlp download (HLS): {type(error).__name__}: {error}") from None
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    if response.status_code in TRANSIENT_STATUS and attempt < retries:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    if response.status_code >= 400:
                        fail(response)
                    with moved_lock:
                        moved[0] += len(content)
                    return content
                raise AssertionError("inalcanzable")

            def segment(url: str, path: Path) -> Path:
                """One segment to disk, streamed (never whole in memory), retried on a passing error; one already
                on disk from an earlier attempt of this range is kept."""

                if path.is_file() and path.stat().st_size > 0:
                    return path
                for attempt in range(retries + 1):
                    partial = path.with_name(path.name + ".part")
                    try:
                        with self._sessions[way].get(url, headers=headers, timeout=60, proxies=proxies,
                                                     stream=True) as response:
                            if response.status_code >= 400:
                                fail(response)
                            size = 0
                            with partial.open("wb") as handle:
                                for block in response.iter_content(256 * 1024):
                                    handle.write(block)
                                    size += len(block)
                        if size == 0:
                            raise RuntimeError("yt-dlp download (HLS): segmento vacío")
                        partial.replace(path)
                        with moved_lock:
                            moved[0] += size
                        return path
                    except (requests.RequestException, RuntimeError) as error:
                        partial.unlink(missing_ok=True)
                        text = str(error)
                        if any(code in text for code in ("HTTP Error 403", "HTTP Error 410", "HTTP Error 404")) \
                                or attempt >= retries:
                            raise RuntimeError(text if text.startswith("yt-dlp") else f"yt-dlp download (HLS): {text}") \
                                from None
                        time.sleep(0.5 * (attempt + 1))
                raise AssertionError("inalcanzable")

            try:
                playlist_url = str(piece["url"])
                segments, init_url = parse_media_playlist(get(playlist_url).decode("utf-8", "replace"), playlist_url)
                if not segments:
                    raise RuntimeError("yt-dlp download (HLS): empty media playlist")
                wanted = [seg for seg in segments if seg[2] > start + 1e-3 and seg[1] < end - 1e-3]
                if not wanted:
                    raise RuntimeError(f"yt-dlp download (HLS): no segment covers {start:.1f}-{end:.1f} s")
                work.mkdir(parents=True, exist_ok=True)
                tag = re.sub(r"[^A-Za-z0-9]", "", str(piece.get("format_id") or "f"))[:12]
                init_path = None
                if init_url:
                    init_path = work / f"init_{tag}.mp4"
                    if not init_path.is_file():
                        init_path.write_bytes(get(urljoin(playlist_url, init_url)))
                # a few segments at once through the same session: bytes of a video already extracted, not new requests
                # for its details (the pace and the hourly budget count this download as one request, as before)
                names = [work / f"seg_{tag}_{a:.3f}.ts" for _, a, _ in wanted]
                with ThreadPoolExecutor(max_workers=min(workers, len(wanted))) as pool:
                    paths = list(pool.map(segment, [urljoin(playlist_url, url) for url, _, _ in wanted], names))
            finally:
                self._local.proxy_bytes = getattr(self._local, "proxy_bytes", 0) + moved[0]
            # one file, the segments one after the other (MPEG-TS and fragmented mp4 both join byte by byte), cut
            # with an exact seek: through a local m3u8 the HLS demuxer seeked wrong in segments that keep the
            # source's timestamps (832 s…) with one keyframe each — clips came out empty or 1.3 s of 3.7 (22-11)
            joined = join_segments(paths, init_path, work / f"joined_{tag}{'.mp4' if init_path is not None else '.ts'}")
            return wanted[0][1], joined

        def attempt(pieces: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
            for _ in range(3):
                session_at = session_now()
                got = self._call("download (HLS)", lambda: fetch(pieces, session_at))
                if got is not stale:
                    return got, pieces
                pieces = choose(self._fresh_full_info(video_id))     # the new session's own links
            raise RuntimeError("yt-dlp download (HLS): la sesión del proxy cambió de IP tres veces seguidas")

        pieces = choose(info_path)
        try:
            try:
                inputs, pieces = attempt(pieces)
            except RuntimeError as error:
                if not any(code in str(error) for code in ("HTTP Error 403", "HTTP Error 410", "HTTP Error 404")):
                    raise
                self._full_info_path(video_id).unlink(missing_ok=True)      # stale links: fresh ones, once more
                inputs, pieces = attempt(choose(self._fresh_full_info(video_id)))
            target = target_dir / f"{prefix}_{start:.3f}_{end:.3f}{suffix}"
            part = part_for(target)                    # the final name only once it is complete and checked
            command = local_cut_command(inputs, start, end, prefix, audio, audio_only, part)
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=600, env=local_env())
            except subprocess.TimeoutExpired:
                part.unlink(missing_ok=True)
                raise RuntimeError("yt-dlp download (HLS): el corte local tardó más de 10 min") from None
            if done.returncode != 0 or not part.is_file() or part.stat().st_size == 0:
                part.unlink(missing_ok=True)
                words = " ".join((done.stderr or "").split())[:200]
                raise RuntimeError(f"yt-dlp download (HLS): el corte local falló: {words or f'ffmpeg código {done.returncode}'}")
            if not audio_only:
                height = next((p.get("height") for p in pieces if p.get("vcodec") not in (None, "none")),
                              pieces[0].get("height"))
                self._write_range_sidecar(target, height=int(height) if height else None, cap=requested_height(fmt))
            self._publish(part, target, video=not audio_only, seconds=end - start, what="HLS")
            return target
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _fetch_byte_range(self, video_id: str, start: float, end: float, fmt: str, prefix: str, audio: bool,
                          audio_only: bool, info_path: Path) -> Path:
        """[start, end] of a DASH mp4 by HTTP byte ranges (see byteranges.py): the first KB give the index, then only
        the fragments covering the seconds, through this video's session, and ffmpeg cuts locally. NoIndex when the
        format is not an indexed mp4 (webm, no sidx): the caller goes on as before."""

        import subprocess

        def choose(path: Path) -> list[dict[str, Any]]:
            return self._range_formats(path, fmt, audio, audio_only)

        target_dir = self.cache_dir / "videos" / video_id
        work = part_for(target_dir / f"br_{prefix}_{start:.2f}_{end:.2f}")
        margin = 0.0

        def fetch(pieces_: list[dict[str, Any]]) -> list[tuple[Path, Plan]]:
            way = getattr(self._local, "way", 0) or 0
            proxies = self._requests_proxies(way)

            answer: dict[str, Any] = {}

            def get(url: str, headers: dict[str, str], first: int, last: int) -> bytes:
                body, answer["status"], answer["type"] = self._range_get(way, proxies, url, headers, first, last)
                return body

            out = []
            work.mkdir(parents=True, exist_ok=True)
            planned = []
            # every track's index first: an audio that cannot be cut must not cost the video's megabytes (22-11:
            # ~23 MB of AV1 per attempt, paid and thrown away when the opus audio came)
            for n, piece in enumerate(pieces_):
                url = str(piece["url"])
                headers = {k: str(v) for k, v in (piece.get("http_headers") or {}).items()}
                head = get(url, headers, 0, 64 * 1024 - 1)
                try:
                    if head[:4] == EBML_MAGIC:
                        raise NoIndex("llega un webm (Matroska) aunque se pidió mp4")
                    need = needed_head(head)
                    if need is not None and need > len(head):
                        if need > 4 * 1024 * 1024:
                            raise NoIndex(f"índice demasiado grande ({need / 1e6:.1f} MB)")
                        head += get(url, headers, len(head), need - 1)
                    cut = plan(head, start, end, margin=margin)
                except NoIndex as error:      # what came, so one row of the log says why (descargas-rango-fallo.md)
                    raise NoIndex(f"{error} · {range_diagnosis(piece, answer.get('status'), answer.get('type'), head)}") \
                        from None
                size_mb = (cut.data[1] - cut.data[0] + 1) / 1e6
                limit_mb = float(self.cfg.get("range_max_mb", 25))
                if size_mb > limit_mb:
                    # a coarse index (a few huge fragments: 33 MB for 5 s of 4K AV1) is dearer than any other way
                    raise NoIndex(f"el tramo pediría {size_mb:.0f} MB (> {limit_mb:g} MB, range_max_mb): índice demasiado "
                                  f"grueso · {range_diagnosis(piece, answer.get('status'), answer.get('type'), head)}")
                planned.append((n, url, headers, head, cut))
            for n, url, headers, head, cut in planned:
                path = work / f"pista{n}.mp4"
                with path.open("wb") as handle:
                    handle.write(head[cut.init[0]:cut.init[1] + 1])
                    for a, b in byte_pieces(*cut.data):
                        handle.write(get(url, headers, a, b))
                out.append((path, cut))
            return out

        pieces_ = choose(info_path)
        try:
            try:
                tracks = self._call("download (rango)", lambda: fetch(pieces_))
            except RuntimeError as error:
                if not any(code in str(error) for code in ("HTTP Error 403", "HTTP Error 410", "HTTP Error 404")):
                    raise
                self._full_info_path(video_id).unlink(missing_ok=True)      # stale links: fresh ones, once more
                pieces_ = choose(self._fresh_full_info(video_id))
                tracks = self._call("download (rango)", lambda: fetch(pieces_))
            suffix = ".m4a" if audio_only else ".mp4"
            target = target_dir / f"{prefix}_{start:.3f}_{end:.3f}{suffix}"
            part = part_for(target)
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
            for path, cut in tracks:
                command += ["-ss", f"{max(0.0, start - cut.start):.3f}", "-i", str(path)]
            command += ["-t", f"{end - start:.3f}"]
            if audio_only:
                command += ["-map", "0:a:0", "-vn", "-c:a", "aac", "-b:a", "160k", str(part)]
            else:
                command += ["-map", "0:v:0", *(["-map", "1:a:0", "-c:a", "aac"] if audio and len(tracks) > 1 else ["-an"]),
                            *cut_codec(prefix), "-pix_fmt", "yuv420p", str(part)]
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=600, env=local_env())
            except subprocess.TimeoutExpired:
                part.unlink(missing_ok=True)
                raise RuntimeError("yt-dlp download (rango): el corte local tardó más de 10 min") from None
            if done.returncode != 0:
                part.unlink(missing_ok=True)
                words = " ".join((done.stderr or "").split())[:200]
                raise RuntimeError(f"yt-dlp download (rango): el corte local falló: {words or done.returncode}")
            if not audio_only:
                height = pieces_[0].get("height")
                self._write_range_sidecar(target, height=int(height) if height else None, cap=requested_height(fmt))
            self._publish(part, target, video=not audio_only, seconds=end - start, what="rango")
            return target
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _range_formats(self, info_path: Path, fmt: str, audio: bool, audio_only: bool) -> list[dict[str, Any]]:
        """The DASH mp4 formats (video, and m4a audio when asked) a byte range would read, as yt-dlp picks them."""

        import json

        data = json.loads(info_path.read_text(encoding="utf-8"))
        if audio_only:
            request = "ba[ext=m4a][protocol=https]"
        else:
            video = "/".join(dict.fromkeys(f"{alt.split('+')[0]}[ext=mp4][protocol=https]"
                                           for alt in fmt.split("/") if alt.strip() and not alt.startswith("ba")))
            request = f"({video})+ba[ext=m4a][protocol=https]" if audio else video
        try:
            with self._ydl({"format": request, "simulate": True, "quiet": True}) as ydl:
                chosen = ydl.process_ie_result(selectable(data), download=False)
        except Exception as error:
            raise NoIndex(f"sin formato mp4 por HTTPS ({str(error)[:80]})") from None
        pieces = list(chosen.get("requested_formats") or [chosen])
        for piece in pieces:                   # checked before a single byte is asked for
            if piece.get("ext") not in ("mp4", "m4a") or piece.get("protocol") != "https":
                raise NoIndex(f"el formato elegido no es mp4/m4a por HTTPS (itag {piece.get('format_id')}, "
                              f"{piece.get('ext')}, {piece.get('protocol')})")
        return pieces

    def _range_get(self, way: int, proxies: Any, url: str, headers: dict[str, str], first: int,
                   last: int) -> tuple[bytes, int, str]:
        """bytes [first, last] of a format's URL through this video's session: (body, HTTP code, Content-Type).

        A passing error (a 502 of the proxy's tunnel, a connection cut halfway) is asked again in the same session,
        `range_retries` (2) times, for the bytes still missing only (27-11: one cut lost the clip). A refusal
        (403/404/410) is never asked again here: the caller refreshes the links."""

        wanted = last - first + 1
        retries = max(0, int(self.cfg.get("range_retries", 2)))
        body = bytearray()
        status, kind, attempts = 0, "", 0
        while len(body) < wanted:
            low = first + len(body)
            try:
                response = self._sessions[way].get(url, headers={**headers, "Range": f"bytes={low}-{last}"},
                                                   timeout=60, proxies=proxies, stream=True)
            except TRANSIENT_ERRORS as error:
                if attempts >= retries:
                    raise RuntimeError(f"yt-dlp download (rango): {type(error).__name__}: {error}") from None
                attempts += 1
                time.sleep(0.5 * attempts)
                continue
            got = 0
            try:
                status, kind = response.status_code, str(response.headers.get("Content-Type") or "")
                if status in TRANSIENT_STATUS and attempts < retries:
                    attempts += 1
                    time.sleep(0.5 * attempts)
                    continue
                if status >= 400:
                    raise RuntimeError(f"yt-dlp download (rango): HTTP Error {status}: {response.reason}")
                if status != 206 and low > 0:
                    raise NoIndex(f"el servidor no atiende peticiones Range (HTTP {status} {kind})")
                try:
                    for block in response.iter_content(256 * 1024):
                        body += block
                        got += len(block)
                        if len(body) >= wanted:
                            break
                except TRANSIENT_ERRORS as error:
                    if attempts >= retries:
                        raise RuntimeError(f"yt-dlp download (rango): cortado a {len(body)} de {wanted} bytes "
                                           f"({type(error).__name__})") from None
                    attempts += 1
                    time.sleep(0.5 * attempts)
                    continue
            finally:
                response.close()
                self._local.proxy_bytes = getattr(self._local, "proxy_bytes", 0) + got
            break                     # complete, or the file ended before `last` (the caller decides)
        return bytes(body[:wanted]), status, kind

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
        # Through a paid residential proxy a whole video for a 5 s clip is the costliest thing this program does
        # (330 MB seen for one clip): much lower caps there, and past them the shot takes its next candidate.
        max_minutes, max_mb = self._whole_caps()
        if float(data.get("duration") or 0) > 60 * max_minutes:
            self._whole_skipped(video_id, f"dura {float(data.get('duration') or 0) / 60:.0f} min (> {max_minutes:g} min)")
            return None
        fmt = whole_format(fmt)
        with self._ydl({"format": fmt, "simulate": True, "quiet": True}) as ydl:
            chosen = ydl.process_ie_result(selectable(data), download=False)
        pieces = chosen.get("requested_formats") or [chosen]
        if any(str(f.get("protocol") or "").startswith(("m3u8", "http_dash")) for f in pieces):
            return None
        size = sum(float(f.get("filesize") or f.get("filesize_approx") or 0) for f in pieces)
        if size > 1e6 * max_mb:
            self._whole_skipped(video_id, f"pesa {size / 1e6:.0f} MB (> {max_mb:g} MB)")
            return None
        if self.residential:
            print(f"   yt:{video_id}: sin HLS; se baja entero por el proxy ({size / 1e6:.0f} MB) para cortar el tramo")
        # two clips of one video, in this process or in another video's process: one download (an flock per video)
        with file_lock(target_dir / f".lock-full_{prefix}"):
            done = next(iter(sorted(target_dir.glob(f"full_{prefix}.*"))), None)
            if done is not None and done.suffix in (".mp4", ".mkv", ".webm"):
                return done
            target_dir.mkdir(parents=True, exist_ok=True)
            wip = part_for(target_dir / f"wip_{prefix}.mp4").with_suffix("")      # this process's own name
            options = {"format": fmt, "outtmpl": str(wip) + ".%(ext)s", "overwrites": True,
                       "http_chunk_size": 10 * 1024 * 1024, "merge_output_format": "mp4", "concurrent_fragment_downloads": 1,
                       **self._whole_deadline(size)}

            def fetch() -> None:
                with self._ydl(options) as ydl:
                    ydl.download_with_info_file(str(info_path))

            try:
                self._call("download (completo)", fetch)
            except BaseException:
                for leftover in target_dir.glob(f"{wip.name}.*"):
                    leftover.unlink(missing_ok=True)
                raise
            produced = [p for p in target_dir.glob(f"{wip.name}.*") if p.stem == wip.name and p.suffix in (".mp4", ".mkv", ".webm")]
            for leftover in target_dir.glob(f"{wip.name}.*"):          # the separate video/audio pieces
                if leftover not in produced:
                    leftover.unlink(missing_ok=True)
            if not produced:
                return None
            final = target_dir / f"full_{prefix}{produced[0].suffix}"
            duration = float(data.get("duration") or 0) or None
            self._publish(produced[0], final, video=True, seconds=duration, what="completo")
            return final

    def _whole_deadline(self, size_bytes: float) -> dict[str, Any]:
        """yt-dlp options so a whole download can never hang a stage: a connection crawling under
        `whole_min_rate_kb` (100 KB/s) is dropped and retried (throttledratelimit: yt-dlp re-extracts), each
        fragment/chunk retries `fragment_retries` (5) times, and the whole download stops after a total time
        proportional to its size (`whole_deadline_seconds_per_mb`, 6 s/MB, plus 2 min)."""

        options: dict[str, Any] = {"throttledratelimit": int(float(self.cfg.get("whole_min_rate_kb", 100)) * 1024),
                                   "fragment_retries": int(self.cfg.get("fragment_retries", 5))}
        if size_bytes <= 0:                  # size unknown: only the crawl detection, no total limit
            return options
        mb = size_bytes / 1e6
        limit = 120 + float(self.cfg.get("whole_deadline_seconds_per_mb", 6)) * mb
        deadline = time.monotonic() + limit

        def hook(status: dict[str, Any]) -> None:
            if status.get("status") == "downloading" and time.monotonic() > deadline:
                raise RuntimeError(f"yt-dlp download (completo): más de {limit:.0f} s para {mb:.0f} MB; se corta")

        return {**options, "progress_hooks": [hook]}

    def _cut(self, whole: Path, video_id: str, start: float, end: float, prefix: str, audio: bool) -> Path:
        """[start, end] of the downloaded source, cut exactly (re-encoding only those seconds)."""

        import subprocess

        target = self.cache_dir / "videos" / video_id / f"{prefix}_{start:.3f}_{end:.3f}.mp4"
        part = part_for(target)                        # the final name only once it is complete and checked
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{start:.3f}", "-i", str(whole),
                 "-t", f"{end - start:.3f}", "-map", "0:v:0", *(["-map", "0:a:0?", "-c:a", "aac"] if audio else ["-an"]),
                 *cut_codec(prefix), "-pix_fmt", "yuv420p", str(part)],
                check=True, env=local_env(), timeout=600,
            )
        except subprocess.TimeoutExpired:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"yt-dlp download: cortar {start:.1f}-{end:.1f} s de {video_id} tardó más de 10 min") from None
        except subprocess.CalledProcessError as error:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"yt-dlp download: ffmpeg no pudo cortar {start:.1f}-{end:.1f} s de {video_id} "
                               f"(código {error.returncode})") from None
        self._write_range_sidecar(target, height=self._probe_height(part), cap=self.cfg.get("max_height", 720))
        self._publish(part, target, video=True, seconds=end - start, what="corte")
        return target

    def _publish(self, part: Path, target: Path, *, video: bool, seconds: float | None, what: str) -> None:
        """`part` → `target` once ffprobe sees a whole clip (a picture, and at least ~80 % of the seconds asked: the
        source may end before `end`). Otherwise the RuntimeError names it and nothing reaches the cache."""

        try:
            publish(part, target, video=video, seconds=seconds, tolerance=max(1.0, 0.2 * (seconds or 0)))
        except RuntimeError as error:
            target.with_suffix(target.suffix + ".json").unlink(missing_ok=True)
            raise RuntimeError(f"yt-dlp download ({what}): {error}") from None

    def _fetch_range(self, video_id: str, start: float, end: float, fmt: str, prefix: str, audio: bool,
                     audio_only: bool, info_path: Path, *, exact: bool) -> Path:
        import json
        import subprocess

        from yt_dlp.utils import download_range_func

        target_dir = self.cache_dir / "videos" / video_id
        suffix = ".m4a" if audio_only else ".mp4"
        stream = "a:0" if audio_only else "v:0"
        raw = part_for(target_dir / f"dl_{prefix}_{start:.2f}_{end:.2f}.mp4")     # this process's own name
        options: dict[str, Any] = {
            "format": fmt,
            "outtmpl": str(raw.with_suffix(".%(ext)s")),
            "overwrites": True,
            "nopart": True,
            "download_ranges": download_range_func(None, [(start, end)]),
            "force_keyframes_at_cuts": exact,             # exact: the file starts right at `start`
        }
        info_file = str(info_path)

        def fetch() -> None:
            self._local.moved_unseen = True     # ffmpeg fetches the range: its bytes only show as the file's size
            with self._ydl({**options, "external_downloader_args": self._ffmpeg_args(exact)}) as ydl:
                ydl.download_with_info_file(info_file)

        def attempt() -> tuple[Path, dict[str, Any]] | None:
            try:
                self._call("download (HLS)" if exact else "download", fetch)
            except RuntimeError as error:
                if "ffmpeg exited with code" not in str(error):
                    raise
                # yt-dlp reports only the exit code (ffmpeg runs with -loglevel quiet): ask ffmpeg itself why
                raise RuntimeError(f"{error} — ffmpeg dice: {self._ffmpeg_diagnosis(info_file, fmt)}") from None
            produced = [p for p in target_dir.glob(f"{raw.stem}.*")
                        if p.suffix in (".mp4", ".webm", ".mkv", ".m4a", ".opus", ".weba", ".ts")]
            if not produced:
                return None
            try:
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", "stream=start_time,height:format=duration",
                     "-of", "json", str(produced[0])],
                    capture_output=True, text=True, env=local_env(), timeout=60,
                )
                info = json.loads(probe.stdout or "{}")
            except (ValueError, subprocess.SubprocessError):
                probe, info = None, {}
            if probe is None or probe.returncode != 0 or not info.get("streams") or not (info.get("format") or {}).get("duration"):
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
        part = part_for(target)                        # the final name only once it is complete and checked
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(produced[0]), "-map", f"0:{stream}",
                 *(["-map", "0:a:0?"] if audio and not audio_only else []),
                 "-c", "copy", "-avoid_negative_ts", "make_zero", str(part)],
                check=True, env=local_env(), timeout=300,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            part.unlink(missing_ok=True)
            produced[0].unlink(missing_ok=True)
            raise RuntimeError(f"yt-dlp download: el remux del tramo falló ({type(error).__name__})") from None
        produced[0].unlink(missing_ok=True)
        if not audio_only:
            height = info["streams"][0].get("height")
            self._write_range_sidecar(target, height=int(height) if height else None, cap=requested_height(fmt))
        self._publish(part, target, video=not audio_only, seconds=None, what="tramo")
        return target

    def _ffmpeg_args(self, exact: bool) -> dict[str, list[str]]:
        """Input/output arguments for the ffmpeg yt-dlp drives for a range (built when the request runs, so they
        carry the way out it was given).

        -rw_timeout: ffmpeg waits forever on a connection that stops answering (a proxy PC asleep mid-download hung
        instrum4 for 5 hours at 180/191); range_stall_seconds (60) without data and the piece fails instead.
        -http_proxy: yt-dlp hands ffmpeg the proxy only through the http_proxy environment variable, and ffmpeg
        ignores that variable for https:// (libavformat/http.c: `use_proxy = 0` for https; only the -http_proxy
        option reaches the TLS layer). So every googlevideo range left straight from this server, from an IP the
        stream URLs were not bound to: 403, «ffmpeg exited with code 8». The option carries the proxy, sticky
        session included; the HLS demuxer passes it on to every segment request."""

        # -loglevel error (after yt-dlp's -loglevel quiet; the last one wins): ffmpeg's errors reach the service log
        args: dict[str, list[str]] = {"ffmpeg_i": ["-loglevel", "error", "-nostats",
                                                   "-rw_timeout", str(int(float(self.cfg.get("range_stall_seconds", 60)) * 1e6))]}
        proxy = self.proxies[getattr(self._local, "way", 0) or 0] if self.proxies else ""
        if proxy:
            args["ffmpeg_i"] += ["-http_proxy", self._proxy_for(proxy)]
        if not exact:
            args["ffmpeg_o"] = ["-copyts"]
        return args

    def _ffmpeg_diagnosis(self, info_file: str, fmt: str) -> str:
        """ffmpeg's own words for a range that died with just an exit code: open the stream yt-dlp chose for half
        a second, with the same proxy (option and environment) and headers, and keep the error line. One small extra
        request, only after a failure, so «ffmpeg exited with code 8» stops hiding a 403, a DNS error or a bad proxy."""

        import json
        import subprocess

        try:
            data = json.loads(Path(info_file).read_text(encoding="utf-8"))
            with self._ydl({"format": fmt, "simulate": True, "quiet": True}) as ydl:
                chosen = ydl.process_ie_result(selectable(data), download=False)
            piece = (chosen.get("requested_formats") or [chosen])[0]
            url = piece.get("url")
            if not url:
                return "el formato elegido no tiene URL"
            headers = piece.get("http_headers") or chosen.get("http_headers") or {}
            inputs = self._ffmpeg_args(exact=True)["ffmpeg_i"]
            command = ["ffmpeg", "-hide_banner", "-nostdin", *inputs]
            if headers:
                command += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())]
            command += ["-i", url, "-t", "0.5", "-f", "null", "-"]
            env = local_env()
            if "-http_proxy" in inputs:                       # as yt-dlp hands it to ffmpeg: in the environment too
                env["http_proxy"] = env["HTTP_PROXY"] = inputs[inputs.index("-http_proxy") + 1]
            done = subprocess.run(command, capture_output=True, text=True, timeout=90, env=env)
            # the error lines, without the stream URLs (hundreds of characters of signature that say nothing)
            text = re.sub(r"https?://\S+", "<url>", " ".join((done.stderr or "").split()))
            text = re.sub(r"\[\w+ @ 0x[0-9a-f]+\] ", "", text)[:220]
            if done.returncode == 0:
                return "la misma URL abre bien ahora (¿enlace caducado o IP distinta en el intento?)"
            return text or f"salió con código {done.returncode} sin mensaje"
        except Exception as error:
            return f"no se pudo diagnosticar ({type(error).__name__}: {str(error)[:80]})"

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
            info_path = self._fresh_full_info(video_id)
            if self.residential and self.refused_why(video_id) in self._blocking_refusals():
                return False
            if self.hd_unreachable(video_id, info_path):
                return False                     # download_section says why (and the video is not asked for again)
            if self.residential and not self.cfg.get("prefetch_whole_residential", False) and _has_hls(info_path):
                # paid by the GB: the whole 360p file (13 MB on average) cost 60 % of gimnasia2's proxy (1.7 of
                # 2.8 GB, 124 videos) where its 3-6 windows by HLS come to a fraction; same 360p for the analysis
                return False
            return self._fetch_whole(video_id, self.SECTION_FORMAT, "a360", info_path) is not None
        except SourceUnavailable:
            raise
        except Exception as error:
            print(f"   yt:{video_id}: el vídeo entero a 360p no se pudo bajar ({type(error).__name__}: "
                  f"{str(error)[:100]}); van por tramos")
            return False

    # --- per shot ---------------------------------------------------------------------

    def queries_for(self, broll: BrollSpec) -> list[str]:
        queries = [
            *broll.queries[: int(self.cfg.get("queries_en", 2))],
            *broll.queriesLocal[: int(self.cfg.get("queries_local", 1))],
        ]
        if self.api is not None and self.cfg.get("api_concrete_query", True):
            # API quota: still `api_queries_per_shot` (2) searches — but the event's and the shot's MOST CONCRETE one
            # (the narrated moment, the full name, the year), the moment's first; before, the event's and the LLM's
            # first, whatever it was, and queries 2-5, the local one and placeQuery never ran
            event = broll.queries[0] if broll.event and broll.queries and \
                broll.queries[0].casefold() == broll.event.casefold() else None
            rest = list(broll.queries[1:] if event else broll.queries)
            concrete = most_concrete(rest, broll)
            picked = [concrete, event] if broll.moment else [event, concrete]
            queries = [q for q in picked if q][: int(self.cfg.get("api_queries_per_shot", 2))]
            if self.cfg.get("api_local_query", False):           # +1 search per shot: +100 units (off)
                queries += broll.queriesLocal[:1]
        elif self.api is not None:   # API quota: the event search + one more (~30k units a video instead of ~46k)
            queries = queries[: int(self.cfg.get("api_queries_per_shot", 2))]
        elif broll.placeQuery and self.cfg.get("place_queries", True):
            queries.append(broll.placeQuery)   # the news from where it happened (the same for the whole event: cached)
        return list(dict.fromkeys(self.merged(q) for q in queries))

    def merged(self, query: str) -> str:
        """The same search said another way («Simone Biles Amanar vault Rio 2016» / «… vault 2016 Rio Olympics»):
        the one an earlier shot of this video already asked, so the cache answers instead of YouTube
        (`query_merge`: how alike the words must be, 0 = off). Never across a different year or number."""

        limit = float(self.cfg.get("query_merge", 0.8) or 0)
        if limit <= 0:
            return query
        words = tokens(query)
        book = self.__dict__.setdefault("_query_book", [])
        lock = self.__dict__.setdefault("_query_lock", threading.Lock())
        with lock:
            for other, other_words in book:
                if other == query:
                    return query
                differ = words ^ other_words
                if words and other_words and not any(any(ch.isdigit() for ch in w) for w in differ) \
                        and len(words & other_words) / len(words | other_words) >= limit:
                    self.__dict__["merged_queries"] = self.__dict__.get("merged_queries", 0) + 1
                    return other
            book.append((query, words))
        return query

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

        from ..budget import ApiSearchesShort, BudgetReached

        try:
            info = self.info(video_id)
            if not self.passes_metadata_filters(info):
                return None
            why = self._undownloadable(info)
            if why:
                # no HLS and too big to come whole through the paid proxy: analysing it (its windows, its whole
                # file) would be paid for nothing, since the download refuses it anyway (gimnasia1: 13 shots)
                self._refuse(video_id, "sin-hls")
                notes.append(f"yt:{video_id}: {why}; descartado para el proxy residencial")
                return None
            board = self.storyboard(info)
        except (SourceUnavailable, ApiSearchesShort, BudgetReached):
            # the proxy down (ProxyDown) or the quota is the run's problem, not this video's: swallowed as a note
            # it made every shot «hard, give up» with six unanswered videos, cached as final (gym6.0: 257 shots)
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
        for video_id, entry in entries.items():
            scores[video_id] = scores.get(video_id, 0.0) + relevance_bonus(entry, broll)

        wanted = int(self.cfg.get("videos_per_shot", 3))
        # a hard shot (most results fail the filters: short, low resolution, refused) stops after a few videos'
        # details instead of asking for all of them: each one is a request YouTube may answer «are you a bot»
        tries = int(self.cfg.get("max_details_per_shot", 6) or 0) or len(entries)
        result: list[Candidate] = []
        for asked, video_id in enumerate(sorted(entries, key=lambda v: -scores.get(v, 0.0))):
            if len(result) >= wanted:
                break
            if asked >= tries:
                notes.append(f"{GAVE_UP}: {asked} vídeos mirados, {len(result)} válidos")
                break
            found = self.candidate(video_id, entries[video_id], scores.get(video_id, 0.0), notes)
            if found is not None:
                result.append(found)
        return result


GAVE_UP = "plano difícil, se deja de buscar"

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def most_concrete(queries: list[str], broll: BrollSpec) -> str | None:
    """The search that names the most of what this shot shows: the narrated moment's words, an entity's full name,
    the year (a tie keeps the planner's order)."""

    moment = tokens(broll.moment or "")
    names = [tokens(e) for e in broll.entities if tokens(e)]
    years = set(_YEAR.findall(" ".join([broll.event or "", broll.moment or "", *broll.queries])))

    def score(q: str) -> float:
        words = tokens(q)
        return (3 * len(words & moment) + 2 * sum(1 for n in names if n <= words)
                + (1 if years & set(_YEAR.findall(q)) else 0) + 0.1 * min(len(words), 8))

    return max(queries, key=lambda q: (score(q), -queries.index(q)), default=None)


def relevance_bonus(entry: dict[str, Any], broll: BrollSpec) -> float:
    """What the title (and, from the API, the description) say before paying an extraction: an entity's FULL name
    (one loose word of it gave the whole bonus before: «Simone» in any title), the event's words, the year."""

    entities = list(getattr(broll, "entities", None) or [])
    event_text, moment = str(getattr(broll, "event", None) or ""), str(getattr(broll, "moment", None) or "")
    queries = list(getattr(broll, "queries", None) or [])
    title = tokens(f"{entry.get('title') or ''} {entry.get('channel') or ''}")
    description = tokens(str(entry.get("description") or ""))
    bonus = 0.0
    for name in (tokens(e) for e in entities):
        if name and name <= title:
            bonus += 0.3
        elif name and name <= description:
            bonus += 0.12
    bonus = min(bonus, 0.45)
    event = tokens(event_text) - set(_YEAR.findall(event_text))
    for name in entities:
        event -= tokens(name)
    if event:
        bonus += 0.2 * len(event & title) / len(event)
    years = set(_YEAR.findall(" ".join([event_text, moment, *queries])))
    if years:
        said = set(_YEAR.findall(f"{entry.get('title') or ''} {entry.get('description') or ''}"))
        bonus += 0.1 if said & years else (-0.05 if said else 0.0)
    return bonus


def _parse_rate(value: str) -> int:
    match = re.fullmatch(r"\s*([\d.]+)\s*([kKmM]?)\s*", value)
    if not match:
        raise ValueError(f"youtube.rate_limit inválido: {value!r} (usa p. ej. '2M' o '500K')")
    number = float(match.group(1))
    factor = {"": 1, "k": 1024, "m": 1024 * 1024}[match.group(2).lower()]
    return int(math.floor(number * factor))
