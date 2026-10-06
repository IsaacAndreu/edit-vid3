"""«Noticias del día»: the stories of each niche that YouTube is watching right now, to have a video out in 24 h.

Every morning (with the radar) and on demand from the studio, for every channel: its news searches
(`radar.news_queries`, else the first `lab.queries`) plus a few general ones (`radar.news_free`), only videos of the
last `radar.news_hours` (48) hours. Each video gets its speed (views per hour since it went up). Videos about the same
story are grouped by the names they share in their titles («Christa Pike», «Gypsy Rose»): a story covered by several
channels at once and growing fast is the news of the day. The studio shows them with a «Borrador de guion» button that
writes the script with the «caso-real» structure from what those videos say (titles and descriptions); the facts it
cannot confirm come marked [COMPROBAR].

Cost: about 100 quota units per search (YouTube Data API), ~1.5k a day with the defaults; the keys give 10k each.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import RunContext

FILE = "out/_radar/noticias.json"
FREE = ["caso real noticia", "última hora caso", "true crime caso", "polémica hoy"]
_STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "en", "por", "que", "su", "sus", "con", "para", "a",
         "lo", "al", "es", "se", "the", "of", "and", "in", "to", "on", "hoy", "esto", "este", "esta", "asi", "así",
         "como", "cómo", "qué", "que", "quien", "quién", "nadie", "todos", "todo", "nuevo", "nueva", "video", "vídeo",
         "caso", "historia", "verdad", "noticias", "noticia", "última", "ultima", "hora", "en vivo", "live", "official",
         "oficial", "mujer", "hombre", "murió", "muere", "fue", "ser", "sobrevivió"}


def _age_hours(published: str, now: datetime | None = None) -> float:
    try:
        when = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return 1e9
    now = now or datetime.now(timezone.utc)
    return max(0.5, (now - when).total_seconds() / 3600)


def _plain(word: str) -> str:
    return unicodedata.normalize("NFKD", word.casefold()).encode("ascii", "ignore").decode()


def _tokens(title: str) -> list[str]:
    return [_plain(w) for w in re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+", title)]


def keys(title: str) -> list[str]:
    """What a title could be «about»: pairs of neighbouring meaningful words («christa pike», «gypsy rose») and
    single long words («tennessee»). Case-blind: these channels write names in capitals for emphasis."""

    words = _tokens(title)
    out = []
    for a, b in zip(words, words[1:]):
        if a not in _STOP and b not in _STOP and len(a) > 2 and len(b) > 2 and not a.isdigit() and not b.isdigit():
            out.append(f"{a} {b}")
    out += [w for w in words if w not in _STOP and len(w) >= 5 and not w.isdigit()]
    return list(dict.fromkeys(out))


def group(videos: list[dict[str, Any]], keep: int = 6) -> list[dict[str, Any]]:
    """Videos → stories: each video joins the pair of words (else word) it shares with the most other videos."""

    counts = Counter(k for v in videos for k in keys(v["title"]))
    stories: dict[str, dict[str, Any]] = {}
    for video in videos:
        shared = [k for k in keys(video["title"]) if counts[k] >= 2]
        if not shared:
            continue
        key = max(shared, key=lambda k: (counts[k] + (0.5 if " " in k else 0), len(k)))
        story = stories.setdefault(key, {"name": key.title(), "videos": [], "speed": 0.0, "views": 0, "channels": set()})
        story["videos"].append(video)
        story["speed"] += video["perHour"]
        story["views"] += video["views"]
        story["channels"].add(video["channel"])
    out = []
    for story in stories.values():
        story["videos"].sort(key=lambda v: -v["perHour"])
        covered = len(story["channels"])
        out.append({"name": story["name"], "speed": round(story["speed"]), "views": story["views"], "channels": covered,
                    "score": round(story["speed"] * (1 + 0.5 * (covered - 1))),
                    "videos": story["videos"][:6]})
    return sorted(out, key=lambda s: -s["score"])[:keep]


def search(api: Any, query: str, hours: float, min_views: int, now: datetime | None = None) -> list[dict[str, Any]]:
    ids = api.search(query, days=max(1, round(hours / 24 + 0.49)), order="viewCount", language="es", max_results=25)
    out = []
    for v in api.videos(ids):
        age = _age_hours(v["published"], now)
        if age <= hours and v["views"] >= min_views and v["duration"] >= 120 and v.get("live", "none") == "none":
            out.append({**{k: v.get(k) for k in ("id", "title", "channel", "views", "thumbnail", "url", "published",
                                                  "duration", "description")},
                        "ageHours": round(age, 1), "perHour": round(v["views"] / age)})
    return out


def scan(root: Path, api: Any = None, now: datetime | None = None) -> dict[str, Any]:
    from .radar import channels
    from .ytapi import NoKeysLeft, YouTubeAPI

    base = RunContext.create("_radar", root=root)
    cfg = base.section("radar")
    api = api or YouTubeAPI(base)
    hours = float(cfg.get("news_hours", 48))
    min_views = int(cfg.get("news_min_views", 3000))
    report: dict[str, Any] = {"at": (now or datetime.now()).isoformat(timespec="minutes"), "channels": {}, "errors": []}
    asks = []
    for name in channels(root):
        ctx = RunContext.create("_radar", root=root, channel=name)
        queries = [str(q) for q in (ctx.section("radar").get("news_queries") or ctx.section("lab").get("queries") or [])]
        asks.append((name, queries[: int(cfg.get("news_per_channel", 2))]))
    asks.append(("general", [str(q) for q in cfg.get("news_free", FREE)]))
    for name, queries in asks:
        videos: dict[str, dict[str, Any]] = {}
        for query in queries:
            try:
                for v in search(api, query, hours, min_views, now):
                    videos.setdefault(v["id"], v)
            except NoKeysLeft:
                report["errors"].append("Sin cuota de la API de YouTube por hoy")
                report["channels"][name] = group(list(videos.values()))
                return _save(root, report)
            except Exception as error:
                report["errors"].append(f"{name} «{query}»: {str(error)[:120]}")
        report["channels"][name] = group(list(videos.values()))
        print(f"   Noticias · {name}: {len(videos)} vídeos de las últimas {hours:g} h → "
              + ", ".join(s["name"] for s in report["channels"][name][:3]))
    return _save(root, report)


def _save(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    import json

    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def latest(root: Path) -> dict[str, Any] | None:
    import json

    try:
        return json.loads((root / FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return None


def idea_for(story: dict[str, Any]) -> dict[str, Any]:
    """A story → an idea for the script draft (caso-real), with what the videos about it say."""

    lines = []
    for v in story["videos"][:4]:
        lines.append(f"- «{v['title']}» ({v['channel']}, hace {v['ageHours']:.0f} h): {' '.join(str(v.get('description') or '').split())[:400]}")
    return {"title": story["name"], "format": "caso-real",
            "note": "NOTICIA DE LAS ÚLTIMAS HORAS. Lo que cuentan los vídeos que ya hay (úsalo como fuente; lo que no "
                    "esté aquí, márcalo [COMPROBAR]):\n" + "\n".join(lines)}


def telegram_lines(report: dict[str, Any], per: int = 2) -> list[str]:
    lines = []
    for name, stories in report.get("channels", {}).items():
        hot = [s for s in stories if s["channels"] >= 2][:per] or stories[:1]
        for s in hot:
            lines.append(f"  {name}: {s['name']} · {s['speed']:,}/h · {s['channels']} canales".replace(",", "."))
    return lines
