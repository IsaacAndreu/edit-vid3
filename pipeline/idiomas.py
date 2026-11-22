"""Gaps in any language (prompt «qué canales empezar, cuáles doblar», part 1).

`huecos.measure` compares Spanish with English, written by hand. This measures one topic in a list of languages
(`radar.idiomas`, es en pt de fr it by default): the search translated by the model, every result checked to really
be in that language (`relevanceLanguage` is a preference, not a filter: the uploader's default language and audio
language from `videos.list`, else the title's words), and per language the same numbers as Huecos — demand,
recent competition, weight of the big channels, small channels winning, autocomplete suggestions.

Two readings come out of the table:
- where there is an audience nobody serves (to START a channel in that language);
- which language has the biggest gap against the one where the topic already works (to DUB into it).

Quota rules: the origin language and Spanish first; the rest only for topics whose origin demand passes
`radar.idiomas_min_demand`; never more than `radar.gaps_units_per_day` for all of this, and always
`radar.keep_for_queue` units left for the videos in the queue. What does not fit waits for tomorrow and says so.
The autocomplete count and the views of recent videos are SIGNS of searches, not search volume (YouTube publishes
none): the page calls them that.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import date
from pathlib import Path
from typing import Any, Callable

LANGUAGES = ("es", "en", "pt", "de", "fr", "it")
NAMES = {"es": "español", "en": "inglés", "pt": "portugués", "de": "alemán", "fr": "francés", "it": "italiano"}
BUDGET_FILE = "out/_radar/cuota_idiomas.json"
SEARCH_UNITS = 100
UNITS_PER_LANGUAGE = 2 * SEARCH_UNITS + 5           # top of the year + last 30 days, plus videos/channels lookups
UNITS_FIRST = UNITS_PER_LANGUAGE + SEARCH_UNITS     # the origin also reads the all-time top (is it stale?)

# frequent short words: a title with two of them and none of another language's is in that language
WORDS = {
    "es": set("el la los las de del que y en por para con una un es su sus como más pero lo qué por qué cómo".split()),
    "en": set("the of and to in is for on with how why what this that you your from are was".split()),
    "pt": set("o a os as do da dos das que e em por para com um uma é seu sua como mais não você".split()),
    "de": set("der die das und ist nicht ein eine zu mit von für auf wie warum was ich du den dem des".split()),
    "fr": set("le la les de des du et en un une est pour pas que qui sur dans avec comment pourquoi ce".split()),
    "it": set("il lo la gli le di del della e che un una è per non con come perché più questo sono".split()),
}

TRANSLATE_SYSTEM = """
Te paso una búsqueda de YouTube sobre un tema. Escríbela como la escribiría alguien que busca ese tema en cada idioma
(no una traducción palabra por palabra: los términos que de verdad se usan allí), 2-6 palabras. Di también en qué
idioma crees que el tema YA funciona mejor (donde más se hace y se ve). Devuelve SOLO JSON:
{"origin": "en", "queries": {"es": "...", "en": "...", "pt": "...", "de": "...", "fr": "...", "it": "..."}}
""".strip()


def configured(cfg: dict[str, Any]) -> list[str]:
    wanted = [str(l).lower()[:2] for l in (cfg.get("idiomas") or LANGUAGES)]
    return [l for l in dict.fromkeys(wanted) if l in WORDS]


def in_language(video: dict[str, Any], lang: str) -> bool | None:
    """Is this result in `lang`? The uploader's audio language, else default language, else the title's words.
    None when nothing says (the result is then not counted for any language)."""

    for field in ("audioLanguage", "language"):
        value = str(video.get(field) or "").lower()
        if value and value not in ("zxx", "und"):
            return value.split("-")[0] == lang
    words = re.findall(r"[^\W\d_]+", str(video.get("title") or "").casefold())
    if not words:
        return None
    hits = {code: sum(w in vocab for w in words) for code, vocab in WORDS.items()}
    best = max(hits.values())
    if best < 1:
        return None
    winners = [code for code, n in hits.items() if n == best]
    return lang in winners if len(winners) == 1 else (None if lang in winners else False)


# --- the quota ---------------------------------------------------------------------------------------------------

class Budget:
    """`radar.gaps_units_per_day` for the gaps per language, counted apart in out/_radar/cuota_idiomas.json, and
    never below `radar.keep_for_queue` units of the day's API quota (the searches of the videos in the queue)."""

    def __init__(self, root: Path, api: Any, cfg: dict[str, Any], today: str | None = None) -> None:
        self.root, self.api = root, api
        self.cap = int(cfg.get("gaps_units_per_day", 3000))
        self.reserve = int(cfg.get("keep_for_queue", 3000))
        self.today = today or date.today().isoformat()
        try:
            data = json.loads((root / BUDGET_FILE).read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        self.spent = int(data.get("spent", 0)) if data.get("day") == self.today else 0

    def left(self) -> int:
        api_left = None
        try:
            api_left = int(self.api.quota()["left"]) - self.reserve
        except Exception:
            api_left = None
        mine = self.cap - self.spent
        return max(0, mine if api_left is None else min(mine, api_left))

    def allows(self, units: int) -> bool:
        return units <= self.left()

    def spend(self, units: int) -> None:
        self.spent += units
        path = self.root / BUDGET_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"day": self.today, "spent": self.spent}), encoding="utf-8")

    def topics_today(self, languages: int) -> int:
        """How many topics still fit today, measured in `languages` languages each."""

        per_topic = UNITS_FIRST + UNITS_PER_LANGUAGE * max(0, languages - 1)
        return self.left() // per_topic


# --- measuring ----------------------------------------------------------------------------------------------------

def measure_language(api: Any, query: str, lang: str, first: bool = False) -> dict[str, Any]:
    """The numbers of one topic in one language, counting only the results really in that language."""

    from .huecos import _age_days, relevant, suggestions

    def keep(videos: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
        long = [v for v in videos if v.get("duration", 0) >= 240 and v.get("live", "none") == "none"]
        said = [(v, in_language(v, lang)) for v in long]
        known = [v for v, ok in said if ok is not None]
        return [v for v, ok in said if ok], len(known), len(long)

    top, known_top, long_top = keep(api.videos(api.search(query, days=365, order="viewCount", language=lang,
                                                          max_results=50)))
    top = top[:20]
    recent, _, _ = keep(api.videos(api.search(query, days=30, order="date", language=lang, max_results=50)))
    recent = [v for v in recent if relevant(v, query)]
    stale = 0.0
    if first:
        alltime, _, _ = keep(api.videos(api.search(query, order="viewCount", language=lang, max_results=10)))
        stale = statistics.median([_age_days(v["published"]) / 365 for v in alltime]) if alltime else 0.0
    ids = sorted({v["channelId"] for v in top if v.get("channelId")})
    subs = {c["id"]: c.get("subscribers") for c in (api.channels(ids) if ids else [])}
    views = [v["views"] for v in top]
    total = sum(views) or 1
    small = [v for v in top if subs.get(v["channelId"]) is not None and subs[v["channelId"]] < 50_000
             and v["views"] >= max(10_000, 2 * subs[v["channelId"]])]
    keep_fields = ("id", "title", "channel", "views", "url", "published")
    return {
        "lang": lang, "query": query,
        "demand": int(statistics.median(views)) if views else 0,
        "perDay": int(statistics.median([v["views"] / _age_days(v["published"]) for v in top])) if top else 0,
        "recent": len(recent), "recentChannels": len({v["channelId"] for v in recent}),
        "bigShare": round(sum(v["views"] for v in top if (subs.get(v["channelId"]) or 0) >= 500_000) / total, 2),
        "smallWins": len(small), "staleYears": round(stale, 1),
        "inLanguage": round(len(top) / max(1, known_top), 2) if known_top else None,   # results really in it
        "checked": known_top, "results": long_top,
        "suggestions": suggestions(query, lang),       # a SIGN people type it, not a search volume
        "examples": [{**{k: v.get(k) for k in keep_fields}, "subscribers": subs.get(v["channelId"])}
                     for v in sorted(small or top, key=lambda v: -v["views"])[:3]],
    }


def translate(ctx: Any, query: str, languages: list[str]) -> dict[str, Any]:
    from .llm import complete_json

    answer = complete_json(ctx, stage="radar", section="planner", max_tokens=500, system=TRANSLATE_SYSTEM,
                           user=f"BÚSQUEDA: {query}\nIDIOMAS: {', '.join(languages)}")
    queries = {str(k)[:2]: " ".join(str(v).split())[:80] for k, v in (answer.get("queries") or {}).items()
               if str(k)[:2] in languages and str(v).strip()}
    origin = str(answer.get("origin") or "").lower()[:2]
    return {"origin": origin if origin in languages else "", "queries": queries}


def table(api: Any, budget: Budget, query: str, languages: list[str], cfg: dict[str, Any],
          translate_fn: Callable[[str, list[str]], dict[str, Any]], origin: str = "") -> dict[str, Any]:
    """The topic in every language that fits: {"origin", "queries", "languages": {lang: numbers}, "skipped":
    {lang: why}, "readings": …}."""

    told = translate_fn(query, languages)
    queries = {**told.get("queries", {})}
    origin = origin or told.get("origin") or "en"
    queries.setdefault(origin, query)
    order = [origin] + (["es"] if origin != "es" and "es" in languages else [])
    order += [l for l in languages if l not in order]
    minimum = int(cfg.get("idiomas_min_demand", 20_000))
    measured: dict[str, dict[str, Any]] = {}
    skipped: dict[str, str] = {}
    for lang in order:
        if lang not in queries:
            skipped[lang] = "sin búsqueda traducida"
            continue
        if lang not in order[:2] and measured.get(origin, {}).get("demand", 0) < minimum:
            skipped[lang] = f"el tema no pasa el mínimo en {NAMES.get(origin, origin)} ({minimum} visitas de mediana)"
            continue
        units = UNITS_FIRST if lang == origin else UNITS_PER_LANGUAGE
        if not budget.allows(units):
            skipped[lang] = "no cabe en la cuota de hoy: mañana"
            continue
        measured[lang] = measure_language(api, queries[lang], lang, first=lang == origin)
        budget.spend(units)
    return {"origin": origin, "queries": queries, "languages": measured, "skipped": skipped,
            "readings": readings(measured, origin)}


def readings(measured: dict[str, dict[str, Any]], origin: str) -> dict[str, Any]:
    """Per language a 0-10 score and a verdict (Huecos' formula, with the gap taken against the origin language),
    then the two readings: where to START (an audience nobody serves) and where to DUB (biggest gap against the
    origin, where the topic already works)."""

    from .huecos import score

    base = measured.get(origin, {}).get("demand", 0)
    rows = []
    for lang, m in measured.items():
        gap = round(base / max(m["demand"], 1), 1) if lang != origin and base else 0.0
        value, verdict = score({**m, "englishGap": gap})
        if verdict == "hueco en inglés":
            verdict = f"hueco frente al {NAMES.get(origin, origin)}"
        rows.append({"lang": lang, "score": value, "verdict": verdict, "gap": gap, "demand": m["demand"],
                     "recent": m["recent"], "smallWins": m["smallWins"], "inLanguage": m.get("inLanguage")})
    rows.sort(key=lambda r: -r["score"])
    start = [r for r in rows if r["verdict"] in ("hueco",) or r["verdict"].startswith("hueco frente")]
    works = base >= 20_000 and measured.get(origin, {}).get("verdict") != "sin demanda"
    dub = sorted((r for r in rows if r["lang"] != origin and r["gap"] >= 2 and r["recent"] <= 20), key=lambda r: -r["gap"])
    return {"rows": rows, "start": start, "dub": dub[:3] if works else [],
            "dubNote": None if works else "el tema aún no funciona bien en su idioma de origen: no hay de dónde doblar"}


def save(root: Path, topic_key: str, result: dict[str, Any]) -> dict[str, Any]:
    """Next to the topic in Huecos (out/_radar/huecos.json → item["idiomas"]), dated."""

    from .huecos import _read, _write

    data = _read(root)
    item = data["items"].setdefault(topic_key, {"name": topic_key, "query_es": topic_key})
    item["idiomas"] = {**result, "date": date.today().isoformat()}
    _write(root, data)
    return item
