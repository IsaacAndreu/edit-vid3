"""Each attempt of a video, on its card in the studio: when, how it ended, at which stage, the error, the seconds, the
dollars and the GB through the proxy. 27-11: there was no way to see how much money and time a video lost.

work/<vídeo>/intentos.json (the last KEEP attempts), written by main._run_one when an attempt ends (well or not).
The dollars are the costs ledger's entries since the attempt started; the GB, the «proxy_bytes» of the download log
(work/<vídeo>/youtube_downloads.jsonl) since then.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .aviso_fallo import spent_since
from .context import RunContext
from .fileio import read_json, update_json

FILE = "intentos.json"
KEEP = 50


def proxy_gb_since(work_dir: Path, started: float) -> float:
    total = 0
    try:
        lines = (work_dir / "youtube_downloads.jsonl").read_text("utf-8").splitlines()
    except OSError:
        return 0.0
    for line in lines:
        if '"proxy_bytes"' not in line:
            continue
        try:
            row = json.loads(line)
            if float(row.get("ts") or 0) >= started - 1:
                total += int(row.get("proxy_bytes") or 0)
        except (ValueError, TypeError, AttributeError):
            continue
    return round(total / 1e9, 3)


def _stage(ctx: RunContext) -> str:
    import os

    try:
        current = json.loads((ctx.work_dir / "current.json").read_text("utf-8"))
    except (OSError, ValueError):
        return ""
    return str(current.get("stage") or "") if isinstance(current, dict) and current.get("pid") == os.getpid() else ""


def record(ctx: RunContext, started: float, status: str, error: BaseException | None = None) -> None:
    """One attempt ended: written on the video's card. Never fails the video."""

    now = time.time()
    try:
        entry = {"start": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
                 "seconds": round(now - started), "status": status, "stage": _stage(ctx),
                 "error": f"{type(error).__name__}: {str(error).strip()[:300]}" if error is not None else "",
                 "usd": round(spent_since(ctx, started), 4), "proxyGb": proxy_gb_since(ctx.work_dir, started)}

        def add(old: Any) -> Any:
            attempts = old if isinstance(old, list) else []
            return [*[a for a in attempts if isinstance(a, dict)], entry][-KEEP:]

        ctx.work_dir.mkdir(parents=True, exist_ok=True)
        update_json(ctx.work_dir / FILE, add, [])
    except Exception as failure:
        print(f"   (ficha de intentos no guardada: {type(failure).__name__})")


def load(work_dir: Path) -> dict[str, Any]:
    """The card: every attempt, the total, and what the attempts that did not end well cost («lost»)."""

    raw = read_json(work_dir / FILE, [])
    attempts = [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []

    def add_up(rows: list[dict[str, Any]]) -> dict[str, Any]:
        number = lambda key: sum(float(r.get(key) or 0) for r in rows)   # noqa: E731
        return {"attempts": len(rows), "seconds": round(number("seconds")), "usd": round(number("usd"), 4),
                "proxyGb": round(number("proxyGb"), 3)}

    return {"attempts": attempts, "total": add_up(attempts),
            "lost": add_up([a for a in attempts if a.get("status") != "OK"])}
