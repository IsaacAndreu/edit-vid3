"""Where the hours go: the time of every stage of the finished videos, so we speed up what really weighs.

    python main.py --tiempos [días]     (30 by default) → prints it and writes out/_tiempos.md

Read from the stage markers (work/<vídeo>/.stages/<etapa>.json, `seconds`: the work of the stage, the wait for its
turn in the queue not counted; `waitSeconds`: that wait; `failedSeconds`: attempts that died before succeeding,
also in .stages/<etapa>.fallos.jsonl while the stage has not succeeded yet) of the videos with a render. Per kind of video (third-party footage, the rest:
simulations, drawn, dubs): the median minutes of each stage, its share of the total, and for the footage ones the
search per shot (sourcing minutes / shots with footage) and what YouTube's requests cost (youtube_downloads.jsonl).
The queue's report (out/_cola.md) also names the slowest stage of each video.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

REPORT = "out/_tiempos.md"
NAMES = {"factcheck": "verificar datos", "align": "sincronizar voz", "planner": "planificar planos",
         "sourcing": "buscar material", "analysis": "analizar clips", "judge": "juez", "ingest": "descargar clips",
         "people": "personas", "fallback": "planos alternativos", "coldopen": "apertura", "timeline": "montaje",
         "qa": "revisión", "render": "render", "shorts": "Shorts", "package": "paquete"}


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def stage_seconds(work: Path) -> dict[str, float]:
    folder = work / ".stages"
    if not folder.is_dir():
        return {}
    return {p.stem: float((_read(p) or {}).get("seconds") or 0) for p in folder.glob("*.json")}


def stage_waits(work: Path) -> dict[str, dict[str, float]]:
    """Per stage: {"wait": turn's wait, "failed": seconds of attempts that died, "failedWait": their waits}.
    Markers written before 11-2026 have none of these: 0."""

    folder = work / ".stages"
    if not folder.is_dir():
        return {}
    out = {}
    for p in folder.glob("*.json"):
        data = _read(p) or {}
        out[p.stem] = {"wait": float(data.get("waitSeconds") or 0), "failed": float(data.get("failedSeconds") or 0),
                       "failedWait": float(data.get("failedWaitSeconds") or 0)}
    for p in folder.glob("*.fallos.jsonl"):          # a stage still failing: no marker yet
        stage = p.name[: -len(".fallos.jsonl")]
        try:
            rows = [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]
        except (OSError, ValueError):
            continue
        entry = out.setdefault(stage, {"wait": 0.0, "failed": 0.0, "failedWait": 0.0})
        entry["failed"] += sum(float(r.get("seconds") or 0) for r in rows)
        entry["failedWait"] += sum(float(r.get("waitSeconds") or 0) for r in rows)
    return out


def footage_shots(work: Path) -> int:
    return int((_read(work / "candidates" / "_summary.json") or {}).get("shots") or 0)


def slowest(work: Path) -> str:
    """«buscar material 2 h 10 min (64 %)»: the stage that took the most of this video, for the queue's report."""

    seconds = stage_seconds(work)
    total = sum(seconds.values())
    if not total:
        return "—"
    name, worst = max(seconds.items(), key=lambda kv: kv[1])
    return f"{NAMES.get(name, name)} {duration(worst)} ({worst / total:.0%})"


def duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{max(minutes, 0)} min" if seconds >= 60 \
        else f"{seconds:.0f} s"


def _youtube_seconds(work: Path) -> dict[str, float]:
    """Seconds of YouTube's requests by kind (search, info, download…), from the sourcing's metrics."""

    out: dict[str, float] = {}
    path = work / "youtube_downloads.jsonl"
    if not path.is_file():
        return out
    for line in path.read_text("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        action = str(row.get("action") or "?")
        out[action] = out.get(action, 0.0) + float(row.get("seconds") or 0)
        if row.get("wait"):              # waiting for the pace / a 429's pause before asking
            out["esperas"] = out.get("esperas", 0.0) + float(row["wait"])
    return out


def report(root: Path, days: float = 30) -> dict[str, Any]:
    since = time.time() - days * 86400
    kinds: dict[str, list[dict[str, Any]]] = {}
    lost: list[dict[str, Any]] = []
    for work in sorted((root / "work").glob("*")) if (root / "work").is_dir() else []:
        render = work / ".stages" / "render.json"
        if not render.is_file() or render.stat().st_mtime < since:
            failures = [p for p in (work / ".stages").glob("*.fallos.jsonl") if p.stat().st_mtime >= since] \
                if (work / ".stages").is_dir() else []
            if failures:                 # not finished: what its attempts that died cost
                waits = stage_waits(work)
                cost = sum(w["failed"] for w in waits.values())
                lost.append({"slug": work.name, "seconds": cost,
                             "stage": max(waits, key=lambda k: waits[k]["failed"]) if waits else "?"})
            continue
        seconds = stage_seconds(work)
        shots = footage_shots(work)
        kind = "terceros" if shots else "sin metraje"
        kinds.setdefault(kind, []).append({"slug": work.name, "seconds": seconds, "total": sum(seconds.values()),
                                           "waits": stage_waits(work),
                                           "shots": shots, "youtube": _youtube_seconds(work) if shots else {}})
    out: dict[str, Any] = {"days": days, "kinds": {}, "lost": sorted(lost, key=lambda r: -r["seconds"])}
    for kind, videos in kinds.items():
        stages = sorted({s for v in videos for s in v["seconds"]}, key=lambda s: list(NAMES).index(s) if s in NAMES else 99)
        median_total = statistics.median(v["total"] for v in videos)
        rows = []
        for stage in stages:
            values = [v["seconds"].get(stage, 0.0) for v in videos]
            share = sum(values) / max(1.0, sum(v["total"] for v in videos))
            waits = [v["waits"].get(stage, {}) for v in videos]
            rows.append({"stage": stage, "name": NAMES.get(stage, stage), "median": statistics.median(values),
                         "max": max(values), "share": share,
                         "medianWait": statistics.median(w.get("wait", 0.0) for w in waits),
                         "failed": sum(w.get("failed", 0.0) for w in waits),
                         "failedWait": sum(w.get("failedWait", 0.0) for w in waits)})
        entry: dict[str, Any] = {"videos": len(videos), "medianTotal": median_total,
                                 "stages": sorted(rows, key=lambda r: -r["share"]),
                                 "slowest": sorted(({"slug": v["slug"], "total": v["total"]} for v in videos),
                                                   key=lambda r: -r["total"])[:5]}
        with_shots = [v for v in videos if v["shots"]]
        if with_shots:
            entry["sourcingPerShot"] = statistics.median(v["seconds"].get("sourcing", 0.0) / v["shots"] for v in with_shots)
            youtube: dict[str, float] = {}
            for v in with_shots:
                for action, s in v["youtube"].items():
                    youtube[action] = youtube.get(action, 0.0) + s
            entry["youtubeHours"] = {a: s / 3600 for a, s in sorted(youtube.items(), key=lambda kv: -kv[1])}
        out["kinds"][kind] = entry
    return out


def markdown(data: dict[str, Any]) -> str:
    lines = [f"# Dónde se va el tiempo · últimos {data['days']:g} días", ""]
    lost = [r for r in data.get("lost", []) if r["seconds"] >= 60]
    tail = []
    if lost:
        tail = ["## Trabajo perdido en vídeos sin terminar", "",
                f"{len(lost)} vídeos, {duration(sum(r['seconds'] for r in lost))} de trabajo en intentos que fallaron: "
                + ", ".join(f"{r['slug']} ({duration(r['seconds'])}, sobre todo {NAMES.get(r['stage'], r['stage'])})"
                            for r in lost[:10]), ""]
    if not data["kinds"]:
        return "\n".join(lines + ["Todavía no hay vídeos terminados en este periodo.", ""] + tail) + "\n"
    for kind, entry in data["kinds"].items():
        lines += [f"## {kind.capitalize()} · {entry['videos']} vídeos · mediana {duration(entry['medianTotal'])} por vídeo", "",
                  "| Etapa | Trabajo (mediana) | Máximo | Parte del total | Espera de turno (mediana) | "
                  "Intentos fallidos (suma: trabajo + espera) |", "|---|---|---|---|---|---|"]
        for row in entry["stages"]:
            if row["max"] < 1 and not row.get("failed") and not row.get("medianWait"):
                continue
            failed = (f"{duration(row['failed'])} + {duration(row['failedWait'])}"
                      if row.get("failed") or row.get("failedWait") else "—")
            lines.append(f"| {row['name']} | {duration(row['median'])} | {duration(row['max'])} | {row['share']:.0%} | "
                         f"{duration(row.get('medianWait', 0.0))} | {failed} |")
        if "sourcingPerShot" in entry:
            lines += ["", f"Buscar material: **{entry['sourcingPerShot']:.0f} s por plano** (mediana)."]
        if entry.get("youtubeHours"):
            lines.append("Peticiones a YouTube (suma de todos los vídeos, con esperas por 429): "
                         + " · ".join(f"{a} {h:.1f} h" for a, h in entry["youtubeHours"].items()))
        lines += ["", "Los más lentos: " + ", ".join(f"{v['slug']} ({duration(v['total'])})" for v in entry["slowest"]), ""]
    return "\n".join(lines + tail) + "\n"


def write(root: Path, days: float = 30) -> str:
    text = markdown(report(root, days))
    path = root / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text
