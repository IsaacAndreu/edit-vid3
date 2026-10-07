"""«Canales revelación»: small channels with far more views than subscribers — niches and formats to exploit.

Every day (with the radar): broad searches of the last `radar.rising_days` (60) days — the channels' own niche
searches plus a rotating set of documentary formats — collect the channels behind the most viewed videos. The ones
with at most `radar.rising_max_subs` (50,000) subscribers whose best recent video has many times their subscribers
in views (`radar.rising_min_multiple`, 5x) are the signal: YouTube is pushing that format to people who do not
follow the channel yet, so a new channel can get in. For the best `radar.rising_keep` (8) the latest videos are read
(titles, views, length) and the LLM says what the format is, whether this tool can make it (faceless documentary:
voice, archive clips, graphics; 0-10) and how to exploit it. Seen channels are remembered (out/_radar/canales.json)
so the daily digest shows what is new.
"""

from __future__ import annotations

import json
import statistics
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .context import RunContext

FILE = "out/_radar/canales.json"
FORMATS = ["la historia de", "el caso de", "documental", "qué pasó con", "la verdad sobre", "el misterio de",
           "top 10", "por qué", "la caída de", "cómo funciona", "el hombre que", "la mujer que", "el día que",
           "curiosidades", "explicado", "nadie sabe"]

FIT_SYSTEM = """
Eres analista de YouTube para un creador con una herramienta que hace documentales SIN CARA en español: guion leído por
una voz sintética, clips de archivo de YouTube y fotos, gráficos animados (mapas, cifras, rankings, cronologías), 8-15 min.
Te paso canales pequeños que están creciendo rápido, con sus últimos vídeos. Para CADA canal devuelve SOLO JSON:
{"channels": [{"id": "id del canal", "format": "el formato en 1 frase concreta (tema + forma de contarlo)",
  "niche": "el nicho en 2-4 palabras", "query": "búsqueda de YouTube de 2-5 palabras para ese nicho",
  "fit": 0-10 (10 = la herramienta lo puede hacer igual o mejor; 0 = necesita cara, cámara propia, gameplay, animación
  hecha a mano o algo que la herramienta no hace), "why": "por qué crece (1 frase)",
  "how": "cómo lo harías tú con la herramienta: canal, formato y primer vídeo (1-2 frases)"}]}
""".strip()


def _age_days(iso: str) -> float:
    try:
        return max(1.0, (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 86400)
    except (ValueError, AttributeError):
        return 9999.0


def _read(root: Path) -> dict[str, Any]:
    try:
        return json.loads((root / FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def known(root: Path) -> dict[str, Any]:
    return _read(root)


def candidates(api: Any, queries: list[str], days: int, max_subs: int, min_multiple: float) -> list[dict[str, Any]]:
    """Channels behind the most viewed recent videos of `queries`, small and punching far above their size."""

    best: dict[str, dict[str, Any]] = {}
    for query in queries:
        ids = api.search(query, days=days, order="viewCount", language="es", max_results=50)
        for v in api.videos(ids):
            if v["duration"] < 240 or not v.get("channelId"):
                continue
            seen = best.get(v["channelId"])
            if seen is None or v["views"] > seen["views"]:
                best[v["channelId"]] = {**{k: v.get(k) for k in ("id", "title", "views", "thumbnail", "url", "published",
                                                                  "duration")}, "query": query}
    if not best:
        return []
    out = []
    for c in api.channels(list(best)):
        subs = c.get("subscribers")
        if subs is None or subs > max_subs:
            continue
        hit = best[c["id"]]
        multiple = hit["views"] / max(subs, 100)
        if multiple < min_multiple:
            continue
        age = _age_days(c.get("created") or "")
        out.append({"id": c["id"], "title": c["title"], "handle": c.get("handle") or "", "subscribers": subs,
                    "views": c.get("viewCount", 0), "videos": c.get("videoCount", 0), "created": c.get("created", ""),
                    "ageDays": round(age), "thumbnail": c.get("thumbnail", ""), "uploads": c.get("uploads", ""),
                    "url": f"https://www.youtube.com/{c['handle']}" if c.get("handle") else f"https://www.youtube.com/channel/{c['id']}",
                    "best": hit, "multiple": round(multiple, 1),
                    "score": round(min(10.0, 2 * (multiple ** 0.5) / 2 + (3 if age < 365 else 1 if age < 730 else 0)), 1)})
    return sorted(out, key=lambda c: -c["score"])


def describe(ctx: RunContext, api: Any, chosen: list[dict[str, Any]]) -> None:
    """Latest videos of each channel, then the LLM's read of its format and fit (in place)."""

    from .llm import complete_json

    blocks = []
    for c in chosen:
        latest = api.uploads(c["uploads"], 12) if c.get("uploads") else []
        long = [v for v in latest if v["duration"] >= 240]
        c["medianViews"] = int(statistics.median([v["views"] for v in long])) if long else 0
        c["shortsShare"] = round(1 - len(long) / len(latest), 2) if latest else 0
        c["latest"] = [{k: v.get(k) for k in ("title", "views", "duration", "thumbnail", "url")} for v in latest[:8]]
        blocks.append(f"[{c['id']}] {c['title']} · {c['subscribers']} subs · creado hace {c['ageDays']} días · "
                      f"mejor vídeo {c['best']['views']} visitas («{c['best']['title']}»)\n"
                      + "\n".join(f"   - {v['title']} · {v['views']} visitas · {v['duration'] // 60} min" for v in latest[:10]))
    if not blocks:
        return
    try:
        result = complete_json(ctx, stage="radar", section="planner", system=FIT_SYSTEM, user="\n\n".join(blocks),
                               max_tokens=2500, use_cache=False)
    except Exception as error:
        print(f"   canales revelación: {str(error)[:160]}")
        return
    by_id = {str(x.get("id")): x for x in result.get("channels", []) if isinstance(x, dict)}
    for c in chosen:
        info = by_id.get(c["id"]) or {}
        c.update({k: info.get(k) for k in ("format", "niche", "query", "why", "how")})
        try:
            c["fit"] = max(0, min(10, int(info.get("fit"))))
        except (TypeError, ValueError):
            c["fit"] = None


def scan(root: Path, api: Any, today: date | None = None) -> list[dict[str, Any]]:
    from .radar import channels as profiles

    base = RunContext.create("_radar", root=root)
    cfg = base.section("radar")
    today = today or date.today()
    per_day = int(cfg.get("rising_queries", 4))
    formats = [str(q) for q in cfg.get("rising_formats", FORMATS)]
    start = (today.toordinal() * per_day) % max(1, len(formats))
    queries = [formats[(start + i) % len(formats)] for i in range(min(per_day, len(formats)))]
    for name in profiles(root):                                  # one search of each of your niches too
        mine = RunContext.create("_radar", root=root, channel=name).section("lab").get("queries") or []
        if mine:
            queries.append(str(mine[today.toordinal() % len(mine)]))
    found = candidates(api, list(dict.fromkeys(queries)), int(cfg.get("rising_days", 60)),
                       int(cfg.get("rising_max_subs", 50_000)), float(cfg.get("rising_min_multiple", 5)))
    seen = _read(root)
    fresh = [c for c in found if c["id"] not in seen][: int(cfg.get("rising_keep", 8))]
    again = [c for c in found if c["id"] in seen][:4]
    describe(base, api, fresh)
    for c in again:                                              # known ones: keep their read, update the numbers
        c.update({k: seen[c["id"]].get(k) for k in ("format", "niche", "query", "why", "how", "fit", "latest",
                                                      "medianViews", "shortsShare") if seen[c["id"]].get(k) is not None})
    stamp = today.isoformat()
    for c in fresh:
        c["new"], c["firstSeen"] = True, stamp
    for c in again:
        c["new"], c["firstSeen"] = False, seen[c["id"]].get("firstSeen", stamp)
    for c in [*fresh, *again]:
        seen[c["id"]] = {**c, "lastSeen": stamp}
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(seen.items(), key=lambda kv: kv[1].get("lastSeen", ""))[-400:]),
                               ensure_ascii=False, indent=1), encoding="utf-8")
    ranked = sorted([*fresh, *again], key=lambda c: (-(c.get("fit") or 0), -c["score"]))
    print(f"   Canales revelación: {len(fresh)} nuevos, {len(again)} ya vistos")
    return ranked


def telegram_lines(rising: list[dict[str, Any]], top: int = 5) -> list[str]:
    lines = []
    for c in [c for c in rising if (c.get("fit") or 0) >= 5][:top] or rising[:3]:
        k = lambda n: f"{n / 1e6:.1f} M" if n >= 1e6 else f"{n / 1e3:.0f} mil" if n >= 1e3 else str(n)
        lines.append(f"{'🆕 ' if c.get('new') else ''}{c['title']} · {k(c['subscribers'])} subs · vídeo de {k(c['best']['views'])} "
                     f"({c['multiple']}× sus subs) · {c['ageDays']} días"
                     + (f"\n   {c['format']}" if c.get("format") else "")
                     + (f" · encaje {c['fit']}/10" if c.get("fit") is not None else "")
                     + (f"\n   → {c['how']}" if c.get("how") else "")
                     + f"\n   {c['url']}")
    return lines
