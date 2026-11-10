"""Does the adaptive analysis (analysis.adaptive) save YouTube work without costing shots? Video by video, and the
median of each channel with and without it: `python main.py --informe-analisis [CANAL]` → out/_informe_analisis.md.

Per video, from what the run left in work/<slug>/:
- distinct YouTube videos looked at in the fine pass, and 360p windows (scores/_rondas.json, or the request log);
- the units the analysis took from the home connection's hourly budget (youtube_downloads.jsonl, stage analysis:
  details 4, piece 3, whole 8 — what goes through the metadata proxy does not count, as in the queue);
- minutes of the stage (.stages/analysis.json);
- shots the judge accepted, shots sent to the fallback, and shots nothing could fill in the end (fallback.json):
  the quality side — fewer videos looked at is only a gain if these do not get worse;
- overlapping clip downloads: the same video and kind downloaded again over seconds an earlier file already had
  (logged since the start/end of each clip is written).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from .sourcing.youtube import REQUEST_UNITS


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _rows(work: Path) -> list[dict[str, Any]]:
    path = work / "youtube_downloads.jsonl"
    out = []
    if path.is_file():
        for line in path.read_text("utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def overlaps(rows: list[dict[str, Any]]) -> int:
    """Clip files downloaded over seconds an earlier file of the same video and kind already covered."""

    seen: dict[tuple[str, str], list[tuple[float, float]]] = {}
    count = 0
    for r in sorted(rows, key=lambda r: r.get("ts") or 0):
        if not str(r.get("action", "")).startswith("archivo") or not r.get("ok") or r.get("start") is None:
            continue
        key = (str(r.get("video")), str(r["action"]))
        a, b = float(r["start"]), float(r["end"])
        if any(x < b and a < y for x, y in seen.get(key, [])):
            count += 1
        seen.setdefault(key, []).append((a, b))
    return count


def video(work: Path) -> dict[str, Any] | None:
    stage = _read(work / ".stages" / "analysis.json")
    if not stage:
        return None
    rows = _rows(work)
    analysis = [r for r in rows if r.get("stage") == "analysis"]
    units = sum(REQUEST_UNITS.get(str(r.get("action")), 0) for r in analysis
                if r.get("proxy") != "metadatos" and not str(r.get("action", "")).startswith("archivo"))
    rounds = _read(work / "scores" / "_rondas.json") or {}
    looked = rounds.get("videos") or len({r.get("video") for r in analysis if str(r.get("action", "")).startswith("archivo")})
    stats = (_read(work / "selection.json") or {}).get("stats") or {}
    accepted = int(stats.get("byScore", 0)) + int(stats.get("byJudge", 0))
    sent = int(stats.get("fallback", 0))
    unresolved = len((_read(work / "fallback.json") or {}).get("unresolved") or {})
    shots = accepted + sent
    return {"slug": work.name, "adaptive": bool(rounds.get("adaptive")), "videos": looked, "units": units,
            "minutes": round(float(stage.get("seconds") or 0) / 60, 1), "shots": shots,
            "accepted": round(accepted / shots, 3) if shots else None, "toFallback": round(sent / shots, 3) if shots else None,
            "unfilled": unresolved, "overlaps": overlaps(rows), "secondRound": rounds.get("shotsSecondRound")}


def report(root: Path, channel: str | None = None) -> dict[str, Any]:
    from . import agenda

    channel_of = {v["slug"]: v["channel"] for v in agenda.videos(root)}
    rows = []
    for work in sorted((root / "work").glob("*/")):
        found = video(work)
        if found and (channel is None or channel_of.get(work.name) == channel):
            rows.append({**found, "channel": channel_of.get(work.name, "?")})
    groups: dict[tuple[str, bool], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["channel"], row["adaptive"]), []).append(row)

    def median(items: list[dict[str, Any]], field: str) -> float | None:
        values = [i[field] for i in items if i.get(field) is not None]
        return round(statistics.median(values), 3) if values else None

    summary = [{"channel": c, "adaptive": a, "count": len(items),
                **{f: median(items, f) for f in ("videos", "units", "minutes", "accepted", "toFallback", "unfilled", "overlaps")}}
               for (c, a), items in sorted(groups.items())]
    return {"videos": rows, "summary": summary}


def markdown(data: dict[str, Any]) -> str:
    pct = lambda x: "—" if x is None else f"{100 * x:.0f} %"          # noqa: E731
    lines = ["# Análisis adaptativo: antes y después", "",
             "Mediana por canal. Menos vídeos y unidades con el mismo % aceptado (y no más planos sin cubrir) = ahorro real.", "",
             "| Canal | Análisis | Vídeos | Vídeos mirados | Unidades | Minutos | Aceptados por el juez | A relleno | Sin cubrir | Descargas solapadas |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in data["summary"]:
        lines.append(f"| {s['channel']} | {'adaptativo' if s['adaptive'] else 'antes'} | {s['count']} | {s['videos']} | {s['units']} | "
                     f"{s['minutes']} | {pct(s['accepted'])} | {pct(s['toFallback'])} | {s['unfilled']} | {s['overlaps']} |")
    lines += ["", "## Vídeo a vídeo", "",
              "| Vídeo | Canal | Análisis | Vídeos mirados | Unidades | Minutos | Aceptados | A relleno | Sin cubrir | 2.ª ronda | Solapadas |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for v in data["videos"]:
        lines.append(f"| {v['slug']} | {v['channel']} | {'adaptativo' if v['adaptive'] else 'antes'} | {v['videos']} | {v['units']} | "
                     f"{v['minutes']} | {pct(v['accepted'])} | {pct(v['toFallback'])} | {v['unfilled']} | {v['secondRound'] or '—'} | {v['overlaps']} |")
    return "\n".join(lines) + "\n"
