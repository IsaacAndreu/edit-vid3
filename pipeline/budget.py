"""Daily API spending limit, for a server that makes videos on its own.

`budget.daily_usd` (0 = no limit; the web studio's settings can change it): before each video the queue adds up what
every video spent today (work/*/costs.json, UTC day) and, at the limit, waits until tomorrow instead of starting.

`budget.proxy_gb_per_day` (0 = no limit; also in the studio): GB through the paid residential proxy per UTC day,
summed from work/*/youtube_downloads.jsonl. At the cap a video that needs YouTube waits for tomorrow (the rest, dubs
and drawn videos, go on): a 250 GB block bought for 75 $ lasts the days you decide, not the days the retries leave.

`budget.per_video_usd` (1.5; also in the studio): what ONE attempt at a video may spend. Over it, before the next
stage, the video stops and leaves the queue (it is put on hold) with a message: a video that keeps costing is a video
that is going wrong (negocio2-4 on 05-10: 1.4-1.5 $ each for chalkboard videos).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class BudgetReached(RuntimeError):
    pass


class ApiSearchesShort(BudgetReached):
    """The YouTube API's searches left today do not cover this video's (api_overflow: esperar, the scene pilot):
    THIS video waits for the next quota reset (`until`, epoch seconds) instead of searching the rest through yt-dlp;
    the queue goes on with the others (main.QUOTA_WAIT)."""

    def __init__(self, message: str, until: float, why: str = "cuota de la API de YouTube") -> None:
        super().__init__(message)
        self.until = until
        self.why = why


class ProxyDown(ApiSearchesShort):
    """The way out to YouTube (the home proxy) does not answer: THIS video waits a few minutes and is tried again;
    the queue goes on. Not a YouTube block, nothing is quarantined."""

    def __init__(self, message: str, minutes: float = 15) -> None:
        import time

        super().__init__(message, time.time() + minutes * 60, why="el proxy no responde")


DEAD_KEY_MARKERS = ("token_invalidated", "invalid_api_key", "expired_secret", "Incorrect API key",
                    "Authentication Fails", "Error code: 401")


def dead_key(text: str) -> bool:
    """An API key revoked, expired or wrong (401): every call fails the same way until a new key is in .env."""

    return any(marker in text for marker in DEAD_KEY_MARKERS)


def spent_today(root: Path) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    total = 0.0
    for path in (root / "work").glob("*/costs.json"):
        try:
            entries = json.loads(path.read_text("utf-8")).get("entries", [])
        except (OSError, ValueError):
            continue
        total += sum(float(e.get("usd") or 0) for e in entries if str(e.get("at", "")).startswith(today))
    return round(total, 3)


def settings(root: Path) -> dict:
    path = root / "out" / "_ajustes.json"
    try:
        return json.loads(path.read_text("utf-8")) if path.is_file() else {}
    except ValueError:
        return {}


def limit(root: Path, config: dict) -> float:
    value = settings(root).get("daily_usd", (config.get("budget") or {}).get("daily_usd", 0))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class VideoOverBudget(RuntimeError):
    pass


PER_VIDEO_DEFAULT = 1.5


def per_video(root: Path, config: dict) -> float:
    value = settings(root).get("per_video_usd", (config.get("budget") or {}).get("per_video_usd", PER_VIDEO_DEFAULT))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return PER_VIDEO_DEFAULT


def video_spent(work_dir: Path) -> float:
    try:
        return float(json.loads((work_dir / "costs.json").read_text("utf-8")).get("totalUsd") or 0)
    except (OSError, ValueError):
        return 0.0


def check_video(root: Path, config: dict, work_dir: Path, folder: Path, started_at: float) -> None:
    """Between stages: this attempt (what was spent since it began) over budget.per_video_usd → out of the queue."""

    cap = per_video(root, config)
    spent = video_spent(work_dir) - started_at
    if cap > 0 and spent > cap:
        (folder / ".en-espera").write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        raise VideoOverBudget(
            f"Este intento ya ha gastado {spent:.2f} $ (límite por vídeo {cap:.2f} $): se para y sale de la cola para "
            "que lo mires. Si está bien, súbelo en Ajustes → «Límite por vídeo» y pulsa «Volver a la cola».")


class ProxyBudgetReached(ApiSearchesShort):
    """Today's GB through the paid proxy at budget.proxy_gb_per_day: THIS video (it needs YouTube) waits for the
    next UTC day; the queue goes on with the videos that need no proxy."""

    def __init__(self, gb: float, cap: float) -> None:
        from datetime import timedelta

        tomorrow = datetime.combine(datetime.now(timezone.utc).date() + timedelta(days=1), datetime.min.time(),
                                    tzinfo=timezone.utc)
        super().__init__(f"Tope diario del proxy alcanzado ({gb:.2f} GB de {cap:g} GB): este vídeo espera a mañana "
                         "para no gastar más proxy hoy", tomorrow.timestamp(), why="tope diario de GB del proxy")


def proxy_gb_today(root: Path) -> float:
    """GB the paid proxy carried today (UTC): proxy_bytes of every request row of every video."""

    start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc).timestamp()
    total = 0
    for path in (root / "work").glob("*/youtube_downloads.jsonl"):
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if '"proxy_bytes"' not in line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if float(row.get("ts") or 0) >= start:
                        total += int(row.get("proxy_bytes") or 0)
        except OSError:
            continue
    return round(total / 1e9, 3)


def proxy_limit(root: Path, config: dict) -> float:
    value = settings(root).get("proxy_gb_per_day", (config.get("budget") or {}).get("proxy_gb_per_day", 0))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def check_proxy(root: Path, config: dict) -> None:
    """Raises ProxyBudgetReached when today's GB through the proxy are at budget.proxy_gb_per_day."""

    cap = proxy_limit(root, config)
    if cap > 0:
        used = proxy_gb_today(root)
        if used >= cap:
            raise ProxyBudgetReached(used, cap)


def check(root: Path, config: dict) -> None:
    """Raises BudgetReached when today's spending is at the limit."""

    cap = limit(root, config)
    if cap > 0:
        spent = spent_today(root)
        if spent >= cap:
            raise BudgetReached(f"Límite diario de gasto alcanzado ({spent:.2f} $ de {cap:.2f} $): sigo mañana")
