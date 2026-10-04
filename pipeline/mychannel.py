"""Analysis of your own channel (in the studio: «Mi canal»), from the YouTube Data API.

Every video is compared with the median of its own kind (Shorts with Shorts, long with long): 1x = a normal video of
yours. From there:
- Números: subscribers, views, videos, median views per kind, the last 28 days.
- Evolución: per month, how many videos and how they did.
- Ganadores: the videos that beat your normal the most (and the ones that did worst).
- Horarios: day × hour heat map (your time zone, `mychannel.timezone`) and per day of the week.
- Constancia: videos per month for the last 12 months, and the longest stop.
- Títulos: what the titles of the videos that work have (short, CAPITALS, numbers, emojis, ¡!, questions…).
- Duración: which lengths work.
- Temas: the LLM groups the titles by topic; the numbers come from your real views.
Your channel per profile: set it in the studio (Ajustes → Mi canal) or `ideas.my_channel` in canales/<canal>.yaml.
Saved in out/_canal/<canal>.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .context import RunContext

FOLDER = "out/_canal"
SHORT_SECONDS = 180
DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
DAY_NAMES = dict(zip(DAYS, ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]))
BLOCKS = ["0–3", "3–6", "6–9", "9–12", "12–15", "15–18", "18–21", "21–24"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F1E6-\U0001F1FF]")

TOPICS_SYSTEM = """
Agrupa los títulos de vídeos de un canal de YouTube por TEMA (de qué trata el vídeo, no su formato). Entre 4 y 9 temas,
cada uno con al menos 2 vídeos; nombres cortos en español (2-5 palabras). Cada vídeo en un solo tema.
Devuelve SOLO JSON: {"topics": [{"name": "…", "videos": [números de la lista]}]}
""".strip()

TITLE_TRAITS: list[tuple[str, str, Any]] = [
    ("short", "Título corto (< 40 letras)", lambda t: len(t) < 40),
    ("long", "Título largo (> 60 letras)", lambda t: len(t) > 60),
    ("caps", "Palabras en MAYÚSCULAS", lambda t: any(len(w) >= 3 and w.isupper() and w.isalpha() for w in re.findall(r"\w+", t))),
    ("numbers", "Tiene números", lambda t: bool(re.search(r"\d", t))),
    ("emoji", "Tiene emojis", lambda t: bool(EMOJI.search(t))),
    ("exclaim", "Tiene signos ! ¡", lambda t: "!" in t or "¡" in t),
    ("question", "Es una pregunta", lambda t: "?" in t or "¿" in t),
    ("money", "Habla de dinero (€, $, millones)", lambda t: bool(re.search(r"[€$]|millon|billon|dinero", t, re.I))),
    ("colon", "Tiene «:» o «|»", lambda t: ":" in t or "|" in t),
]


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def handle_for(root: Path, channel: str) -> str:
    from . import budget

    mine = (budget.settings(root).get("my_channels") or {}).get(channel)
    if mine:
        return str(mine)
    return str(RunContext.create("_canal", root=root, channel=channel).section("ideas").get("my_channel") or "")


def _zone(name: str):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:                       # Windows without tzdata: this machine's time zone
        return datetime.now().astimezone().tzinfo


def _when(video: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(video["published"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _times(x: float | None) -> float | None:
    return round(x, 2) if x is not None else None


def score(videos: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Each video's views / the median of its kind (videos under 3 days old are left out of the medians)."""

    now = now or datetime.now(timezone.utc)
    out = []
    for index, v in enumerate(videos):
        when = _when(v)
        out.append({**v, "index": index, "short": (v.get("duration") or 0) <= SHORT_SECONDS, "when": when,
                    "ageDays": (now - when).total_seconds() / 86400 if when else 0})
    for kind in (True, False):
        mature = [v["views"] for v in out if v["short"] is kind and v["ageDays"] >= 3]
        median = _median(mature) or 1
        for v in out:
            if v["short"] is kind:
                v["ratio"] = round(v["views"] / median, 2) if v["ageDays"] >= 3 else None
                v["kindMedian"] = median
    return out


def _cell(videos: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = [v["ratio"] for v in videos if v["ratio"] is not None]
    return {"count": len(videos), "ratio": _times(_median(ratios))}


def analyse(videos: list[dict[str, Any]], channel: dict[str, Any], tz_name: str = "Europe/Madrid",
            now: datetime | None = None, topics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    zone = _zone(tz_name)
    scored = [v for v in score(videos, now) if v["when"]]
    rated = [v for v in scored if v["ratio"] is not None]
    long = [v for v in scored if not v["short"]]
    shorts = [v for v in scored if v["short"]]
    recent = [v for v in scored if v["ageDays"] <= 28]

    # Números
    numbers = {"subscribers": channel.get("subscribers"), "views": channel.get("viewCount"),
               "videos": channel.get("videoCount"), "analysed": len(scored), "long": len(long), "shorts": len(shorts),
               "medianLong": _median([v["views"] for v in long if v["ageDays"] >= 3]),
               "medianShort": _median([v["views"] for v in shorts if v["ageDays"] >= 3]),
               "last28": {"videos": len(recent), "views": sum(v["views"] for v in recent)},
               "hits": sum(1 for v in rated if v["ratio"] >= 2)}

    # Evolución y constancia (last 12 months, oldest first)
    months = []
    first = (now.astimezone(zone).replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    for back in range(11, -1, -1):
        y, m = first.year, first.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        inside = [v for v in scored if (lambda w: (w.year, w.month) == (y, m))(v["when"].astimezone(zone))]
        months.append({"month": f"{MONTHS[m - 1]} {str(y)[2:]}", "long": sum(1 for v in inside if not v["short"]),
                       "shorts": sum(1 for v in inside if v["short"]),
                       "views": sum(v["views"] for v in inside), **{"ratio": _cell(inside)["ratio"]}})
    gap, best_gap = 0, (0, -1)
    for i, month in enumerate(months):
        gap = gap + 1 if month["long"] + month["shorts"] == 0 else 0
        if gap > best_gap[0]:
            best_gap = (gap, i)
    consistency_note = None
    if best_gap[0] >= 2:
        end = best_gap[1]
        start = end - best_gap[0] + 1
        before = months[max(0, start - 3): start]
        rate = sum(m["long"] + m["shorts"] for m in before) / len(before) if before else 0
        consistency_note = (f"Entre {months[start]['month']} y {months[end]['month']} no subiste ningún vídeo: "
                            f"{best_gap[0]} meses parado." + (f" En los {len(before)} meses anteriores subías "
                                                              f"{rate:.1f}".replace(".", ",") + " por mes." if before else ""))

    # Ganadores
    winners = sorted(rated, key=lambda v: -v["ratio"])[:10]
    losers = sorted(rated, key=lambda v: v["ratio"])[:5]

    # Horarios
    grid = [[[] for _ in BLOCKS] for _ in DAYS]
    for v in rated:
        local = v["when"].astimezone(zone)
        grid[local.weekday()][local.hour // 3].append(v)
    heat = [[_cell(c) for c in row] for row in grid]
    per_day = [{"day": d, **_cell([v for c in grid[i] for v in c])} for i, d in enumerate(DAYS)]
    slots = [(DAYS[d], BLOCKS[b], heat[d][b]) for d in range(7) for b in range(8) if heat[d][b]["count"] >= 3]
    best_slot = max(slots, key=lambda s: s[2]["ratio"] or 0, default=None)

    # Títulos
    traits = []
    for key, name, test in TITLE_TRAITS:
        yes = [v["ratio"] for v in rated if test(v["title"])]
        no = [v["ratio"] for v in rated if not test(v["title"])]
        if len(yes) >= 3 and len(no) >= 3:
            traits.append({"key": key, "name": name, "count": len(yes),
                           "factor": round(statistics.median(yes) / max(0.01, statistics.median(no)), 2)})
    traits.sort(key=lambda t: -t["factor"])
    typical_length = int(statistics.median(len(v["title"]) for v in scored)) if scored else 0

    # Duración (long videos)
    buckets = [("< 8 min", 0, 480), ("8–12 min", 480, 720), ("12–20 min", 720, 1200), ("20+ min", 1200, 10**9)]
    durations = [{"name": n, **_cell([v for v in long if a <= v["duration"] < b and v["ratio"] is not None])}
                 for n, a, b in buckets]

    # Temas
    topic_rows = []
    for topic in topics or []:
        wanted = {i for i in topic.get("videos", []) if isinstance(i, int)}     # numbers in the list given to the LLM
        inside = [v for v in scored if v["index"] in wanted]
        ratios = [v["ratio"] for v in inside if v["ratio"] is not None]
        if len(inside) < 2:
            continue
        best = max(inside, key=lambda v: v["ratio"] or 0)
        topic_rows.append({"name": topic["name"], "count": len(inside), "ratio": _times(_median(ratios)),
                           "hits": sum(1 for r in ratios if r >= 2), "medianViews": _median([v["views"] for v in inside]),
                           "thumbnail": best.get("thumbnail"), "best": best["title"]})
    topic_rows.sort(key=lambda t: -(t["ratio"] or 0))

    tips = []
    if best_slot:
        tips.append(f"Tu mejor franja: los {DAY_NAMES[best_slot[0]]} de {best_slot[1]} h — {str(best_slot[2]['ratio']).replace('.', ',')}x "
                    f"lo normal en {best_slot[2]['count']} vídeos.")
    if traits and traits[0]["factor"] >= 1.15:
        tips.append(f"En tus títulos funciona: {traits[0]['name'].lower()} ({str(traits[0]['factor']).replace('.', ',')}x).")
    if traits and traits[-1]["factor"] <= 0.85:
        tips.append(f"Evita: {traits[-1]['name'].lower()} ({round((1 - traits[-1]['factor']) * 100)} % menos).")
    if topic_rows:
        tips.append(f"Tu tema más fuerte: «{topic_rows[0]['name']}» ({str(topic_rows[0]['ratio']).replace('.', ',')}x).")
    if consistency_note:
        tips.append(consistency_note)

    clean = lambda v: {k: v.get(k) for k in ("id", "title", "views", "ratio", "thumbnail", "url", "published", "duration", "short")}  # noqa: E731
    return {
        "channel": {k: channel.get(k) for k in ("id", "title", "handle", "thumbnail", "subscribers")},
        "generated": now.isoformat(timespec="seconds"), "timezone": tz_name,
        "numbers": numbers, "months": months, "consistencyNote": consistency_note,
        "winners": [clean(v) for v in winners], "losers": [clean(v) for v in losers],
        "heat": heat, "days": DAYS, "blocks": BLOCKS, "perDay": per_day,
        "titles": {"typicalLength": typical_length, "traits": traits},
        "durations": durations, "topics": topic_rows, "tips": tips,
        "videos": [clean(v) for v in sorted(scored, key=lambda v: v["when"], reverse=True)],
    }


def group_topics(ctx: RunContext, titles: list[str]) -> list[dict[str, Any]]:
    """The LLM groups the titles (cached by the list of titles, so it costs once per new video)."""

    if len(titles) < 6:
        return []
    from .llm import complete_json

    path = ctx.root / FOLDER / "temas-cache.json"
    cache = _read(path) or {}
    digest = hashlib.sha256("\n".join(titles).encode()).hexdigest()[:20]
    if digest in cache:
        return cache[digest]
    result = complete_json(ctx, stage="mychannel", section="planner", system=TOPICS_SYSTEM, max_tokens=4000,
                           user="\n".join(f"{i}. {t}" for i, t in enumerate(titles)))
    topics = [t for t in result.get("topics", []) if isinstance(t, dict) and t.get("name") and t.get("videos")]
    cache[digest] = topics
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return topics


def run(root: Path, channel: str) -> dict[str, Any]:
    from .ytapi import YouTubeAPI

    handle = handle_for(root, channel)
    if not handle:
        raise ValueError(f"Falta tu canal de {channel}: ponlo en Ajustes → Mi canal")
    ctx = RunContext.create("_canal", root=root, channel=channel)
    cfg = ctx.section("mychannel")
    api = YouTubeAPI(ctx)
    if not api.keys:
        raise ValueError("El análisis del canal necesita YOUTUBE_API_KEYS en .env")
    info = api.channel(handle)
    videos = api.uploads(info["uploads"], int(cfg.get("max_videos", 400))) if info.get("uploads") else []
    videos = [v for v in videos if v.get("live", "none") == "none"]
    ordered = sorted(videos, key=lambda v: v.get("published", ""), reverse=True)
    topics: list[dict[str, Any]] = []
    try:
        topics = group_topics(ctx, [v["title"] for v in ordered])
    except Exception as error:
        print(f"Temas: {str(error)[:160]}")
    report = analyse(ordered, info, str(cfg.get("timezone", "Europe/Madrid")), topics=topics)
    report["profile"] = channel
    path = root / FOLDER / f"{channel}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
    return report


def saved(root: Path, channel: str) -> dict[str, Any] | None:
    return _read(root / FOLDER / f"{channel}.json")
