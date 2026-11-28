"""Append-only ledger of external API spend: work/<slug>/costs.json."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from .context import RunContext


COSTS_FILE = "costs.json"
_LOCK = threading.Lock()


def _load(ctx: RunContext) -> list[dict[str, Any]]:
    path = ctx.work_dir / COSTS_FILE
    if not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    return entries if isinstance(entries, list) else []


def record_cost(
    ctx: RunContext,
    *,
    stage: str,
    provider: str,
    operation: str,
    usd: float,
    details: dict[str, Any] | None = None,
) -> None:
    with _LOCK:
        _append(ctx, stage=stage, provider=provider, operation=operation, usd=usd, details=details)


def _append(ctx: RunContext, *, stage: str, provider: str, operation: str, usd: float, details) -> None:
    entries = _load(ctx)
    entries.append(
        {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": stage,
            "provider": provider,
            "operation": operation,
            "usd": round(float(usd), 6),
            **({"details": details} if details else {}),
        }
    )
    ctx.write_json(COSTS_FILE, {"totalUsd": round(sum(float(e.get("usd", 0)) for e in entries), 6), "entries": entries})


def record_searches(ctx: RunContext, stage: str, provider: str, count: int) -> None:
    """Paid web searches (Serper) at `budget.<provider>_usd_per_search`; without a price, written down as «unpriced»
    with their number, so they are seen in the spend page instead of costing nothing."""

    if count <= 0:
        return
    try:
        price = float((ctx.config.get("budget") or {}).get(f"{provider}_usd_per_search") or 0)
    except (AttributeError, TypeError, ValueError):
        price = 0.0
    record_cost(ctx, stage=stage, provider=provider, operation=f"{count} búsquedas", usd=price * count,
                details={"searches": int(count), **({} if price else {"unpriced": True})})


def total_cost(ctx: RunContext) -> float:
    return round(sum(float(entry.get("usd", 0)) for entry in _load(ctx)), 6)
