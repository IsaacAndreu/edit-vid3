"""Helpers shared by every sourcing backend: polite HTTP, search cache, rank fusion."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

import requests


USER_AGENT = "edit-vid3/0.1 (documentary video pipeline; https://github.com/IsaacAndreu/edit-vid3)"


class SourceUnavailable(RuntimeError):
    """The backend refuses service for the rest of the run (blocked, quota exhausted...)."""


class Pacer:
    """Minimum interval between requests to one backend, safe across threads."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            delay = self._last + self._min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


class SharedPacer(Pacer):
    """The same minimum interval, shared by every process on the machine (two videos at once in the queue, the
    radar…): YouTube sees one steady pace from this IP, not one per process. A file holds the last request time,
    under an exclusive lock. Where file locks do not exist (Windows), it is a plain Pacer."""

    def __init__(self, min_interval: float, path: Path) -> None:
        super().__init__(min_interval)
        self._path = path

    def wait(self) -> None:
        try:
            import fcntl
        except ImportError:
            return super().wait()
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a+") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    handle.seek(0)
                    try:
                        last = float(handle.read().strip() or 0)
                    except ValueError:
                        last = 0.0
                    delay = last + self._min_interval - time.time()
                    if delay > 0:
                        time.sleep(min(delay, self._min_interval))
                    handle.seek(0)
                    handle.truncate()
                    handle.write(f"{time.time():.3f}")
                    handle.flush()
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)


def http_get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    pacer: Pacer | None = None,
    attempts: int = 4,
    timeout: float = 30,
) -> Any:
    last_error = ""
    for attempt in range(attempts):
        if pacer:
            pacer.wait()
        try:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as error:
            last_error = f"{type(error).__name__}"
        else:
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "")
                if attempt == attempts - 1:
                    raise SourceUnavailable(f"{url}: límite de peticiones agotado (429)")
                time.sleep(min(60.0, float(retry_after) if retry_after.isdigit() else 5.0 * 2**attempt))
                continue
            if response.status_code < 400:
                try:
                    return response.json()
                except ValueError:
                    last_error = "respuesta no JSON"
            else:
                last_error = f"HTTP {response.status_code}"
                if 400 <= response.status_code < 500 and response.status_code != 408:
                    break
        time.sleep(1.5 * 2**attempt)
    raise RuntimeError(f"{url}: {last_error}")


def download_file(session: requests.Session, url: str, target: Path, *, pacer: Pacer | None = None) -> Path:
    if target.is_file() and target.stat().st_size > 0:
        return target
    if pacer:
        pacer.wait()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    with session.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(1 << 16):
                handle.write(chunk)
    tmp.replace(target)
    return target


def cached_json(cache_file: Path, producer: Callable[[], Any]) -> Any:
    """Return cache_file's JSON, or produce, store and return it."""

    if cache_file.is_file():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    value = producer()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_name(cache_file.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(cache_file)
    return value


def key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def tokens(text: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return {t for t in re.findall(r"[a-z0-9]+", plain) if len(t) > 2}


def fuse_ranks(result_lists: list[list[str]]) -> dict[str, float]:
    """Reciprocal-rank fusion: items found early and by several queries rank higher."""

    scores: dict[str, float] = {}
    for results in result_lists:
        for rank, item in enumerate(results):
            scores[item] = scores.get(item, 0.0) + 1.0 / (rank + 3)
    return scores


def strip_html(text: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", text or "").split())


DEFAULT_TITLE_BLOCKLIST = (
    "gta", "gameplay", "walkthrough", "let's play", "lets play", "playthrough", "minecraft", "roblox",
    "fortnite", "red dead", "videojuego", "video game", "sims 4", "simulator", "speedrun",
)


# Always out, whatever the channel's own list says: footage that is never on topic in a documentary, or that brings
# a Content ID claim (negocios1 on 05-10 had «The Office», JoBlo movie clips, a kids' music channel and EDM Nation).
ALWAYS_BLOCKED_TERMS = ("asmr", "nursery rhymes", "kids music", "canciones infantiles", "movie clip", "full episode",
                        "official trailer", "tráiler oficial", "lyrics video", "lyric video")
ALWAYS_BLOCKED_CHANNELS = ("the office", "joblo", "movieclips", "kiboomers", "cocomelon", "super simple songs",
                           "edm nation", "rancho humilde", "netflix", "hbo max", "disney plus", "warner bros")


LEARNED_BLOCKED_CHANNELS: set[str] = set()     # from your «Errores» labels (feedback.load_learned), casefolded


def _has(term: str, text: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.casefold())}(?![a-z0-9])", text))


def blocked_by_title(title: str, channel: str, blocklist: list[str] | tuple[str, ...] | None = None) -> str | None:
    """The blocklisted term found in a source's title/channel (video games, gameplay...), if any."""

    text = f" {title} {channel} ".casefold()
    for term in [*(blocklist if blocklist is not None else DEFAULT_TITLE_BLOCKLIST), *ALWAYS_BLOCKED_TERMS]:
        if _has(term, text):
            return term
    name = f" {channel or ''} ".casefold()
    if name.strip() in LEARNED_BLOCKED_CHANNELS:
        return name.strip()
    return next((term for term in ALWAYS_BLOCKED_CHANNELS if _has(term, name)), None)
