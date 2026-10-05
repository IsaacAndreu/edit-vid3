"""Daily API spending limit, for a server that makes videos on its own.

`budget.daily_usd` (0 = no limit; the web studio's settings can change it): before each video the queue adds up what
every video spent today (work/*/costs.json, UTC day) and, at the limit, waits until tomorrow instead of starting.

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


def check(root: Path, config: dict) -> None:
    """Raises BudgetReached when today's spending is at the limit."""

    cap = limit(root, config)
    if cap > 0:
        spent = spent_today(root)
        if spent >= cap:
            raise BudgetReached(f"Límite diario de gasto alcanzado ({spent:.2f} $ de {cap:.2f} $): sigo mañana")
