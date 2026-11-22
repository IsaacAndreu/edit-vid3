"""«Qué hacer ahora» (prompt «qué canales empezar, cuáles doblar», part 4): three short lists, each entry with its
numbers, what it does NOT know, and a button.

- Empezar: measured topics with a gap in some language (Huecos + pipeline/idiomas.py), whether the tool can make
  them (`fit`, and whether footage or photos exist: a niche with nothing downloadable is not for it), with which
  formula (if references were measured: pipeline/formula.py), the money per view only from `radar.rpm` (the owner's
  own numbers; empty = no income is invented) and the effort (videos a week the niche asks, cost per video).
- Doblar: own channel → language (pipeline/doblar.py).
- Dejar o cambiar: own channels whose last `radar.dejar_videos` long videos are all under their median, or whose
  niche filled up (its Huecos score fell to «saturado»).

Only what was MEASURED becomes a recommendation; an idea of the model nobody measured stays an idea elsewhere. The
autocomplete counts and recent views are signs of searches, never «searches».
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

SIGNS_NOTE = ("YouTube no publica cuántas búsquedas tiene un tema: las sugerencias del autocompletado y las visitas "
              "de los vídeos recientes son indicios, no búsquedas.")


def _rpm(cfg: dict[str, Any], lang: str, category: str = "") -> float | None:
    table = (cfg.get("rpm") or {}).get(lang)
    if isinstance(table, (int, float)):
        return float(table)
    if isinstance(table, dict):
        value = table.get(category) if category else None
        value = value if value is not None else table.get("default")
        return float(value) if isinstance(value, (int, float)) else None
    return None


def cost_per_video(root: Path) -> float | None:
    """The median API spend of the finished videos (work/<vídeo>/costs.json), what the program already measures."""

    totals = []
    for path in (root / "work").glob("*/costs.json") if (root / "work").is_dir() else []:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        rows = data.get("entries") if isinstance(data, dict) else data
        value = sum(float(r.get("usd") or r.get("cost") or 0) for r in rows or [] if isinstance(r, dict))
        if value > 0 and (root / "out" / path.parent.name / "video-final.mp4").is_file():
            totals.append(value)
    return round(statistics.median(totals), 2) if totals else None


def can_make(item: dict[str, Any], lang_numbers: dict[str, Any] | None) -> tuple[bool | None, str]:
    """Whether the tool can make it well: the model's fit (0-10) AND whether there is material — videos found to
    take footage from. None when nothing says."""

    fit = item.get("fit")
    found = len((lang_numbers or {}).get("examples") or item.get("examples") or [])
    if fit is None and not found:
        return None, "sin dato de si la herramienta lo puede hacer"
    if fit is not None and fit < 5:
        return False, f"encaje {fit}/10: necesita cara, cámara o gameplay propio"
    if not found:
        return False, "no aparece metraje descargable del tema"
    return True, f"encaje {fit if fit is not None else '?'}/10 y hay metraje del tema"


def start(root: Path, cfg: dict[str, Any], formulas: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    from .huecos import ranked
    from .idiomas import NAMES

    effort = cost_per_video(root)
    out = []
    for item in ranked(root, 80):
        by_lang = (item.get("idiomas") or {}).get("languages") or {}
        rows = ((item.get("idiomas") or {}).get("readings") or {}).get("start") or []
        if not rows and item.get("verdict") in ("hueco", "hueco en inglés"):      # measured in Spanish only
            rows = [{"lang": "es", "score": item.get("score"), "verdict": item.get("verdict"), "demand": item.get("demand"),
                     "recent": item.get("recent"), "gap": item.get("englishGap"), "smallWins": item.get("smallWins")}]
        for r in rows[:2]:
            ok, why_fit = can_make(item, by_lang.get(r["lang"]))
            if ok is False:
                continue
            numbers = by_lang.get(r["lang"]) or {}
            rpm = _rpm(cfg, r["lang"], str(item.get("category") or ""))
            unknown = [] if rpm is not None else ["cuánto se gana por visita (rellena radar.rpm con lo que ves en tus canales)"]
            if ok is None:
                unknown.append(why_fit)
            if not numbers and not item.get("idiomas"):
                unknown.append("solo medido en español y frente al inglés")
            formula = formulas.get(str(item.get("name") or "").casefold())
            out.append({
                "kind": "empezar", "topic": item.get("name"), "query": numbers.get("query") or item.get("query_es"),
                "lang": r["lang"], "langName": NAMES.get(r["lang"], r["lang"]), "score": r.get("score"),
                "verdict": r.get("verdict"), "demand": r.get("demand"), "recent": r.get("recent"),
                "smallWins": r.get("smallWins"), "gap": r.get("gap"), "suggestions": numbers.get("suggestions"),
                "fit": why_fit, "rpm": rpm,
                "income": round(r["demand"] * rpm / 1000, 2) if rpm is not None and r.get("demand") else None,
                "videosPerWeek": round(max(1.0, (r.get("recent") or 0) / 4 / max(1, numbers.get("recentChannels") or 1)), 1),
                "costPerVideo": effort, "formula": formula.get("summary") if formula else None,
                "why": item.get("why") or "", "unknown": unknown,
                "measured": (item.get("idiomas") or {}).get("date") or item.get("date"),
            })
    out.sort(key=lambda e: -(e.get("score") or 0))
    return out[:limit]


def leave(root: Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Own channels that should stop or change: the last N long videos all under the channel's median, or the niche
    filled up (its search, measured in Huecos, now «saturado»)."""

    from .context import RunContext
    from .doblar import own_channels
    from .huecos import _read, key
    from .mychannel import saved

    n = int(cfg.get("dejar_videos", 8))
    gaps = _read(root)["items"]
    out = []
    for channel in sorted(own_channels(root)):
        report = saved(root, channel) or {}
        long = [v for v in report.get("videos") or [] if not v.get("short") and v.get("ratio") is not None][:n]
        reasons = []
        if len(long) >= n and all(v["ratio"] < 1 for v in long):
            reasons.append(f"sus últimos {n} vídeos largos están todos por debajo de su mediana "
                           f"(el mejor, {max(v['ratio'] for v in long):.1f}x)")
        queries = (RunContext.create("_radar", root=root, channel=channel).config.get("lab") or {}).get("queries") or []
        for q in queries[:2]:
            gap = gaps.get(key(str(q)))
            if gap and gap.get("verdict") == "saturado":
                history = gap.get("history") or []
                fell = f" (de {history[0]['score']} a {history[-1]['score']})" if len(history) >= 2 else ""
                reasons.append(f"su nicho «{q}» está saturado{fell}")
        if reasons:
            out.append({"kind": "dejar", "channel": channel, "reasons": reasons,
                        "median": (report.get("numbers") or {}).get("medianLong"),
                        "unknown": [] if report else ["no hay datos de Mi canal: analízalo primero"]})
    return out


def build(root: Path) -> dict[str, Any]:
    from . import doblar, idiomas
    from .context import RunContext

    base = RunContext.create("_radar", root=root)
    cfg = base.section("radar")
    formulas = {}
    for path in (root / "out" / "_formulas").glob("*.json") if (root / "out" / "_formulas").is_dir() else []:
        try:
            data = json.loads(path.read_text("utf-8"))
            formulas[str(data.get("niche") or path.stem).casefold()] = data
        except (OSError, ValueError):
            continue
    dub = doblar.saved(root)
    quota = None
    try:
        from .ytapi import YouTubeAPI

        api = YouTubeAPI(base)
        if api.keys:
            budget = idiomas.Budget(root, api, cfg)
            quota = {"unitsLeft": budget.left(), "cap": budget.cap, "reserve": budget.reserve,
                     "topicsToday": budget.topics_today(len(idiomas.configured(cfg)))}
    except Exception:
        quota = None
    from . import aprender

    starting = start(root, cfg, formulas)
    dubbing = (dub.get("rows") or [])[:8]
    aprender.record(root, [*starting, *({**r, "kind": "doblar"} for r in dubbing)])   # each one once, with its date
    return {"start": starting, "dub": dubbing, "dubChecks": dub.get("checks") or [],
            "dubWaiting": dub.get("waiting") or [], "dubDate": dub.get("date"), "leave": leave(root, cfg),
            "quota": quota, "languages": idiomas.configured(cfg), "rpmSet": bool(cfg.get("rpm")),
            "signsNote": SIGNS_NOTE, "learned": aprender.report(root)}
