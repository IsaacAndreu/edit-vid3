"""When a failed video is tried again (the owner: «it should be retried at once, after a failure or after a restart»).

The first `watch.retry_now` (2) failures in a row of a video wait only `watch.retry_minutes` (1) — not hours: most
failures pass (the proxy, YouTube, a restart in the middle). Only a video that keeps failing the same way waits
`watch.retry_hours` (6), so one that can never work does not spend all night on itself. A video stopped by a restart
is no failure at all (main.WAITING: «interrumpido»): it goes on as soon as the queue starts again.
"""

from __future__ import annotations

import time
from typing import Any


def wait_seconds(watch: dict[str, Any], info: dict[str, Any]) -> float:
    tries = int(info.get("tries") or 1)
    if tries <= int(watch.get("retry_now", 2)):
        return float(watch.get("retry_minutes", 1)) * 60
    return float(watch.get("retry_hours", 6)) * 3600


def held(watch: dict[str, Any], info: dict[str, Any], signature: str, now: float | None = None) -> bool:
    """Still waiting: the same materials failed less than its wait ago (new materials: tried at once)."""

    now = time.time() if now is None else now
    return info.get("sig") == signature and now - float(info.get("at", 0)) < wait_seconds(watch, info)


def retry_at(watch: dict[str, Any], info: dict[str, Any]) -> float:
    return float(info.get("at", 0)) + wait_seconds(watch, info)


def failed_again(old: dict[str, Any] | None, signature: str) -> int:
    """How many times in a row these materials have failed, counting this one."""

    return int((old or {}).get("tries") or 0) + 1 if (old or {}).get("sig") == signature else 1
