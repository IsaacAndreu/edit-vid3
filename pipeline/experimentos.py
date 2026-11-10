"""The studio's «Experimentos» (Crecer ▾): what each video tried and how it did, so a change is kept or dropped fast.

Every finished video records what it tried by itself — its format, the search (per shot or per scene), its length and
its cutting pace — plus the free labels you give it in the studio («miniatura con cara», «gancho con pregunta»). How it
did: its views at 7 days (pipeline/agenda.py records them) against the median of its channel at 7 days, so videos of
different channels can be pooled («1.4×» = 40 % more than that channel usually gets). Retention and CTR are not in the
public YouTube API: copy them from YouTube Studio into the video's row and they count too.

For each thing tried, its options are compared on the videos that have a result: the median of each side, and a
verdict only with at least `MIN_VIDEOS` videos on each side and a clear gap (`CLEAR` = 25 %); before that, how many
videos are still missing. One change at a time is what makes the verdicts mean something.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

FILE = "out/_experimentos.json"        # {slug: {"tags": [...], "retention30": 62, "retentionAvg": 38, "ctr": 5.1}}
MIN_VIDEOS = 3
CLEAR = 1.25
METRICS = ("retention30", "retentionAvg", "ctr")


def notes(root: Path) -> dict[str, dict[str, Any]]:
    try:
        return json.loads((root / FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def set_notes(root: Path, slug: str, body: dict[str, Any]) -> dict[str, Any]:
    """Labels and the Studio numbers of one video (a number left empty is removed)."""

    data = notes(root)
    entry = dict(data.get(slug) or {})
    if "tags" in body:
        tags = body.get("tags") or []
        tags = [str(t) for t in (tags.split(",") if isinstance(tags, str) else tags)]
        entry["tags"] = list(dict.fromkeys(" ".join(t.split()).lower()[:40] for t in tags if t.strip()))[:6]
    for key in METRICS:
        if key in body:
            try:
                value = float(str(body[key]).replace(",", ".").replace("%", "")) if str(body[key]).strip() else None
            except ValueError:
                raise ValueError(f"{key}: no es un número") from None
            if value is None:
                entry.pop(key, None)
            elif not 0 <= value <= 100:
                raise ValueError(f"{key}: debe estar entre 0 y 100")
            else:
                entry[key] = round(value, 1)
    data[slug] = {k: v for k, v in entry.items() if v not in (None, [], "")}
    if not data[slug]:
        del data[slug]
    (root / FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / FILE).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data.get(slug, {})


def _length(minutes: float) -> str | None:
    if not minutes:
        return None
    return "menos de 8 min" if minutes < 8 else "8-12 min" if minutes <= 12 else "más de 12 min"


def _pace(cuts: float) -> str | None:
    if not cuts:
        return None
    return "pausado (<14 cortes/min)" if cuts < 14 else "medio (14-20)" if cuts <= 20 else "rápido (>20)"


def tried(root: Path, slug: str, production: dict[str, Any]) -> dict[str, str]:
    """What this video tried, read from how it was made."""

    from .context import RunContext

    out: dict[str, str] = {}
    try:
        ctx = RunContext.create(slug, root=root)
        out["Formato"] = str(ctx.config.get("format") or "el del canal")
        scenes = (ctx.section("sourcing").get("youtube") or {}).get("scene_search")
        out["Búsqueda"] = "por escenas" if scenes else "por plano"
    except Exception:
        pass
    if (length := _length(production.get("duration", 0) / 60)):
        out["Duración"] = length
    if (pace := _pace(production.get("cutsPerMin") or 0)):
        out["Ritmo"] = pace
    return out


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def compare(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each thing tried (format, search, length, pace, each label): its options side by side and a verdict."""

    factors: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        for factor, option in row["tried"].items():
            factors.setdefault(factor, {}).setdefault(option, []).append(row)
        for tag in row.get("tags") or []:
            factors.setdefault(f"Etiqueta «{tag}»", {}).setdefault("con", []).append(row)
    for tag_factor, options in factors.items():          # a label against the videos of the same channels without it
        if tag_factor.startswith("Etiqueta"):
            tag = tag_factor[len("Etiqueta «"):-1]
            channels = {r["channel"] for r in options["con"]}
            options["sin"] = [r for r in rows if r["channel"] in channels and tag not in (r.get("tags") or [])]
    out = []
    for factor, options in factors.items():
        sides = []
        for option, members in options.items():
            scored = [r["score"] for r in members if r.get("score") is not None]
            side = {"option": option, "videos": len(members), "withResult": len(scored), "score": _median(scored),
                    "slugs": [r["slug"] for r in members][:12]}
            for key in METRICS:
                side[key] = _median([r[key] for r in members if r.get(key) is not None])
            sides.append(side)
        sides.sort(key=lambda s: -(s["score"] or 0))
        if len(sides) < 2:
            continue                                     # nothing to compare yet: everything tried the same
        ready = [s for s in sides if s["withResult"] >= MIN_VIDEOS and s["score"]]
        best, worst = (ready[0], ready[-1]) if len(ready) >= 2 else (None, None)
        if best and best["score"] >= CLEAR * worst["score"]:
            x = lambda v: f"{v:.1f}".replace(".", ",") + "×"  # noqa: E731
            verdict = {"kind": "gana", "text": f"«{best['option']}» va mejor: {x(best['score'])} frente a "
                                               f"{x(worst['score'])} de «{worst['option']}» ({best['withResult']} y "
                                               f"{worst['withResult']} vídeos)"}
        elif best:
            verdict = {"kind": "empate", "text": "Sin diferencia clara (menos del 25 %): no merece la pena seguir probando esto"}
        else:
            missing = sum(max(0, MIN_VIDEOS - s["withResult"]) for s in sides[:2])
            verdict = {"kind": "falta", "text": f"Faltan {missing} vídeo(s) con 7 días para decidir (mínimo {MIN_VIDEOS} por opción)"}
        out.append({"factor": factor, "options": sides, "verdict": verdict})
    order = {"gana": 0, "empate": 2, "falta": 1}
    return sorted(out, key=lambda f: (order[f["verdict"]["kind"]], f["factor"]))


def report(root: Path) -> dict[str, Any]:
    from . import agenda
    from .estadisticas import production

    listed = [v for v in agenda.videos(root) if v["status"] in ("hecho", "subido")]
    history = agenda.load(root).get("views") or {}
    by_note = notes(root)
    rows = []
    for video in listed:
        made = production(root, video["slug"])
        week = (history.get(video["slug"]) or {}).get("7d")
        entry = by_note.get(video["slug"]) or {}
        rows.append({"slug": video["slug"], "channel": video["channel"], "title": video["title"] or video["slug"],
                     "status": video["status"], "published": video["published"], "views7d": week,
                     "tried": tried(root, video["slug"], made), "tags": entry.get("tags") or [],
                     **{k: entry.get(k) for k in METRICS}})
    medians: dict[str, float] = {}
    for channel in {r["channel"] for r in rows}:
        weeks = [r["views7d"] for r in rows if r["channel"] == channel and r["views7d"]]
        if weeks:
            medians[channel] = statistics.median(weeks)
    for row in rows:
        median = medians.get(row["channel"])
        row["score"] = round(row["views7d"] / median, 2) if row["views7d"] is not None and median else None
    rows.sort(key=lambda r: (r["published"] or "9999", r["slug"]), reverse=True)
    return {"videos": rows, "comparisons": compare(rows), "medians": {k: int(v) for k, v in medians.items()},
            "minVideos": MIN_VIDEOS}
