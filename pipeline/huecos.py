"""«Huecos»: topics with an audience and little competition in Spanish — where a new channel can get in.

The radar already finds what works (outliers, small channels that explode). This measures the other half: how
crowded a topic is. For each topic, with the YouTube Data API (4 searches, ~400 units):
- Demand in Spanish: median views of the most viewed long videos of the last year, and views per day.
- Competition: how many long videos in Spanish were uploaded about it in the last 30 days (and by how many
  channels), and how much of the top belongs to big channels (≥ 500k subscribers).
- Small channels winning: top videos from channels under 50k subscribers with far more views than subscribers —
  proof that the algorithm hands the topic to newcomers.
- The English gap: the same topic's demand in English against Spanish. Big in English, thin in Spanish = the
  easiest content arbitrage for a faceless documentary channel.
- Searched: how many YouTube autocomplete suggestions the query has in Spanish (free, no quota).

Topics come from an LLM that reads today's signals (rising channels' formats, discovered niches) plus your own
channels, and from the studio («Medir un tema»). Every measure is kept with its history in out/_radar/huecos.json,
so a topic that is filling up shows it.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .context import RunContext

FILE = "out/_radar/huecos.json"

PROPOSE_SYSTEM = """
Eres analista de nichos de YouTube para un creador con una herramienta que hace documentales SIN CARA en español
(guion leído por voz sintética, clips de archivo, fotos, mapas y gráficos animados, 8-15 min).
Busca HUECOS: temas con público que en español casi nadie cubre bien (mucho en inglés y poco en español, temas
evergreen sin un canal de referencia en español, subnichos concretos dentro de nichos grandes). Evita lo saturado
(true crime genérico, curiosidades genéricas, misterios genéricos, finanzas personales, motivación).
Te paso SEÑALES de hoy (formatos y nichos que están creciendo) y los nichos YA CONOCIDOS (no los repitas).
Devuelve SOLO JSON con {count} temas, del más prometedor al menos:
{"niches": [{"name": "nombre corto en español", "query_es": "búsqueda de YouTube en español, 2-5 palabras",
  "query_en": "la misma búsqueda en inglés", "why": "por qué crees que hay hueco (1 frase)",
  "fit": 0-10 (10 = la herramienta lo hace igual o mejor que un humano; 0 = necesita cara, cámara o gameplay),
  "ideas": ["3 títulos concretos de primeros vídeos"]}]}
""".strip()

EVALUATE_SYSTEM = """
Eres analista de nichos de YouTube para documentales SIN CARA en español (voz sintética, clips de archivo, gráficos).
Te paso un tema. Devuelve SOLO JSON: {"name": "nombre corto en español", "query_es": "búsqueda en español, 2-5
palabras", "query_en": "la misma en inglés", "fit": 0-10, "why": "1 frase", "ideas": ["3 títulos de primeros vídeos"]}
""".strip()

STOP = set("""de la el los las un una unos unas y o en del al por para con sin que como qué cómo su sus lo the of and
a an in on for to with how why what is are""".split())


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


def key(query: str) -> str:
    return " ".join(query.casefold().split())


def _age_days(iso: str) -> float:
    try:
        return max(1.0, (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 86400)
    except (ValueError, AttributeError):
        return 365.0


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-záéíóúñü0-9]+", text.casefold()) if len(w) >= 4 and w not in STOP}


def relevant(video: dict[str, Any], query: str) -> bool:
    """A search result really about the query: it shares a meaningful word (searches by date bring a lot of noise)."""

    words = _words(query)
    return not words or bool(words & _words(f"{video.get('title', '')} {video.get('description', '')[:200]}"))


def suggestions(query: str, language: str = "es") -> int | None:
    """YouTube autocomplete suggestions for the query (0-10): people type it. None when it cannot be asked."""

    try:
        import requests

        response = requests.get("https://suggestqueries.google.com/complete/search",
                                params={"client": "firefox", "ds": "yt", "hl": language, "q": query}, timeout=6)
        response.raise_for_status()
        data = json.loads(response.content.decode(response.encoding or "utf-8", "replace"))
        return len(data[1]) if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else None
    except Exception:
        return None


def score(m: dict[str, Any]) -> tuple[float, str]:
    """0-10 and a verdict from the measures: demand, competition, small channels winning, big channels, English gap."""

    demand = (math.log10(max(1, m["demand"])) - 3) * 3.3                  # 1k → 0, 10k → 3.3, 100k → 6.6, 1M → 10
    crowd = 10 - m["recent"] / 4                                           # 0 uploads a month → 10, 40 → 0
    small = m["smallWins"] * 2.0
    big = 10 * (1 - m["bigShare"])
    gap = math.log2(m["englishGap"]) * 2.5 if m["englishGap"] > 1 else 0.0
    parts = [(demand, 0.35), (crowd, 0.25), (small, 0.15), (big, 0.10), (gap, 0.15)]
    value = sum(max(0.0, min(10.0, x)) * w for x, w in parts)
    if m.get("staleYears", 0) >= 2 and m["recent"] <= 10:                  # the top is old and nobody renews it
        value += 0.5
    value = round(max(0.0, min(10.0, value)), 1)
    if demand < 3:
        verdict = "sin demanda"
    elif crowd < 3 or m["bigShare"] >= 0.7:
        verdict = "saturado"
    elif value >= 6.5:
        verdict = "hueco"
    elif m["englishGap"] >= 4 and demand >= 4:
        verdict = "hueco en inglés"
    else:
        verdict = "a vigilar"
    return value, verdict


def measure(api: Any, query_es: str, query_en: str = "") -> dict[str, Any]:
    """The numbers of one topic (4 searches + a few cheap lookups)."""

    top = [v for v in api.videos(api.search(query_es, days=365, order="viewCount", language="es", max_results=50))
           if v["duration"] >= 240 and v.get("live", "none") == "none"][:20]
    recent = [v for v in api.videos(api.search(query_es, days=30, order="date", language="es", max_results=50))
              if v["duration"] >= 240 and relevant(v, query_es)]
    alltime = [v for v in api.videos(api.search(query_es, order="viewCount", language="es", max_results=10))
               if v["duration"] >= 240]
    english = []
    if query_en:
        english = [v for v in api.videos(api.search(query_en, days=365, order="viewCount", language="en", max_results=25))
                   if v["duration"] >= 240][:20]
    subs = {c["id"]: c.get("subscribers") for c in (api.channels(sorted({v["channelId"] for v in top if v.get("channelId")}))
                                                    if top else [])}
    views = [v["views"] for v in top]
    demand = int(statistics.median(views)) if views else 0
    per_day = int(statistics.median([v["views"] / _age_days(v["published"]) for v in top])) if top else 0
    total = sum(views) or 1
    big = sum(v["views"] for v in top if (subs.get(v["channelId"]) or 0) >= 500_000)
    small = [v for v in top if subs.get(v["channelId"]) is not None and subs[v["channelId"]] < 50_000
             and v["views"] >= max(10_000, 2 * subs[v["channelId"]])]
    en_demand = int(statistics.median([v["views"] for v in english])) if english else 0
    stale = statistics.median([_age_days(v["published"]) / 365 for v in alltime]) if alltime else 0.0
    m = {"demand": demand, "perDay": per_day, "recent": len(recent),
         "recentChannels": len({v["channelId"] for v in recent}), "bigShare": round(big / total, 2),
         "smallWins": len(small), "englishDemand": en_demand,
         "englishGap": round(en_demand / max(demand, 1), 1) if en_demand else 0.0, "staleYears": round(stale, 1),
         "searched": suggestions(query_es)}
    m["score"], m["verdict"] = score(m)
    keep = ("id", "title", "channel", "views", "thumbnail", "url", "published")
    m["examples"] = [{**{k: v.get(k) for k in keep}, "subscribers": subs.get(v["channelId"])} for v in
                     sorted(small or top, key=lambda v: -v["views"])[:4]]
    m["englishExamples"] = [{k: v.get(k) for k in keep} for v in english[:3]]
    return m


def _remember(root: Path, entry: dict[str, Any], today: str) -> dict[str, Any]:
    data = _read(root)
    k = key(entry["query_es"])
    old = data["items"].get(k) or {}
    history = [h for h in old.get("history", []) if h.get("date") != today][-20:]
    history.append({"date": today, "score": entry["score"], "demand": entry["demand"], "recent": entry["recent"]})
    entry = {**old, **entry, "history": history, "firstSeen": old.get("firstSeen", today), "date": today}
    data["items"][k] = entry
    if len(data["items"]) > 300:                                            # keep the best and the latest
        ranked = sorted(data["items"].items(), key=lambda kv: (kv[1].get("date", ""), kv[1].get("score", 0)))
        data["items"] = dict(ranked[-300:])
    _write(root, data)
    return entry


def ranked(root: Path, limit: int = 40) -> list[dict[str, Any]]:
    items = list(_read(root)["items"].values())
    for item in items:
        h = item.get("history") or []
        item["trend"] = round(h[-1]["score"] - h[-2]["score"], 1) if len(h) >= 2 else None
    return sorted(items, key=lambda i: (-i.get("score", 0), i.get("name", "")))[:limit]


def _clean(n: dict[str, Any]) -> dict[str, Any] | None:
    query = " ".join(str(n.get("query_es") or "").split())[:80]
    if not query:
        return None
    try:
        fit = max(0, min(10, int(n.get("fit"))))
    except (TypeError, ValueError):
        fit = None
    return {"name": str(n.get("name") or query)[:60], "query_es": query,
            "query_en": " ".join(str(n.get("query_en") or "").split())[:80], "why": str(n.get("why") or "")[:240],
            "fit": fit, "ideas": [str(i)[:120] for i in (n.get("ideas") or []) if str(i).strip()][:3]}


def propose(ctx: RunContext, signals: list[str], known: list[str], count: int) -> list[dict[str, Any]]:
    from .llm import complete_json

    result = complete_json(ctx, stage="radar", section="planner", max_tokens=2200, use_cache=False,
                           system=PROPOSE_SYSTEM.replace("{count}", str(count)),
                           user="SEÑALES DE HOY:\n" + ("\n".join(f"- {s}" for s in signals[:40]) or "(ninguna)")
                                + "\n\nNICHOS YA CONOCIDOS (no repetir):\n" + "\n".join(f"- {k}" for k in known[-200:]))
    out = [_clean(n) for n in result.get("niches", []) if isinstance(n, dict)]
    return [n for n in out if n][:count]


def evaluate(root: Path, topic: str, api: Any = None) -> dict[str, Any]:
    """A topic you type in the studio: its queries and fit from the LLM, then measured like the rest."""

    from .llm import complete_json
    from .ytapi import YouTubeAPI

    topic = " ".join(topic.split())[:120]
    if len(topic) < 3:
        raise ValueError("Escribe un tema")
    ctx = RunContext.create("_radar", root=root)
    niche = _clean(complete_json(ctx, stage="radar", section="planner", max_tokens=600, use_cache=False,
                                 system=EVALUATE_SYSTEM, user=f"TEMA: {topic}") or {}) or \
        {"name": topic, "query_es": topic, "query_en": "", "why": "", "fit": None, "ideas": []}
    api = api or YouTubeAPI(ctx)
    entry = {**niche, "origin": "manual", **measure(api, niche["query_es"], niche["query_en"])}
    return _remember(root, entry, date.today().isoformat())


def scan(root: Path, api: Any, signals: list[str], known: list[str], today: str | None = None) -> list[dict[str, Any]]:
    """The radar's daily turn: `radar.gaps_new` new topics from today's signals, and the best old one measured again."""

    from .ytapi import NoKeysLeft

    base = RunContext.create("_radar", root=root)
    cfg = base.section("radar")
    today = today or date.today().isoformat()
    stored = _read(root)["items"]
    known = known + [i["name"] for i in stored.values()] + [i["query_es"] for i in stored.values()]
    fresh: list[dict[str, Any]] = []
    try:
        proposals = propose(base, signals, known, int(cfg.get("gaps_new", 5)))
    except Exception as error:
        print(f"   huecos: {str(error)[:160]}")
        proposals = []
    again = sorted((i for i in stored.values() if i.get("date", "") < today and i.get("score", 0) >= 6),
                   key=lambda i: i.get("date", ""))[: int(cfg.get("gaps_again", 1))]
    for niche, origin in [*((n, "radar") for n in proposals), *((i, i.get("origin", "radar")) for i in again)]:
        try:
            m = measure(api, niche["query_es"], niche.get("query_en", ""))
        except NoKeysLeft:
            break
        except Exception as error:
            print(f"   hueco «{niche['query_es']}»: {str(error)[:120]}")
            continue
        entry = _remember(root, {**{k: niche.get(k) for k in ("name", "query_es", "query_en", "why", "fit", "ideas")},
                                 "origin": origin, **m}, today)
        entry["new"] = origin != "manual" and entry["firstSeen"] == today
        fresh.append(entry)
        print(f"   hueco «{entry['name']}»: {entry['score']} ({entry['verdict']}) · mediana {entry['demand']} · "
              f"{entry['recent']} vídeos/mes · inglés x{entry['englishGap']}")
    return sorted(fresh, key=lambda e: -e["score"])


def telegram_lines(found: list[dict[str, Any]], top: int = 3) -> list[str]:
    k = lambda n: f"{n / 1e6:.1f} M" if n >= 1e6 else f"{n / 1e3:.0f} mil" if n >= 1e3 else str(n)
    lines = []
    for e in [e for e in found if e.get("new") and e["verdict"] in ("hueco", "hueco en inglés")][:top]:
        lines.append(f"{e['name']} · {e['score']}/10 · mediana {k(e['demand'])} visitas · {e['recent']} vídeos/mes en español"
                     + (f" · inglés x{e['englishGap']}" if e.get("englishGap", 0) >= 2 else "")
                     + (f"\n   → {e['ideas'][0]}" if e.get("ideas") else ""))
    return lines
