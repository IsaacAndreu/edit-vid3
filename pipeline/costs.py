"""Append-only ledger of external API spend: work/<slug>/costs.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .context import RunContext


COSTS_FILE = "costs.json"


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


def total_cost(ctx: RunContext) -> float:
    return round(sum(float(entry.get("usd", 0)) for entry in _load(ctx)), 6)
