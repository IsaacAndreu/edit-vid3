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
    from .fileio import file_lock

    path = ctx.work_dir / COSTS_FILE
    # between threads AND processes (27-11: entries lost with several videos and the studio writing at once)
    with _LOCK, file_lock(path.with_name(path.name + ".lock")):
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
    from .fileio import atomic_write_text

    payload = {"totalUsd": round(sum(float(e.get("usd", 0) or 0) for e in entries if isinstance(e, dict)), 6),
               "entries": entries}
    atomic_write_text(ctx.work_dir / COSTS_FILE, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


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
