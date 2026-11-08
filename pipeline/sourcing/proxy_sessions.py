"""Sticky sessions for a paid residential proxy (Rainproxy and the like).

A home proxy (Tailscale, no user in its URL) is one fixed IP: nothing to do. A residential proxy hands out a new exit
IP per connection unless the username carries the provider's session suffix (Rainproxy: `-time-30-session-<id>`;
other providers have their own, sourcing.youtube.proxy_session_suffix): every connection with the same id leaves
from the same IP for up to 30 minutes. YouTube binds stream URLs to the IP that
asked for them, so one video's metadata, storyboard and ranges must share one id — or every segment is a 403.

Sessions live per video id in cache/videos/<id>/.sesion.json (every process and stage of that video sees the same
one) and are rotated, at most a few times per video, when YouTube answers «are you a bot» or 429 to that IP.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

SESSION_SUFFIX = "-time-30-session-{session_id}"
SESSION_FILE = ".sesion.json"
_SESSION_RE = re.compile(r"-time-\d+-session-[A-Za-z0-9]+")


def is_residential(proxy: str | None) -> bool:
    """A paid proxy with a user in its URL (a home/Tailscale proxy has none)."""

    if not proxy:
        return False
    netloc = proxy.partition("://")[2].partition("/")[0] if "://" in proxy else proxy.partition("/")[0]
    return "@" in netloc and bool(netloc.rpartition("@")[0])


def mask_proxy(proxy: str | None) -> str:
    """The proxy for logs and screens: credentials always hidden (//****@host:port)."""

    if not proxy:
        return "directo"
    return re.sub(r"//[^/@\s]+@", "//****@", proxy)


def proxy_host(proxy: str | None) -> str:
    if not proxy:
        return "directo"
    try:
        parts = urlsplit(proxy if "://" in proxy else f"http://{proxy}")
    except ValueError:
        return "proxy"
    return f"{parts.hostname}:{parts.port}" if parts.port else str(parts.hostname or "proxy")


def new_session_id(length: int = 10) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def with_sticky_session(proxy: str, session_id: str, *, suffix: str = SESSION_SUFFIX) -> str:
    """`proxy` whose username carries the session suffix. Plain string handling: the password keeps whatever
    percent-encoding it has (never decoded or re-encoded). Without a user the URL comes back unchanged."""

    if not proxy or not proxy.strip():
        raise ValueError("proxy must be a non-empty string.")
    if not session_id or not re.fullmatch(r"[A-Za-z0-9]+", session_id):
        raise ValueError("session_id must be alphanumeric.")
    scheme, separator, rest = proxy.partition("://")
    if not separator:
        scheme, rest = "http", proxy
    netloc, slash, path = rest.partition("/")
    userinfo, at, hostport = netloc.rpartition("@")
    if not at or not userinfo:
        return proxy
    if "{session_id}" not in suffix:
        raise ValueError("the session suffix must contain {session_id}.")
    user, colon, password = userinfo.partition(":")
    before, _, after = suffix.partition("{session_id}")
    previous = re.compile(re.escape(before) + r"[A-Za-z0-9]+" + re.escape(after))
    user = previous.sub("", _SESSION_RE.sub("", user))   # replace a previous session instead of stacking suffixes
    return f"{scheme}://{user}{suffix.format(session_id=session_id)}{colon}{password}@{hostport}{slash}{path}"


@dataclass(frozen=True)
class Session:
    id: str
    started: float
    rotations: int


class ProxySessions:
    """One sticky session per video (and one for requests without a video, like searches)."""

    def __init__(self, videos_dir: Path, *, minutes: float = 30.0, max_rotations: int = 2,
                 margin_minutes: float = 2.0) -> None:
        self.videos_dir = Path(videos_dir)
        self.lifetime = max(60.0, float(minutes) * 60 - float(margin_minutes) * 60)
        self.max_rotations = int(max_rotations)
        self._lock = threading.RLock()
        self._memory: dict[str, Session] = {}
        self.rotated = 0                      # for the run's summary

    # --- storage -------------------------------------------------------------------

    def _path(self, video_id: str) -> Path | None:
        if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return None                       # searches and other keys live in memory only
        return self.videos_dir / video_id / SESSION_FILE

    def _load(self, key: str) -> Session | None:
        path = self._path(key)
        if path is None:
            return self._memory.get(key)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Session(str(data["id"]), float(data["started"]), int(data.get("rotations", 0)))
        except (OSError, ValueError, KeyError, TypeError):
            return self._memory.get(key)

    def _store(self, key: str, session: Session) -> None:
        self._memory[key] = session
        path = self._path(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps({"id": session.id, "started": session.started, "rotations": session.rotations}),
                           encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    # --- use -----------------------------------------------------------------------

    def alive(self, session: Session | None, now: float | None = None) -> bool:
        if session is None:
            return False
        return (time.time() if now is None else now) - session.started < self.lifetime

    def current(self, key: str) -> Session:
        """The live session of `key` (a video id, or e.g. "search"), or a new one when it ran out."""

        with self._lock:
            session = self._load(key)
            if not self.alive(session):
                session = Session(new_session_id(), time.time(), 0)
                self._store(key, session)
            return session

    def session_id(self, key: str) -> str:
        return self.current(key).id

    def rotate(self, key: str) -> str | None:
        """A new IP for `key` after «are you a bot» or 429: the new session id, or None when the video already
        rotated `max_rotations` times within this session window (then it is the video, not the IP)."""

        with self._lock:
            session = self._load(key)
            rotations = session.rotations if self.alive(session) else 0
            if rotations >= self.max_rotations:
                return None
            fresh = Session(new_session_id(), time.time(), rotations + 1)
            self._store(key, fresh)
            self.rotated += 1
            return fresh.id

    def matches(self, key: str, session_id: str | None) -> bool:
        """Is `session_id` the live session of `key` (same exit IP, so its stream URLs still belong to us)?"""

        if not session_id:
            return False
        with self._lock:
            session = self._load(key)
            return self.alive(session) and session.id == session_id
