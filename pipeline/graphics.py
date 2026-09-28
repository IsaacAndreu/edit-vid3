"""Animated graphics chosen from the script: maps, A vs B, charts, year timelines, spec sheets,
ranking cards and kinetic text (Remotion components in remotion/components/graphics/).

The LLM reads the narration in numbered sentences and proposes where a graphic explains the story
better than footage — "de Manila se fue a Tokio" (map with a route), "Yulo frente a Uchimura" with
their figures (A vs B), three dated milestones in a row (timeline), a list of figures of the same
measure (chart), the specs of a robot (spec sheet). Everything shown must come from the script:
every number is checked against the narration around it (as the planner does for on-screen
labels), place names are geocoded with OpenStreetMap (Nominatim, cached in cache/geo.json) and
countries matched against the map data. A graphic covers the shots of the sentences it spans.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from .context import RunContext
from .llm import complete_json
from .planner import _numbers, _spelled_numbers

STAGE = "timeline"
GEO_CACHE = "geo.json"
TYPES = ("map", "compare", "chart", "timeline", "specs", "rank", "kinetic")

SYSTEM = """
Eres el grafista de un canal de documentales de YouTube. Te paso la narración en frases numeradas
con sus tiempos. Propón como máximo {count} gráficos animados donde expliquen MEJOR que un plano de
vídeo, repartidos por el vídeo (nunca en los primeros 20 s, separados al menos 25 s). Tipos:
- "map": la historia cambia de lugar o nombra ciudades/países relevantes. data: {{"title": "…",
  "countries": ["nombres de países EN INGLÉS como en Natural Earth, p. ej. 'United States of America'"],
  "points": [{{"name": "nombre de la ciudad en el idioma del guion", "query": "ciudad, país en inglés para geolocalizarla",
  "note": "dato corto dicho en el guion o null"}}], "route": true si es un viaje/carrera de un lugar a otro,
  "zoom": índice del punto al que acercarse o null, "globe": true para presentar un país lejano}}
- "compare": DOS personas, equipos, países o productos distintos (nunca dos pruebas o momentos de la misma
  persona) con al menos 2 cifras de cada uno DICHAS en el guion. data: {{"title": "…",
  "left": {{"name": "…"}}, "right": {{"name": "…"}}, "rows": [{{"label": "…", "a": número, "b": número,
  "unit": "…" o null, "better": "high"|"low"}}]}}
- "chart": al menos 3 valores de una misma medida dichos en el guion. data: {{"chart": "bar"|"line"|"pie",
  "title": "…", "unit": "…" o null, "data": [{{"label": "…", "value": número}}]}}
- "timeline": al menos 3 hitos con año dichos seguidos. data: {{"title": "…", "events": [{{"year": "2019", "text": "máx. 5 palabras"}}]}}
- "specs": ficha técnica de un producto/robot/persona con al menos 3 datos dichos. data: {{"name": "…",
  "subtitle": "…" o null, "specs": [{{"label": "…", "value": "número como se dice", "unit": "…" o null}}]}}
- "rank": solo en vídeos de ranking/cuenta atrás, al presentar cada puesto. data: {{"rank": 3, "total": 10 o null,
  "name": "…", "subtitle": "…" o null, "stats": [{{"label": "…", "value": "…"}}]}}
- "kinetic": una frase MUY corta y potente (máx. 8 palabras, literal del guion), como máximo 2. data: {{"lines": ["…", "…"]}}
Reglas: TODOS los datos (cifras, años, nombres) deben estar en esas frases del guion; nada inventado.
Textos en el idioma del guion, cortos. Devuelve SOLO JSON:
{{"graphics": [{{"type": "map", "from": 12, "to": 13, "data": {{...}}}}]}}
""".strip()


# --- geography ----------------------------------------------------------------------------------

def country_names(root: Path) -> set[str]:
    path = root / "node_modules" / "world-atlas" / "countries-50m.json"
    if not path.is_file():
        return set()
    data = json.loads(path.read_text("utf-8"))
    return {g["properties"]["name"] for g in data["objects"]["countries"]["geometries"] if g.get("properties")}


def geocode(ctx: RunContext, query: str) -> tuple[float, float] | None:
    """(lon, lat) of a place from OpenStreetMap's Nominatim, cached; None if not found."""

    path = ctx.cache_dir / GEO_CACHE
    cache: dict[str, Any] = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    key = query.strip().lower()
    if key in cache:
        return tuple(cache[key]) if cache[key] else None
    try:
        time.sleep(1.1)                                   # Nominatim's usage policy: 1 request per second
        found = requests.get("https://nominatim.openstreetmap.org/search", timeout=30,
                             params={"q": query, "format": "json", "limit": 1},
                             headers={"User-Agent": "edit-vid3/1.0 (documentary maps)"}).json()
    except (requests.RequestException, ValueError):
        return None                                       # not cached: retried next time
    value = [round(float(found[0]["lon"]), 4), round(float(found[0]["lat"]), 4)] if found else None
    cache[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return tuple(value) if value else None


# --- checks -------------------------------------------------------------------------------------

def said(value: Any, text: str) -> bool:
    """Every number in `value` is said in `text` (digits or words)."""

    numbers = _numbers(str(value))
    return numbers <= (_numbers(text) | _spelled_numbers(text))


def _num(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def clean(kind: str, data: dict[str, Any], text: str, ctx: RunContext, countries: set[str]) -> dict[str, Any] | None:
    """The graphic with only what the narration supports, or None when too little is left."""

    if kind == "map":
        valid = {c.lower(): c for c in countries}
        names = [valid[c.lower()] for c in data.get("countries", []) if isinstance(c, str) and c.lower() in valid]
        points = []
        for p in data.get("points", [])[:8]:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            where = geocode(ctx, str(p.get("query") or p["name"]))
            if where:
                note = p.get("note") if p.get("note") and said(p.get("note"), text) else None
                points.append({"name": str(p["name"]), "lon": where[0], "lat": where[1], "note": note})
        if not points and not names:
            return None
        zoom = data.get("zoom")
        zoom = zoom if isinstance(zoom, int) and 0 <= zoom < len(points) else None
        return {"type": "map", "title": data.get("title"), "countries": names, "points": points,
                "route": bool(data.get("route")) and len(points) > 1, "zoom": zoom, "globe": bool(data.get("globe"))}
    if kind == "compare":
        rows = [r for r in data.get("rows", []) if isinstance(r, dict) and _num(r.get("a")) is not None
                and _num(r.get("b")) is not None and said(r["a"], text) and said(r["b"], text)]
        if len(rows) < 2 or not (data.get("left") or {}).get("name") or not (data.get("right") or {}).get("name"):
            return None
        return {"type": "compare", "title": data.get("title"), "left": {"name": data["left"]["name"]},
                "right": {"name": data["right"]["name"]},
                "rows": [{"label": str(r.get("label", "")), "a": _num(r["a"]), "b": _num(r["b"]), "unit": r.get("unit"),
                          "better": r.get("better") if r.get("better") in ("high", "low") else "high"} for r in rows[:5]]}
    if kind == "chart":
        points = [d for d in data.get("data", []) if isinstance(d, dict) and _num(d.get("value")) is not None
                  and said(d["value"], text) and said(d.get("label", ""), text)]
        if len(points) < 3 or data.get("chart") not in ("bar", "line", "pie"):
            return None
        return {"type": "chart", "chart": data["chart"], "title": str(data.get("title") or ""), "unit": data.get("unit"),
                "data": [{"label": str(d.get("label", "")), "value": _num(d["value"])} for d in points[:12]]}
    if kind == "timeline":
        events = [e for e in data.get("events", []) if isinstance(e, dict) and e.get("year") and said(e["year"], text)
                  and said(e.get("text", ""), text)]
        if len(events) < 3:
            return None
        return {"type": "timeline", "title": data.get("title"),
                "events": [{"year": str(e["year"]), "text": str(e.get("text", ""))} for e in events[:8]]}
    if kind == "specs":
        specs = [s for s in data.get("specs", []) if isinstance(s, dict) and s.get("value") and said(s["value"], text)]
        if len(specs) < 3 or not data.get("name"):
            return None
        return {"type": "specs", "name": str(data["name"]), "subtitle": data.get("subtitle"),
                "specs": [{"label": str(s.get("label", "")), "value": str(s["value"]), "unit": s.get("unit")} for s in specs[:6]]}
    if kind == "rank":
        if not data.get("name") or not isinstance(data.get("rank"), int) or not said(data["rank"], text):
            return None
        stats = [s for s in data.get("stats", []) if isinstance(s, dict) and s.get("value") and said(s["value"], text)]
        return {"type": "rank", "rank": data["rank"], "total": data.get("total") if isinstance(data.get("total"), int) else None,
                "name": str(data["name"]), "subtitle": data.get("subtitle"),
                "stats": [{"label": str(s.get("label", "")), "value": str(s["value"])} for s in stats[:4]]}
    if kind == "kinetic":
        spoken = set(re.findall(r"\w+", text.lower()))
        lines = [str(line) for line in data.get("lines", []) if str(line).strip()][:3]
        words = [w for line in lines for w in re.findall(r"\w+", line.lower())]
        if not lines or len(words) > 10 or not set(words) <= spoken:
            return None
        return {"type": "kinetic", "lines": lines}
    return None


# --- planning -----------------------------------------------------------------------------------

def plan(ctx: RunContext, sents: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    """[{"start": voice s, "end": voice s, "graphic": {...}}] validated against the narration."""

    cfg = ctx.section("graphics")
    if not cfg.get("enabled", True) or not sents:
        return []
    count = max(1, round(duration / float(cfg.get("seconds_per_graphic", 100))))
    count = min(count, int(cfg.get("max", 8)))
    allowed = [t for t in cfg.get("types", TYPES) if t in TYPES]
    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents)
    try:
        proposed = complete_json(ctx, stage=STAGE, section="planner", max_tokens=6000, user=listing[:80000],
                                 system=SYSTEM.format(count=count)
                                 + f"\nTipos permitidos en este canal: {', '.join(allowed)}.").get("graphics", [])
    except Exception as error:  # graphics are a bonus: the video is complete without them
        print(f"   Gráficos no disponibles: {str(error)[:120]}")
        return []
    countries = country_names(ctx.root)
    min_s, max_s = float(cfg.get("min_seconds", 4)), float(cfg.get("max_seconds", 12))
    out: list[dict[str, Any]] = []
    for item in proposed:
        if not isinstance(item, dict):
            continue
        try:
            kind, first, last = str(item["type"]), int(item["from"]), int(item["to"])
        except (KeyError, TypeError, ValueError):
            continue
        if kind not in allowed or not (0 <= first <= last < len(sents)):
            continue
        # the data must be said in the passage the LLM pointed at (even if the graphic is then shortened)
        nearby = " ".join(s["text"] for s in sents[max(0, first - 3): last + 2])
        while last > first and sents[last]["end"] - sents[first]["start"] > max_s:
            last -= 1
        while last + 1 < len(sents) and sents[last]["end"] - sents[first]["start"] < min_s:
            last += 1
        start, end = sents[first]["start"], min(sents[last]["end"], sents[first]["start"] + max_s)   # long sentences: first 12 s
        if start < 20 or end - start < min_s * 0.8 or any(start < o["end"] + 25 and o["start"] < end + 25 for o in out):
            continue
        graphic = clean(kind, item.get("data") or {}, nearby, ctx, countries)
        if graphic:
            out.append({"start": start, "end": end, "graphic": graphic})
        if len(out) == count:
            break
    return sorted(out, key=lambda g: g["start"])


def portrait(ctx: RunContext, name: str, people: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The athlete-card cutout of the person called `name` (full name, or a surname only one
    person has — "Yulo" must not pick his brother), with the centre of the face for avatars."""

    wanted = set(re.findall(r"\w+", name.lower()))
    names = [set(re.findall(r"\w+", p["name"].lower())) for p in people]
    exact = [p for p, n in zip(people, names) if wanted and wanted >= n]
    partial = [p for p, n in zip(people, names) if wanted and wanted & n]
    person = exact[0] if exact else partial[0] if len(partial) == 1 else None
    if person is None:
        return None
    media = {"src": person["image"], "kind": "image", "source": "web", "credit": person.get("credit", ""), "layout": "person"}
    focus = face_focus(ctx, ctx.work_dir / person["image"])
    if focus:
        media["focus"] = list(focus)
    return media


def face_focus(ctx: RunContext, path: Path) -> tuple[float, float] | None:
    import cv2
    import numpy as np

    from .analysis.detectors import Detectors

    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.ndim == 3 and image.shape[2] == 4:                # transparent cutout over grey
        alpha = image[:, :, 3:4] / 255.0
        image = (image[:, :, :3] * alpha + 128 * (1 - alpha)).astype(np.uint8)
    try:
        return Detectors(cache_dir=ctx.cache_dir).face_centre(image)
    except Exception:
        return None
