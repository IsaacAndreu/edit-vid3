"""What reusing saved: work/<slug>/savings.jsonl, one line per thing not paid again — a judge verdict read from
cache/judge/ instead of asking the model, a piece of narration already made. Only counts are kept here; «Gasto de
API» (pipeline/gasto.py) prices them with what the same thing really cost in the other videos.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

FILE = "savings.jsonl"
_LOCK = threading.Lock()


def record(work_dir: Path, kind: str, amount: float = 1, **details: Any) -> None:
    """Never raises: a saving not written is only a number missing in a report."""

    try:
        with _LOCK:
            work_dir.mkdir(parents=True, exist_ok=True)
            with (work_dir / FILE).open("a", encoding="utf-8") as out:
                out.write(json.dumps({"kind": kind, "amount": amount, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                      **details}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def totals(work_dir: Path) -> dict[str, float]:
    """{"judge": verdicts reused, "voice": characters reused} of one video."""

    out: dict[str, float] = {}
    path = work_dir / FILE
    if not path.is_file():
        return out
    for line in path.read_text("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        out[str(row.get("kind"))] = out.get(str(row.get("kind")), 0.0) + float(row.get("amount") or 0)
    return out
