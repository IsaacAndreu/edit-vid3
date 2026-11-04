from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit


# Environment variables that make HTTP clients route traffic through a proxy
# implicitly. Local-only tools (ffmpeg/ffprobe reading files on disk) never need
# them, so they are stripped from the environment handed to those subprocesses.
PROXY_ENV_VARS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)

# Provider convention supplied by the operator: appending this suffix to the
# proxy username pins the same exit IP for up to 30 minutes.
DEFAULT_SESSION_SUFFIX = "-time-30-session-{session_id}"

ProxyRole = str  # "metadata" | "download"


class ProxyConfigError(ValueError):
    """Raised when a proxy URL cannot be used for sticky sessions."""


def new_session_id(length: int = 10) -> str:
    """Random alphanumeric session id; safe inside a proxy username."""

    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def with_sticky_session(
    proxy_url: str,
    session_id: str,
    *,
    suffix_template: str = DEFAULT_SESSION_SUFFIX,
) -> str:
    """Return ``proxy_url`` whose username carries the provider's session suffix.

    The URL is rebuilt with plain string handling so the password keeps its
    original percent-encoding untouched. A proxy without user info (e.g. an
    IP-whitelisted endpoint) is returned unchanged.
    """

    if not isinstance(proxy_url, str) or not proxy_url.strip():
        raise ProxyConfigError("proxy_url must be a non-empty string.")
    if not session_id or any(ch in session_id for ch in ":@/\\ "):
        raise ProxyConfigError("session_id must not be empty or contain ':', '@', '/', or spaces.")

    scheme, separator, rest = proxy_url.partition("://")
    if not separator:
        scheme, rest = "http", proxy_url
    netloc, slash, path = rest.partition("/")
    userinfo, at, hostport = netloc.rpartition("@")
    if not at or not userinfo:
        return proxy_url
    user, colon, password = userinfo.partition(":")
    suffix = suffix_template.format(session_id=session_id)
    if suffix in user:
        return proxy_url
    rebuilt_userinfo = f"{user}{suffix}{colon}{password}"
    return f"{scheme}://{rebuilt_userinfo}@{hostport}{slash}{path}"


def proxy_host_label(proxy_url: str | None) -> str:
    """Host:port only, safe for logs (never includes credentials)."""

    if not proxy_url:
        return "directo"
    try:
        parsed = urlsplit(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
    except ValueError:
        return "proxy"
    host = parsed.hostname or "proxy"
    return f"{host}:{parsed.port}" if parsed.port else host


def scrub_proxy_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy of the environment without implicit proxy variables.

    Used for ffmpeg/ffprobe invocations that only touch local files, so a
    globally exported ``HTTPS_PROXY`` can never route them (or bill them) through
    the residential proxy by accident.
    """

    source = os.environ if environ is None else environ
    return {key: value for key, value in source.items() if key not in PROXY_ENV_VARS}


@dataclass(frozen=True)
class ProxyConfig:
    """Which proxy, if any, each kind of YouTube traffic must use.

    ``metadata`` covers search, video page/player extraction and subtitles
    (www.youtube.com). ``download`` covers the media bytes (googlevideo.com),
    including the ffmpeg range download that yt-dlp drives. Either may be
    ``None`` to connect directly. When only ``download`` is set, metadata uses
    the same proxy so URLs stay bound to the IP that will fetch them.
    """

    metadata: str | None = None
    download: str | None = None
    session_suffix: str = DEFAULT_SESSION_SUFFIX

    @classmethod
    def from_values(
        cls,
        *,
        download: str | None,
        metadata: str | None,
        session_suffix: str | None = None,
    ) -> "ProxyConfig":
        download = (download or "").strip() or None
        metadata = (metadata or "").strip() or download
        return cls(
            metadata=metadata,
            download=download,
            session_suffix=session_suffix or DEFAULT_SESSION_SUFFIX,
        )

    @property
    def shares_exit_ip(self) -> bool:
        """True when metadata and download traffic use the same proxy (or both direct)."""

        return self.metadata == self.download

    def for_role(self, role: ProxyRole, session_id: str) -> str | None:
        """Proxy URL for ``role`` pinned to ``session_id``; ``None`` means direct."""

        if role == "metadata":
            base = self.metadata
        elif role == "download":
            base = self.download
        else:
            raise ValueError(f"Unknown proxy role: {role!r}")
        if base is None:
            return None
        return with_sticky_session(base, session_id, suffix_template=self.session_suffix)

    def describe(self) -> str:
        """Log-safe description (hosts only, never credentials)."""

        return (
            f"metadatos={proxy_host_label(self.metadata)}, "
            f"descargas={proxy_host_label(self.download)}"
        )
