from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def format_bytes(value: int | float) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


@dataclass
class RoleTraffic:
    requests: int = 0
    bytes: int = 0

    def add(self, amount: int) -> None:
        self.requests += 1
        self.bytes += max(0, int(amount))


@dataclass
class TrafficMeter:
    """Counts bytes moved per proxy role so a job can show what the proxy billed.

    Metadata bytes come from the HTTP responses yt-dlp opens (``Content-Length``
    when the server sends it, otherwise the decompressed body length, so the
    number is an upper bound of what crossed the wire). Media bytes come from
    the size of the file ffmpeg wrote for the requested range, which is a lower
    bound: ffmpeg also reads the index and the keyframe run-up before the cut.
    """

    roles: dict[str, RoleTraffic] = field(default_factory=dict)
    extractions: int = 0
    info_reuses: int = 0
    info_refreshes: int = 0
    clip_downloads: int = 0
    clip_library_hits: int = 0
    storyboard_previews: int = 0

    def record(self, role: str, amount: int) -> None:
        self.roles.setdefault(role, RoleTraffic()).add(amount)

    def bytes_for(self, role: str) -> int:
        return self.roles.get(role, RoleTraffic()).bytes

    def requests_for(self, role: str) -> int:
        return self.roles.get(role, RoleTraffic()).requests

    @property
    def total_bytes(self) -> int:
        return sum(item.bytes for item in self.roles.values())

    def wrap_ydl(self, ydl: Any, role: str) -> Any:
        """Count every HTTP response ``ydl`` opens under ``role``.

        yt-dlp routes extractor requests, subtitle downloads and the native
        downloader through ``YoutubeDL.urlopen``; wrapping that single method is
        enough. ffmpeg-driven range downloads bypass it and are counted by the
        caller from the resulting file size.
        """

        original = getattr(ydl, "urlopen", None)
        if original is None or getattr(ydl, "_traffic_meter_wrapped", False):
            return ydl
        meter = self

        def counting_urlopen(request: Any) -> Any:
            response = original(request)
            content_length = None
            headers = getattr(response, "headers", None)
            if headers is not None:
                try:
                    content_length = int(headers.get("Content-Length"))
                except (TypeError, ValueError, AttributeError):
                    content_length = None
            if content_length is not None:
                meter.record(role, content_length)
                return response
            read = getattr(response, "read", None)
            if read is None:
                meter.record(role, 0)
                return response
            counted = {"bytes": 0, "recorded": False}

            def counting_read(amt: int | None = None) -> bytes:
                data = read(amt)
                counted["bytes"] += len(data)
                if not counted["recorded"]:
                    counted["recorded"] = True
                    meter.record(role, 0)
                meter.roles[role].bytes += len(data)
                return data

            try:
                response.read = counting_read  # type: ignore[method-assign]
            except AttributeError:
                meter.record(role, 0)
            return response

        ydl.urlopen = counting_urlopen  # type: ignore[method-assign]
        ydl._traffic_meter_wrapped = True
        return ydl

    def summary_lines(self) -> list[str]:
        metadata = self.roles.get("metadata", RoleTraffic())
        download = self.roles.get("download", RoleTraffic())
        direct = self.roles.get("direct", RoleTraffic())
        lines = [
            "Tráfico YouTube: proxy metadatos "
            f"{format_bytes(metadata.bytes)} ({metadata.requests} peticiones) · "
            f"proxy descargas {format_bytes(download.bytes)} ({self.clip_downloads} clips) · "
            f"directo {format_bytes(direct.bytes)} ({direct.requests} peticiones) · "
            f"total vía proxy {format_bytes(metadata.bytes + download.bytes)}",
            f"yt-dlp: {self.extractions} extracciones de info, {self.info_reuses} reutilizaciones, "
            f"{self.info_refreshes} renovaciones por fallo · biblioteca de clips: "
            f"{self.clip_library_hits} reutilizados · previsualizaciones storyboard: "
            f"{self.storyboard_previews}",
        ]
        return lines

    def as_dict(self) -> dict[str, Any]:
        return {
            "bytes": {role: item.bytes for role, item in self.roles.items()},
            "requests": {role: item.requests for role, item in self.roles.items()},
            "proxy_bytes": self.bytes_for("metadata") + self.bytes_for("download"),
            "extractions": self.extractions,
            "info_reuses": self.info_reuses,
            "info_refreshes": self.info_refreshes,
            "clip_downloads": self.clip_downloads,
            "clip_library_hits": self.clip_library_hits,
            "storyboard_previews": self.storyboard_previews,
        }
