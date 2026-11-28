"""When a failed video is tried again (the owner: «it should be retried at once, after a failure or after a restart»).

The first `watch.retry_now` (2) failures in a row of a video wait only `watch.retry_minutes` (1) — not hours: most
failures pass (the proxy, YouTube, a restart in the middle). Only a video that keeps failing the same way waits
`watch.retry_hours` (6), so one that can never work does not spend all night on itself. A video stopped by a restart
is no failure at all (main.WAITING: «interrumpido»): it goes on as soon as the queue starts again.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

DAY_CAP = 5                      # watch.max_failures_per_day: past this a video waits for tomorrow (or «Reintentar»)


def _today(now: float | None = None) -> str:
    return date.fromtimestamp(time.time() if now is None else now).isoformat()


def day_cap(watch: dict[str, Any]) -> int:
    return int(watch.get("max_failures_per_day", DAY_CAP))


def wait_seconds(watch: dict[str, Any], info: dict[str, Any]) -> float:
    tries = int(info.get("tries") or 1)
    if tries <= int(watch.get("retry_now", 2)):
        return float(watch.get("retry_minutes", 1)) * 60
    return float(watch.get("retry_hours", 6)) * 3600


def held(watch: dict[str, Any], info: dict[str, Any], signature: str, now: float | None = None) -> bool:
    """Still waiting: the same materials failed less than its wait ago, or already `max_failures_per_day` times today
    (new materials: tried at once)."""

    now = time.time() if now is None else now
    if info.get("sig") != signature:
        return False
    if info.get("day") == _today(now) and int(info.get("dayFails") or 0) >= day_cap(watch):
        return True
    return now - float(info.get("at", 0)) < wait_seconds(watch, info)


def record(old: dict[str, Any] | None, signature: str, status: str, code: str, now: float | None = None) -> dict[str, Any]:
    """The queue's entry for a video that just failed: the failures in a row with these materials (the wait) and
    today's failures whatever the materials (the daily cap). 27-11: the end of the round rewrote the entry without
    `tries` and a video that always failed was tried every round, 8 times in 77 minutes."""

    now = time.time() if now is None else now
    old = old or {}
    today = _today(now)
    return {"sig": signature, "at": now, "status": status, "code": code, "tries": failed_again(old, signature),
            "day": today, "dayFails": int(old.get("dayFails") or 0) + 1 if old.get("day") == today else 1}


def retry_at(watch: dict[str, Any], info: dict[str, Any]) -> float:
    return float(info.get("at", 0)) + wait_seconds(watch, info)


def failed_again(old: dict[str, Any] | None, signature: str) -> int:
    """How many times in a row these materials have failed, counting this one."""

    return int((old or {}).get("tries") or 0) + 1 if (old or {}).get("sig") == signature else 1
