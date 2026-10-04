"""Daily API spending limit, for a server that makes videos on its own.

`budget.daily_usd` (0 = no limit; the web studio's settings can change it): before each video the queue adds up what
every video spent today (work/*/costs.json, UTC day) and, at the limit, waits until tomorrow instead of starting.
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


def check(root: Path, config: dict) -> None:
    """Raises BudgetReached when today's spending is at the limit."""

    cap = limit(root, config)
    if cap > 0:
        spent = spent_today(root)
        if spent >= cap:
            raise BudgetReached(f"Límite diario de gasto alcanzado ({spent:.2f} $ de {cap:.2f} $): sigo mañana")
