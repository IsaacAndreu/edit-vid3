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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


_OWNERS: dict[tuple, tuple[float, dict[str, str]]] = {}
_OWNERS_LOCK = threading.Lock()
OWNERS_SECONDS = 30


def _owners_by_slug(root: Path) -> dict[str, str]:
    """{video slug: owner} for every video folder, from one walk of materiales/ (30 s in memory). Asking video by
    video walked the whole of materiales/ each time: 389 walks, 6 of the 14 s the studio's overview took."""

    from .context import video_folders
    from .usuarios import owners
    from .web import _channel_of

    mapping = owners(root)                      # a channel given to someone else counts for them at once
    key = (str(root), tuple(sorted(mapping.items())))
    with _OWNERS_LOCK:
        hit = _OWNERS.get(key)
        if hit and time.monotonic() - hit[0] < OWNERS_SECONDS:
            return hit[1]
    found: dict[str, str] = {}
    if mapping:
        base = root / "materiales"
        # the same folder find_video picks: a copy put away (materiales/_hechos/…) only when there is no other
        put_away = lambda f: any(p.startswith(("_", ".")) for p in f.relative_to(base).parts[:-1])   # noqa: E731
        for folder in sorted(video_folders(root), key=put_away):
            if folder.name not in found:
                found[folder.name] = mapping.get(_channel_of(root, folder), "")
    with _OWNERS_LOCK:
        _OWNERS.clear()                         # one root, one list of owners at a time: nothing piles up
        _OWNERS[key] = (time.monotonic(), found)
    return found


def owner_of_work(root: Path, slug: str) -> str:
    """Whose spending a work folder is: a partner's name (their channel, usuarios.py) or "" (yours: your videos and
    every «_» folder, the radar, the ideas…)."""

    if slug.startswith("_"):
        return ""
    try:
        known = _owners_by_slug(root)
        if slug in known:
            return known[slug]
        from .context import find_video
        from .usuarios import owners
        from .web import _channel_of

        mapping = owners(root)
        if not mapping:
            return ""
        return mapping.get(_channel_of(root, find_video(root, slug)), "")
    except Exception:
        return ""


def _mine(root: Path, folder: Path, owner: str | None) -> bool:
    return owner is None or owner_of_work(root, folder.name) == owner


def _today_start() -> float:
    return datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc).timestamp()


def _untouched_since(path: Path, start: float) -> bool:
    """A log not written since `start` has nothing from after it (its rows are appended as they happen)."""

    try:
        return path.stat().st_mtime < start
    except OSError:
        return True


def spent_today(root: Path, owner: str | None = None) -> float:
    """Today's API spending (UTC); `owner` ("" you, a partner's name): only that person's videos."""

    today = datetime.now(timezone.utc).date().isoformat()
    start = _today_start()
    total = 0.0
    for path in (root / "work").glob("*/costs.json"):
        if _untouched_since(path, start) or not _mine(root, path.parent, owner):
            continue
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


def video_spent_today(work_dir: Path) -> float:
    """What this video spent today (UTC), whatever the attempts: 27-11, five attempts of 1.40 $ added up to 7 $ with
    the cap at 1.50 $, because the cap was per attempt."""

    today = datetime.now(timezone.utc).date().isoformat()
    try:
        entries = json.loads((work_dir / "costs.json").read_text("utf-8")).get("entries") or []
    except (OSError, ValueError):
        return 0.0
    return sum(float(e.get("usd") or 0) for e in entries if str(e.get("at") or "").startswith(today))


def check_video(root: Path, config: dict, work_dir: Path, folder: Path, started_at: float) -> None:
    """Between stages and before each paid call: what this video spent today (all its attempts) — or this attempt,
    if more — over budget.per_video_usd → out of the queue."""

    cap = per_video(root, config)
    spent = max(video_spent_today(work_dir), video_spent(work_dir) - started_at)
    if cap > 0 and spent > cap:
        (folder / ".en-espera").write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        raise VideoOverBudget(
            f"Este vídeo ya ha gastado hoy {spent:.2f} $ (límite por vídeo {cap:.2f} $): se para y sale de la cola "
            "para que lo mires. Si está bien, súbelo en Ajustes → «Límite por vídeo» y pulsa «Volver a la cola».")


ATTEMPT_START: dict[str, float] = {}      # work dir → what the video had spent when this attempt began (run_stages)


def before_paid_call(ctx: Any) -> None:
    """Before ANY paid call (model, voice, images) of a video: the same caps as `guard`. Not for the studio's or the
    watcher's own work (slugs starting with «_»: radar, ideas, drafts), which has no video to put on hold."""

    slug = str(getattr(ctx, "slug", "") or "")
    if not slug or slug.startswith("_") or not hasattr(ctx, "work_dir"):
        return
    guard(ctx)


def guard(ctx: Any) -> None:
    """Inside the stages that spend by the call (judge, fallback): the daily cap of whoever owns the video and this
    attempt's per-video cap, checked before each paid call — not only between stages, when a long stage could already
    have gone far past them."""

    check(ctx.root, ctx.config, ctx.slug)
    check_video(ctx.root, ctx.config, ctx.work_dir, ctx.materials_dir, ATTEMPT_START.get(str(ctx.work_dir), 0.0))


class ProxyBudgetReached(ApiSearchesShort):
    """Today's GB through the paid proxy at budget.proxy_gb_per_day: THIS video (it needs YouTube) waits for the
    next UTC day; the queue goes on with the videos that need no proxy."""

    def __init__(self, gb: float, cap: float) -> None:
        from datetime import timedelta

        tomorrow = datetime.combine(datetime.now(timezone.utc).date() + timedelta(days=1), datetime.min.time(),
                                    tzinfo=timezone.utc)
        super().__init__(f"Tope diario del proxy alcanzado ({gb:.2f} GB de {cap:g} GB): este vídeo espera a mañana "
                         "para no gastar más proxy hoy", tomorrow.timestamp(), why="tope diario de GB del proxy")


def proxy_gb_today(root: Path, owner: str | None = None) -> float:
    """GB the paid proxy carried today (UTC): proxy_bytes of every request row of every video (of `owner`'s only)."""

    start = _today_start()
    total = 0
    for path in (root / "work").glob("*/youtube_downloads.jsonl"):
        if _untouched_since(path, start) or not _mine(root, path.parent, owner):
            continue
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


def partner_limits(root: Path, owner: str) -> dict:
    """A partner's own daily caps (Ajustes → Personas): {daily_usd, proxy_gb_per_day}, 0 = none."""

    from .usuarios import limits_of

    return limits_of(root, owner)


def check_proxy(root: Path, config: dict, slug: str = "") -> None:
    """Raises ProxyBudgetReached when today's GB through the proxy are at the cap of whoever owns this video: yours
    (budget.proxy_gb_per_day) for your videos, a partner's own for theirs. Each one counts only their own GB."""

    owner = owner_of_work(root, slug) if slug else ""
    cap = float(partner_limits(root, owner).get("proxy_gb_per_day") or 0) if owner else proxy_limit(root, config)
    if cap > 0:
        used = proxy_gb_today(root, owner)
        if used >= cap:
            raise ProxyBudgetReached(used, cap)


def check(root: Path, config: dict, slug: str = "") -> None:
    """Raises BudgetReached when today's spending of whoever owns this video is at their limit."""

    owner = owner_of_work(root, slug) if slug else ""
    cap = float(partner_limits(root, owner).get("daily_usd") or 0) if owner else limit(root, config)
    if cap > 0:
        spent = spent_today(root, owner)
        if spent >= cap:
            raise BudgetReached(f"Límite diario de gasto alcanzado ({spent:.2f} $ de {cap:.2f} $): sigo mañana")
