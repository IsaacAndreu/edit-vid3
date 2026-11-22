"""What to dub of what is already made (prompt «qué canales empezar, cuáles doblar», part 2).

For every own channel (a profile in canales/ with finished videos, not itself a dub target) and every language of
`radar.idiomas` it is not dubbed into yet: the gap of its niche in that language (pipeline/idiomas.py, with the
channel's own search, `lab.queries`, translated), plus what is known at home —

- how many finished videos could be dubbed today (no `-<lang>` version, no voice on its way);
- what that would cost: the voice (characters of each script × `tts.usd_per_1k_chars`) and the API of a dub;
- how much the material depends on the language: a channel drawn in code (maps, simulations) dubs whole; one built
  on statements in Spanish (quotes with their own voice) dubs worse;
- how the channel does (Mi canal: median views of its long videos).

The result is one ordered list «dub THIS channel into THIS language». The channels already dubbed check the score:
a language the score recommends where the dubbed channel does badly is flagged as a badly made score.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

FILE = "out/_radar/doblar.json"
DRAWN_STYLES = {"atlas", "mapas", "simulacion", "stickman", "cine", "monigotes"}
API_USD_PER_DUB = 0.03          # matching sentences + translating on-screen texts: a few cheap calls
REUSE_DAYS = 14


def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def own_channels(root: Path) -> dict[str, list[str]]:
    """{channel: [finished videos]} — dubbed versions (<slug>-<lang>) left out."""

    from .dub import LANGUAGES
    from .web import video_channel

    out: dict[str, list[str]] = {}
    for final in sorted((root / "out").glob("*/video-final.mp4")) if (root / "out").is_dir() else []:
        slug = final.parent.name
        base, _, lang = slug.rpartition("-")
        if lang in LANGUAGES and base and (root / "out" / base / "video-final.mp4").is_file():
            continue
        channel = video_channel(root, slug)
        if channel:
            out.setdefault(channel, []).append(slug)
    return out


def dependency(config: dict[str, Any]) -> tuple[str, str]:
    """How much the channel's material depends on its language: «ninguna», «baja» or «alta», and why."""

    style = str((config.get("visual") or {}).get("style") or "").lower()
    if style in DRAWN_STYLES or (config.get("simulacion") or {}).get("enabled") or (config.get("stickman") or {}).get("enabled"):
        return "ninguna", "todo se dibuja en código: se dobla entero"
    if int((config.get("quotes") or {}).get("count", 0) or 0) > 0:
        return "alta", "lleva declaraciones con su voz original (quotes.count): se quedan en su idioma con subtítulos"
    return "baja", "metraje de archivo bajo la voz: cambia la voz y los textos en pantalla"


def done_languages(root: Path, config: dict[str, Any], slugs: list[str]) -> set[str]:
    langs = set((config.get("dubbing") or {}).get("channels") or {})
    for slug in slugs:
        for other in (root / "out").glob(f"{slug}-*/video-final.mp4"):
            langs.add(other.parent.name.rsplit("-", 1)[1])
    return langs


def ready(root: Path, slugs: list[str], lang: str) -> list[str]:
    """Finished videos with no dub in `lang` yet and no voice on its way."""

    from .context import find_video

    out = []
    for slug in slugs:
        if (root / "out" / f"{slug}-{lang}" / "video-final.mp4").is_file():
            continue
        try:
            folder = find_video(root, slug)
        except Exception:
            continue
        if not any(folder.glob(f"voz-{lang}*.mp3")):
            out.append(slug)
    return out


def cost(root: Path, ctx: Any, slugs: list[str]) -> float:
    """Voice + API of dubbing these videos (the render is local)."""

    from .context import find_video
    from .tts import usd_per_1k_chars

    rate = usd_per_1k_chars(ctx)
    total = 0.0
    for slug in slugs:
        try:
            chars = len((find_video(root, slug) / "guion.txt").read_text("utf-8"))
        except Exception:
            chars = 9000                                          # a 10-minute script
        total += rate * chars / 1000 + API_USD_PER_DUB
    return round(total, 2)


def median_views(root: Path, channel: str | None) -> float | None:
    from .mychannel import saved

    if not channel:
        return None
    report = saved(root, channel) or {}
    return (report.get("numbers") or {}).get("medianLong")


def rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The dubbing score: the gap in that language (0-10), less when the material depends on the language, more
    when there are videos ready to dub today. Ordered best first."""

    for row in rows:
        value = float(row.get("gapScore") or 0)
        value -= {"alta": 2.0, "baja": 0.0, "ninguna": -0.5}.get(row.get("dependency"), 0.0)
        value += min(2.0, len(row.get("ready") or []) / 10)
        row["score"] = round(max(0.0, min(10.0, value)), 1)
    return sorted(rows, key=lambda r: (-r["score"], r["channel"], r["lang"]))


def check(row: dict[str, Any], own_median: float | None, dubbed_median: float | None) -> str | None:
    """A channel already dubbed into this language tells whether the score is right: a recommended language where the
    dubbed channel gets under a third of the original's views is a badly made score."""

    if not own_median or dubbed_median is None:
        return None
    ratio = dubbed_median / own_median
    row["dubbedRatio"] = round(ratio, 2)
    if row.get("score", 0) >= 6 and ratio < 0.33:
        return f"nota mal hecha: se recomienda, pero el canal ya doblado saca {ratio:.0%} de las visitas del original"
    if row.get("score", 0) < 4 and ratio >= 1:
        return f"nota mal hecha: no se recomienda, pero el canal ya doblado saca {ratio:.0%} de las visitas del original"
    return None


def compute(root: Path, api: Any = None, translate_fn: Callable[[str, list[str]], dict[str, Any]] | None = None,
            today: str | None = None) -> dict[str, Any]:
    """The list «dub this channel into this language», measured where today's quota allows (a channel measured in
    the last REUSE_DAYS days keeps its numbers), saved in out/_radar/doblar.json."""

    from . import idiomas
    from .context import RunContext
    from .ytapi import YouTubeAPI

    today = today or date.today().isoformat()
    base = RunContext.create("_radar", root=root)
    cfg = base.section("radar")
    languages = idiomas.configured(cfg)
    previous = _read(root).get("measures") or {}
    measures: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    waiting: list[str] = []
    budget = None
    for channel, slugs in sorted(own_channels(root).items()):
        ctx = RunContext.create("_doblar", root=root, channel=channel)
        config = ctx.config
        if (config.get("dubbing") or {}).get("enabled") is False:
            continue                                   # a dub target itself (gimnasia-br)
        own = str((config.get("align") or {}).get("language") or "es")[:2]
        queries = [str(q) for q in ((config.get("lab") or {}).get("queries") or []) if str(q).strip()]
        done = done_languages(root, config, slugs)
        wanted = [l for l in languages if l != own and l not in done]
        if not wanted:
            continue
        level, why = dependency(config)
        old = previous.get(channel) or {}
        if old.get("date", "") and (date.fromisoformat(today) - date.fromisoformat(old["date"])).days < REUSE_DAYS:
            table = old
        elif not queries:
            table = {"languages": {}, "readings": {"rows": []}, "skipped": {l: "el canal no tiene lab.queries" for l in wanted}}
        else:
            if budget is None:
                api = api or YouTubeAPI(base)
                budget = idiomas.Budget(root, api, cfg, today)
            translate = translate_fn or (lambda q, langs: idiomas.translate(base, q, langs))
            checked = [l for l in languages if l in done and l != own]   # measured last: the check of the score
            table = idiomas.table(api, budget, queries[0], [own] + wanted + checked,
                                  {**cfg, "idiomas_min_demand": int(cfg.get("doblar_min_demand", 5000))}, translate,
                                  origin=own)
            table["date"] = today
        measures[channel] = table
        scores = {r["lang"]: r for r in (table.get("readings") or {}).get("rows") or []}
        home = median_views(root, channel)
        for lang in wanted:
            r = scores.get(lang)
            if r is None:
                waiting.append(f"{channel} → {lang}: {(table.get('skipped') or {}).get(lang, 'sin medir')}")
                continue
            rows.append({"channel": channel, "lang": lang, "gapScore": r["score"], "verdict": r["verdict"],
                         "gap": r["gap"], "demand": r["demand"], "recent": r["recent"], "dependency": level,
                         "dependencyWhy": why, "ready": ready(root, slugs, lang), "homeMedian": home})
        for lang in sorted(done & set(scores)):       # already dubbed: the check of the score
            target = ((config.get("dubbing") or {}).get("channels") or {}).get(lang)
            r = scores[lang]
            row = {"channel": channel, "lang": lang, "gapScore": r["score"], "dependency": level, "ready": []}
            rank([row])
            row["check"] = check(row, home, median_views(root, target)) or "la nota cuadra con cómo va"
            row["dubbedChannel"] = target
            rows.append({**row, "already": True})
    fresh = rank([r for r in rows if not r.get("already")])
    for row in fresh:
        row["cost"] = cost(root, base, row["ready"])
        row["readyCount"] = len(row["ready"])
    result = {"date": today, "rows": fresh, "checks": [r for r in rows if r.get("already")], "waiting": waiting,
              "measures": measures}
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def saved(root: Path) -> dict[str, Any]:
    return _read(root)
