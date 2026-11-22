"""Recommendations that learn (prompt «qué canales empezar, cuáles doblar», part 5).

Every recommendation the «Qué hacer ahora» page shows is kept once, with its date and its numbers
(out/_radar/recomendaciones.json). When the channel it led to — a channel started from it (`link`), or the channel a
dub goes to (`dubbing.channels`) — has 30 days and ten long videos, its real median views are put next to what was
predicted (the median views of the niche in that language when it was recommended). Without this nobody will ever
know whether the score is any good.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

FILE = "out/_radar/recomendaciones.json"
MIN_DAYS = 30
MIN_VIDEOS = 10


def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text("utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("items"), dict) else {"items": {}}
    except (OSError, ValueError):
        return {"items": {}}


def _write(root: Path, data: dict[str, Any]) -> None:
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def rec_id(rec: dict[str, Any]) -> str:
    if rec.get("kind") == "doblar":
        return f"doblar:{rec['channel']}:{rec['lang']}"
    return f"empezar:{str(rec.get('topic') or '').casefold()}:{rec.get('lang')}"


def record(root: Path, recs: list[dict[str, Any]], today: str | None = None) -> int:
    """Keep the recommendations not seen before (the first date and score stay). Returns how many are new."""

    today = today or date.today().isoformat()
    data = _read(root)
    new = 0
    for rec in recs:
        rid = rec_id(rec)
        if rid in data["items"]:
            continue
        data["items"][rid] = {"id": rid, "date": today, "kind": rec.get("kind"), "channel": rec.get("channel"),
                              "topic": rec.get("topic"), "lang": rec.get("lang"), "score": rec.get("score"),
                              "predicted": rec.get("demand"), "made": None}
        new += 1
    if new:
        _write(root, data)
    return new


def link(root: Path, rid: str, channel: str) -> None:
    """A channel started (or dubbed) because of this recommendation."""

    data = _read(root)
    if rid in data["items"]:
        data["items"][rid]["made"] = channel
        data["items"][rid]["madeOn"] = date.today().isoformat()
        _write(root, data)


def _target(root: Path, item: dict[str, Any]) -> str | None:
    if item.get("made"):
        return item["made"]
    if item.get("kind") == "doblar" and item.get("channel"):
        from .context import RunContext

        try:
            config = RunContext.create("_radar", root=root, channel=item["channel"]).config
        except Exception:
            return None
        return ((config.get("dubbing") or {}).get("channels") or {}).get(item.get("lang"))
    return None


def outcome(report: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any] | None:
    """The real numbers of a channel once it has MIN_DAYS and MIN_VIDEOS long videos, else None."""

    if not report:
        return None
    now = now or datetime.now(timezone.utc)
    long = [v for v in report.get("videos") or [] if not v.get("short") and v.get("published")]
    if len(long) < MIN_VIDEOS:
        return None
    first = min(datetime.fromisoformat(str(v["published"]).replace("Z", "+00:00")) for v in long)
    if (now - first).days < MIN_DAYS:
        return None
    return {"videos": len(long), "days": (now - first).days, "median": (report.get("numbers") or {}).get("medianLong")}


def report(root: Path, now: datetime | None = None) -> list[dict[str, Any]]:
    """Each recommendation acted on, with what was predicted and, when it can be told, what happened."""

    from .mychannel import saved

    out = []
    for item in _read(root)["items"].values():
        target = _target(root, item)
        if not target:
            continue
        real = outcome(saved(root, target), now)
        row = {**item, "target": target, "real": real}
        if real and real.get("median") and item.get("predicted"):
            ratio = real["median"] / item["predicted"]
            row["ratio"] = round(ratio, 2)
            row["verdict"] = "mejor de lo previsto" if ratio >= 2 else "peor de lo previsto" if ratio < 0.5 else "como se previó"
        else:
            row["verdict"] = "aún sin datos (30 días y 10 vídeos)"
        out.append(row)
    return sorted(out, key=lambda r: r.get("date", ""), reverse=True)
