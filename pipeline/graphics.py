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
from .sourcing.common import tokens

STAGE = "timeline"
GEO_CACHE = "geo.json"
TYPES = ("map", "compare", "chart", "timeline", "specs", "rank", "kinetic", "score", "press", "article", "rule", "split",
         "strobe", "replay", "standings", "podium", "race", "card", "scale", "receipt", "tier", "iceberg")

# Everyday references for "scale" graphics (general knowledge, so the script does not have to say them).
REFERENCES = {
    "persona": ("Persona media", 1.75), "canasta": ("Canasta de baloncesto", 3.05), "porteria": ("Portería de fútbol", 2.44),
    "autobus": ("Autobús de dos pisos", 4.4), "jirafa": ("Jirafa", 5.5), "casa": ("Casa de dos plantas", 6.0),
    "barra": ("Barra fija", 2.8), "potro": ("Mesa de salto", 1.35), "red_voley": ("Red de voleibol", 2.43),
    "campo_futbol": ("Campo de fútbol", 105.0), "ballena_azul": ("Ballena azul", 30.0),
    "boeing_737": ("Boeing 737-800", 39.5), "edificio_10": ("Edificio de 10 plantas", 30.0),
}

# Fixed words drawn on the graphics, in the narration's language (a dub translates them again).
WORDS = {
    "es": {"stamp": "PROHIBIDO", "rulebook": "REGLAMENTO", "d": "DIFICULTAD", "e": "EJECUCIÓN", "pen": "PENALIZACIÓN",
           "total": "NOTA", "since": "DESDE", "replay": "REPETICIÓN"},
    "en": {"stamp": "BANNED", "rulebook": "RULEBOOK", "d": "DIFFICULTY", "e": "EXECUTION", "pen": "PENALTY",
           "total": "SCORE", "since": "SINCE", "replay": "REPLAY"},
    "pt": {"stamp": "PROIBIDO", "rulebook": "REGULAMENTO", "d": "DIFICULDADE", "e": "EXECUÇÃO", "pen": "PENALIDADE",
           "total": "NOTA", "since": "DESDE", "replay": "REPLAY"},
    "fr": {"stamp": "INTERDIT", "rulebook": "RÈGLEMENT", "d": "DIFFICULTÉ", "e": "EXÉCUTION", "pen": "PÉNALITÉ",
           "total": "NOTE", "since": "DEPUIS", "replay": "RALENTI"},
    "it": {"stamp": "VIETATO", "rulebook": "REGOLAMENTO", "d": "DIFFICOLTÀ", "e": "ESECUZIONE", "pen": "PENALITÀ",
           "total": "PUNTEGGIO", "since": "DAL", "replay": "REPLAY"},
    "de": {"stamp": "VERBOTEN", "rulebook": "REGELWERK", "d": "SCHWIERIGKEIT", "e": "AUSFÜHRUNG", "pen": "ABZUG",
           "total": "WERTUNG", "since": "SEIT", "replay": "WIEDERHOLUNG"},
}


def fixed_words(ctx: RunContext | None) -> dict[str, str]:
    code = str(ctx.section("align").get("language", "es")) if ctx else "es"
    return WORDS.get(code, WORDS["en"])

SYSTEM = """
Eres el grafista de un canal de documentales de YouTube. Te paso la narración en frases numeradas
con sus tiempos. Propón como máximo {count} gráficos animados donde expliquen MEJOR que un plano de
vídeo, repartidos por el vídeo (nunca en los primeros 20 s, separados al menos 25 s). Tipos:
- "map": la historia cambia de lugar o nombra ciudades/países relevantes. data: {{"title": "…",
  "countries": ["nombres de países EN INGLÉS como en Natural Earth, p. ej. 'United States of America'"],
  "points": [{{"name": "nombre de la ciudad en el idioma del guion", "query": "ciudad, país en inglés para geolocalizarla",
  "note": "dato corto dicho en el guion o null", "logo": "empresa/aerolínea de ese lugar SOLO si el guion la nombra
  ahí (p. ej. 'Emirates' en Dubái), si no null"}}], "route": true si es un viaje/carrera de un lugar a otro,
  "zoom": índice del punto al que acercarse o null, "globe": true para presentar un país lejano,
  "date": "fecha o año DICHO en esas frases, como se dice ('17 de noviembre de 2013', '2019'), si no null",
  "region_label": "nombre corto (máx. 3 palabras) para la zona resaltada, p. ej. 'SALÓN DE DUBÁI', o null"}}
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
- "score": una nota de gimnasia con sus partes dichas en el guion (dificultad + ejecución − penalización = nota).
  data: {{"name": "gimnasta o null", "title": "aparato/competición como se dice, o null", "d": 6.6, "e": 8.7,
  "penalty": 0.3 o null, "total": 15.0}}
- "press": la prensa o la gente reaccionó a algo (escándalo, polémica, hazaña). data: {{"items": [{{"outlet": "medio
  SOLO si el guion lo nombra, si no null", "headline": "titular hecho con palabras del guion, máx. 12 palabras",
  "date": "fecha dicha o null", "highlight": "2-4 palabras del titular a subrayar"}}]}} (1-3 titulares)
- "article": el guion cuenta lo que publicó un periódico o una noticia concreta con cifras (un pedido, una quiebra, un
  anuncio): una página de periódico con su titular y un párrafo, con las cifras clave rodeadas en rojo. data:
  {{"outlet": "medio SOLO si el guion lo nombra, si no null", "author": "periodista SOLO si el guion lo nombra, si no null",
  "headline": "titular con palabras del guion, máx. 14", "body": "1-2 frases LITERALES del guion, 20-45 palabras",
  "circles": ["1-3 cifras o palabras de body a rodear, copiadas tal cual"]}}
- "rule": el guion cita o explica una norma/regla del reglamento (algo prohibido, una penalización, un cambio de
  regla). data: {{"source": "nombre del reglamento SOLO si se dice (p. ej. 'Código de Puntuación'), si no null",
  "article": "artículo si se dice, si no null", "text": "la norma con palabras del guion, máx. 30 palabras",
  "highlight": "3-6 palabras de text a resaltar", "stamp": true si la norma prohíbe/elimina algo}}
- "split": se contrastan DOS personas, momentos o ejecuciones que se ven en el metraje ("antes/ahora",
  "ella… mientras que él…"). data: {{"title": "…" o null, "left": {{"name": "…"}}, "right": {{"name": "…"}}}}
- "strobe": el guion describe UN movimiento concreto que se ve en el metraje (un salto, un mortal, un
  lanzamiento) y conviene ver todas sus posiciones a la vez. data: {{"name": "nombre del movimiento como se
  dice", "note": "dato corto dicho (p. ej. 'tres giros y medio') o null"}}
- "replay": el momento decisivo de una acción (el aterrizaje, la caída, el salto ganador) merece repetición
  a cámara lenta. data: {{"name": "etiqueta de máx. 4 palabras del guion (p. ej. 'el doble mortal') o null"}}
- "standings": se dicen las notas/marcas de al menos 3 participantes de una misma prueba (una final).
  data: {{"title": "…" o null, "rows": [{{"name": "…", "score": "nota como se dice"}}]}} en el orden en que se dicen
- "podium": se dice quién quedó 1.º, 2.º y 3.º (o al menos 1.º y 2.º) de una prueba. data: {{"title": "prueba como se
  dice" o null, "places": [{{"place": 1, "name": "…", "note": "nota/marca dicha o null"}}]}}
- "race": la evolución de una cifra de varios países/personas a lo largo de al menos 3 años/fechas dichos (medallas por
  país por Juegos…). data: {{"title": "…", "unit": "…" o null, "steps": [{{"label": "2012", "values": {{"China": 8, "Japón": 5}}}}]}}
- "card": presentar a un atleta con al menos 3 cifras suyas dichas (títulos, medallas, récords, edad…), como una carta
  de videojuego. data: {{"name": "…", "position": "especialidad/aparato como se dice o null", "headline": {{"label": "…",
  "value": "la cifra más impresionante"}}, "stats": [{{"label": "máx. 10 letras", "value": "…"}}]}} (3-6 stats)
- "scale": una medida física impresionante (altura de un salto, longitud, velocidad convertida a altura no). data:
  {{"title": "…", "axis": "height"|"length", "unit": "m", "items": [{{"name": "…", "value": 2.45}}],
  "references": [claves de {refs}, las que den escala, máx. 2]}}
- "kinetic": una frase MUY corta y potente (máx. 8 palabras, literal del guion), como máximo 2. data: {{"lines": ["…", "…"]}}
- "receipt": el guion desglosa un coste o un precio en al menos 3 partidas con su cifra (lo que cuesta montar algo, de
  qué se compone un precio, en qué se va el dinero): un ticket que se imprime línea a línea. data: {{"title": "qué se
  paga, máx. 5 palabras", "items": [{{"label": "partida, máx. 4 palabras", "value": "cifra como se dice"}}],
  "total": {{"label": "TOTAL o como se diga", "value": "cifra dicha"}} o null}} (3-8 partidas)
Reglas: TODOS los datos (cifras, años, nombres) deben estar en esas frases del guion; nada inventado.
Textos en el idioma del guion, cortos. Devuelve SOLO JSON:
{{"graphics": [{{"type": "map", "from": 12, "to": 13, "data": {{...}}}}]}}
""".strip()


RANK_SYSTEM = """
Este vídeo es un ranking / cuenta atrás. Te paso la narración en frases numeradas. Encuentra la frase
donde se PRESENTA cada puesto ("en el número 7…", "puesto 3:", "number one is…") y devuelve SOLO JSON:
{"total": 10 o null, "items": [{"rank": 7, "sentence": 12, "name": "nombre corto del elemento",
 "subtitle": "país, marca o categoría dicho en el guion, o null",
 "place": "si el elemento es un lugar: 'ciudad, país' EN INGLÉS para geolocalizarlo; si no, null",
 "country": "si es un lugar: su país EN INGLÉS como en Natural Earth (p. ej. 'United States of America', 'China'); si no, null",
 "stats": [{"label": "…", "value": "cifra tal como se dice"}]}]}
Reglas: el número del puesto debe decirse en esa frase o la siguiente; "stats" (máx. 3) solo con cifras
dichas al hablar de ese puesto; textos en el idioma del guion; nada inventado.
""".strip()


BANNED_SYSTEM = """
Este vídeo repasa cosas PROHIBIDAS/ELIMINADAS de un deporte (elementos, técnicas, trajes, reglas…). Te paso
la narración en frases numeradas. Encuentra la frase donde se PRESENTA cada elemento prohibido y devuelve SOLO JSON:
{"items": [{"sentence": 12, "name": "nombre corto del elemento como se dice",
 "who": "persona asociada (quien lo hizo famoso) si se dice, si no null",
 "year": "año en que se prohibió si se dice, si no null",
 "reason": "por qué se prohibió, máx. 8 palabras con palabras del guion, o null",
 "number": número si el guion los numera ("el número 5"), si no null}]}
Reglas: nada inventado; textos en el idioma del guion.
""".strip()


TIER_SYSTEM = """
Este vídeo es una TIER LIST: coloca elementos en niveles (S, A, B, C, D… o los niveles que use el guion). Te paso la
narración en frases numeradas. Encuentra la frase donde se COLOCA cada elemento en su nivel y devuelve SOLO JSON:
{"tiers": ["S", "A", "B", "C", "D"], "items": [{"sentence": 12, "name": "nombre corto del elemento", "tier": "A"}]}
"tiers": los niveles en orden, del mejor al peor, tal como los nombra el guion (máx. 7, cada uno máx. 12 letras).
Reglas: cada elemento, en la frase donde se dice en qué nivel va (o justo antes); nada inventado; textos en el
idioma del guion.
""".strip()

ICEBERG_SYSTEM = """
Este vídeo es un ICEBERG: niveles que van de lo más conocido (arriba, sobre el agua) a lo más oscuro (abajo del
todo). Te paso la narración en frases numeradas. Devuelve SOLO JSON:
{"levels": [{"sentence": 3, "title": "nombre del nivel como lo dice el guion, o 'NIVEL 1'"}],
 "items": [{"sentence": 5, "name": "nombre corto del elemento, máx. 5 palabras", "level": 1}]}
"levels": la frase donde EMPIEZA cada nivel, en orden (nivel 1 = el de arriba). "items": cada caso o secreto que se
presenta, con el número de su nivel. Reglas: nada inventado; textos en el idioma del guion.
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


def said_words(value: Any, text: str, share: float = 1.0) -> bool:
    """At least `share` of the meaningful words of `value` (4+ letters, and every number) are in `text`."""

    spoken = set(re.findall(r"\w+", text.lower()))
    wanted = [w for w in re.findall(r"\w+", str(value).lower()) if len(w) >= 4 or w.isdigit()]
    if not said(value, text):
        return False
    return not wanted or sum(w in spoken for w in wanted) / len(wanted) >= share - 1e-9


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
                brand = str(p.get("logo") or "").strip()
                brand = brand if brand and tokens(brand) <= tokens(text) else None   # only a company the script names
                points.append({"name": str(p["name"]), "lon": where[0], "lat": where[1], "note": note, "logo": brand})
        if not points and not names:
            return None
        zoom = data.get("zoom")
        zoom = zoom if isinstance(zoom, int) and 0 <= zoom < len(points) else None
        date = str(data.get("date") or "").strip()
        date = date if date and all(n in _numbers(text) for n in _numbers(date)) and _numbers(date) else None
        label = str(data.get("region_label") or "").strip()[:28] or None
        return {"type": "map", "title": data.get("title"), "countries": names, "points": points,
                "route": bool(data.get("route")) and len(points) > 1, "zoom": zoom, "globe": bool(data.get("globe")),
                "date": date, "regionLabel": label if names else None}
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
    if kind == "score":
        d, e, total = _num(data.get("d")), _num(data.get("e")), _num(data.get("total"))
        penalty = _num(data.get("penalty")) if data.get("penalty") not in (None, "", 0, "0") else None
        if None in (d, e, total) or not all(said(v, text) for v in (data["d"], data["e"], data["total"])):
            return None
        if penalty is not None and not said(data["penalty"], text):
            penalty = None
        if abs(d + e - (penalty or 0) - total) > 0.051:
            return None                                   # the parts must add up to the score that was said
        w = fixed_words(ctx)
        return {"type": "score", "name": data.get("name") if data.get("name") and said_words(data["name"], text) else None,
                "title": data.get("title") if data.get("title") and said_words(data["title"], text) else None,
                "d": d, "e": e, "penalty": penalty, "total": total,
                "labels": {"d": w["d"], "e": w["e"], "penalty": w["pen"], "total": w["total"]}}
    if kind == "press":
        items = []
        for item in data.get("items", [])[:3]:
            if not isinstance(item, dict) or not item.get("headline"):
                continue
            headline = " ".join(str(item["headline"]).split())
            if len(headline.split()) > 14 or not said_words(headline, text, 0.7):
                continue
            highlight = item.get("highlight") if isinstance(item.get("highlight"), str) and item["highlight"].lower() in headline.lower() else None
            items.append({"outlet": item.get("outlet") if item.get("outlet") and said_words(item["outlet"], text) else None,
                          "headline": headline, "date": item.get("date") if item.get("date") and said(item["date"], text)
                          and said_words(item["date"], text) else None, "highlight": highlight})
        return {"type": "press", "items": items} if items else None
    if kind == "article":
        headline = " ".join(str(data.get("headline") or "").split())
        body = " ".join(str(data.get("body") or "").split())
        if not headline or len(headline.split()) > 14 or not said_words(headline, text, 0.7):
            return None
        if not 8 <= len(body.split()) <= 60 or not said_words(body, text, 0.85):
            return None
        circles = [c for c in (data.get("circles") or []) if isinstance(c, str) and c.strip() and c.lower() in body.lower()][:3]
        return {"type": "article", "headline": headline, "body": body, "circles": circles,
                "outlet": data.get("outlet") if data.get("outlet") and said_words(data["outlet"], text) else None,
                "author": data.get("author") if data.get("author") and said_words(data["author"], text) else None}
    if kind == "rule":
        body = " ".join(str(data.get("text") or "").split())
        if not body or len(body.split()) > 34 or not said_words(body, text, 0.7):
            return None
        highlight = data.get("highlight") if isinstance(data.get("highlight"), str) and data["highlight"].lower() in body.lower() else None
        source = data.get("source") if data.get("source") and said_words(data["source"], text) else None
        article = data.get("article") if data.get("article") and said(data["article"], text) and _numbers(str(data["article"])) else None
        return {"type": "rule", "source": source or fixed_words(ctx)["rulebook"], "article": article, "text": body,
                "highlight": highlight, "stamp": fixed_words(ctx)["stamp"] if data.get("stamp") else None}
    if kind == "split":
        left, right = (data.get("left") or {}).get("name"), (data.get("right") or {}).get("name")
        if not left or not right or left == right or not said_words(left, text) or not said_words(right, text):
            return None
        return {"type": "split", "title": data.get("title") if data.get("title") and said_words(data["title"], text, 0.6) else None,
                "left": {"name": str(left)}, "right": {"name": str(right)}}
    if kind == "strobe":
        if not data.get("name") or not said_words(data["name"], text, 0.6):
            return None
        note = data.get("note") if data.get("note") and said_words(data["note"], text, 0.7) else None
        return {"type": "strobe", "name": str(data["name"]), "note": note}
    if kind == "replay":
        name = data.get("name") if data.get("name") and len(str(data["name"]).split()) <= 5 \
            and said_words(data["name"], text, 0.7) else None
        return {"type": "replay", "name": name, "badge": fixed_words(ctx)["replay"]}
    if kind == "standings":
        rows = [r for r in data.get("rows", []) if isinstance(r, dict) and r.get("name") and r.get("score")
                and _num(r["score"]) is not None and said(r["score"], text) and said_words(r["name"], text, 0.5)]
        if len(rows) < 3:
            return None
        return {"type": "standings", "title": data.get("title") if data.get("title") and said_words(data["title"], text, 0.6) else None,
                "rows": [{"name": str(r["name"]), "score": str(r["score"])} for r in rows[:8]]}
    if kind == "podium":
        places = {}
        for item in data.get("places", []):
            if isinstance(item, dict) and item.get("place") in (1, 2, 3) and item.get("name") \
                    and item["place"] not in places and said_words(item["name"], text, 0.5):
                note = item.get("note") if item.get("note") and said(item["note"], text) and _numbers(str(item["note"])) else None
                places[item["place"]] = {"place": item["place"], "name": str(item["name"]), "note": note}
        if 1 not in places or len(places) < 2:
            return None
        return {"type": "podium", "title": data.get("title") if data.get("title") and said_words(data["title"], text, 0.6) else None,
                "places": [places[k] for k in sorted(places)]}
    if kind == "race":
        steps = []
        for step in data.get("steps", [])[:12]:
            if not isinstance(step, dict) or not step.get("label") or not said(step["label"], text) \
                    or not isinstance(step.get("values"), dict):
                continue
            values = {str(k): _num(v) for k, v in step["values"].items()
                      if _num(v) is not None and said(v, text) and said_words(k, text, 0.5)}
            if len(values) >= 2:
                steps.append({"label": str(step["label"]), "values": values})
        if len(steps) < 3:
            return None
        return {"type": "race", "title": str(data.get("title") or ""), "unit": data.get("unit"), "steps": steps}
    if kind == "card":
        stats = [x for x in data.get("stats", []) if isinstance(x, dict) and x.get("value") and x.get("label")
                 and said(x["value"], text) and _numbers(str(x["value"]))]
        head = data.get("headline") if isinstance(data.get("headline"), dict) else {}
        if not data.get("name") or len(stats) < 3 or not said_words(data["name"], text, 0.5):
            return None
        if not (head.get("value") and said(head["value"], text) and _numbers(str(head["value"]))):
            head = stats[0]
        return {"type": "card", "name": str(data["name"]),
                "position": data.get("position") if data.get("position") and said_words(data["position"], text, 0.6) else None,
                "headline": {"label": str(head.get("label", ""))[:14], "value": str(head["value"])},
                "stats": [{"label": str(x["label"])[:12], "value": str(x["value"])} for x in stats[:6]]}
    if kind == "scale":
        items = [{"name": str(i["name"]), "value": _num(i["value"])} for i in data.get("items", [])
                 if isinstance(i, dict) and i.get("name") and _num(i.get("value")) is not None and said(i["value"], text)]
        if not items or data.get("axis") not in ("height", "length"):
            return None
        refs = [{"name": REFERENCES[r][0], "value": REFERENCES[r][1], "reference": True}
                for r in data.get("references", [])[:2] if r in REFERENCES]
        return {"type": "scale", "title": data.get("title"), "axis": data["axis"], "unit": str(data.get("unit") or "m"),
                "items": items[:3] + refs}
    if kind == "receipt":
        items = [{"label": str(x["label"])[:40], "value": str(x["value"])} for x in data.get("items", [])
                 if isinstance(x, dict) and x.get("label") and x.get("value") and _numbers(str(x["value"]))
                 and said(x["value"], text)]
        total = data.get("total") if isinstance(data.get("total"), dict) else None
        if total and not (total.get("value") and _numbers(str(total["value"])) and said(total["value"], text)):
            total = None
        if len(items) < 3:
            return None
        return {"type": "receipt", "title": str(data.get("title") or "")[:60] or None, "items": items[:8],
                "total": {"label": str(total.get("label") or "TOTAL"), "value": str(total["value"])} if total else None}
    if kind == "kinetic":
        spoken = set(re.findall(r"\w+", text.lower()))
        lines = [str(line) for line in data.get("lines", []) if str(line).strip()][:3]
        words = [w for line in lines for w in re.findall(r"\w+", line.lower())]
        if not lines or len(words) > 10 or not set(words) <= spoken:
            return None
        return {"type": "kinetic", "lines": lines}
    return None


# --- planning -----------------------------------------------------------------------------------

def ranking(ctx: RunContext, sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ranking videos: a "#N" card where each position is introduced and, when it is a place, a map
    that flies to it right after. Every position gets its card (no spacing rule between them)."""

    cfg = ctx.section("graphics")
    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents)
    try:
        result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=6000, user=listing[:80000],
                               system=RANK_SYSTEM)
    except Exception as error:  # the video is complete without them
        print(f"   Tarjetas del ranking no disponibles: {str(error)[:120]}")
        return []
    total = result.get("total") if isinstance(result.get("total"), int) else None
    seconds, map_seconds = float(cfg.get("rank_seconds", 5)), float(cfg.get("rank_map_seconds", 4.5))
    countries = country_names(ctx.root) if cfg.get("rank_map", True) else set()
    out: list[dict[str, Any]] = []
    for item in sorted((i for i in result.get("items", []) if isinstance(i, dict)), key=lambda i: _as_int(i.get("sentence"))):
        n, rank = _as_int(item.get("sentence")), item.get("rank")
        if not 0 <= n < len(sents) or not isinstance(rank, int) or not item.get("name") or any(o["graphic"].get("rank") == rank for o in out):
            continue
        intro = " ".join(s["text"] for s in sents[n: n + 2])
        if not said(rank, intro):
            continue
        passage = " ".join(s["text"] for s in sents[n: n + 6])
        stats = [x for x in item.get("stats", []) if isinstance(x, dict) and x.get("value") and said(x["value"], passage)]
        subtitle = item.get("subtitle") if isinstance(item.get("subtitle"), str) and item["subtitle"].strip() else None
        start = sents[n]["start"]
        if out and start < out[-1]["end"] + 1:
            continue
        card = {"type": "rank", "rank": rank, "total": total, "name": str(item["name"]), "subtitle": subtitle,
                "stats": [{"label": str(x.get("label", "")), "value": str(x["value"])} for x in stats[:3]]}
        out.append({"start": start, "end": start + seconds, "graphic": card, "ranked": True})
        where = geocode(ctx, str(item["place"])) if countries and item.get("place") else None
        if where:
            country = {c.lower(): c for c in countries}.get(str(item.get("country") or "").lower())
            out.append({"start": start + seconds, "end": start + seconds + map_seconds, "ranked": True,
                        "graphic": {"type": "map", "title": None, "countries": [country] if country else [],
                                    "points": [{"name": str(item["name"]), "lon": where[0], "lat": where[1], "note": None}],
                                    "route": False, "zoom": 0, "globe": False}})
    return out


def banned(ctx: RunContext, sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """"Banned" videos: a card with a stamp where each banned element is introduced."""

    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents)
    try:
        result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=5000, user=listing[:80000],
                               system=BANNED_SYSTEM)
    except Exception as error:  # the video is complete without them
        print(f"   Tarjetas de prohibidos no disponibles: {str(error)[:120]}")
        return []
    seconds = float(ctx.section("graphics").get("banned_seconds", 5.5))
    w = fixed_words(ctx)
    out: list[dict[str, Any]] = []
    for item in sorted((i for i in result.get("items", []) if isinstance(i, dict)), key=lambda i: _as_int(i.get("sentence"))):
        n = _as_int(item.get("sentence"))
        if not 0 <= n < len(sents) or not item.get("name"):
            continue
        intro, passage = " ".join(s["text"] for s in sents[n: n + 2]), " ".join(s["text"] for s in sents[max(0, n - 1): n + 8])
        if not said_words(item["name"], passage, 0.5):
            continue
        start = sents[n]["start"]
        if out and start < out[-1]["end"] + 8:
            continue
        year = str(item["year"]) if item.get("year") and said(item["year"], passage) and _numbers(str(item["year"])) else None
        number = item.get("number") if isinstance(item.get("number"), int) and said(item["number"], intro) else None
        out.append({"start": start, "end": start + seconds, "ranked": True, "graphic": {
            "type": "banned", "name": str(item["name"]), "number": number,
            "who": item.get("who") if item.get("who") and said_words(item["who"], passage) else None,
            "reason": item.get("reason") if item.get("reason") and said_words(item["reason"], passage, 0.7) else None,
            "stamp": w["stamp"], "since": f"{w['since']} {year}" if year else None}})
    return out


def tier(ctx: RunContext, sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tier lists: the board with every element placed so far, each new one flying into its row."""

    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents)
    try:
        result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=5000, user=listing[:80000],
                               system=TIER_SYSTEM)
    except Exception as error:  # the video is complete without them
        print(f"   Tier list no disponible: {str(error)[:120]}")
        return []
    tiers = [str(t).strip()[:12] for t in result.get("tiers", []) if str(t).strip()][:7]
    if len(tiers) < 2:
        return []
    seconds = float(ctx.section("graphics").get("tier_seconds", 4.5))
    placed: list[dict[str, str]] = []
    out: list[dict[str, Any]] = []
    for item in sorted((i for i in result.get("items", []) if isinstance(i, dict)), key=lambda i: _as_int(i.get("sentence"))):
        n, name, level = _as_int(item.get("sentence")), str(item.get("name") or "").strip(), str(item.get("tier") or "").strip()
        if not 0 <= n < len(sents) or not name or level not in tiers or any(p["name"] == name for p in placed):
            continue
        if not said_words(name, " ".join(s["text"] for s in sents[max(0, n - 2): n + 2]), 0.5):
            continue
        start = sents[n]["start"]
        if out and start < out[-1]["end"] + 0.5:
            continue
        placed.append({"name": name[:40], "tier": level})
        out.append({"start": start, "end": start + seconds, "ranked": True, "graphic": {
            "type": "tier", "tiers": tiers, "items": [dict(p) for p in placed], "current": len(placed) - 1}})
    return out


def iceberg(ctx: RunContext, sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Iceberg videos: at each new level the camera sinks to it; the cases of the levels above stay written."""

    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {s['text']}" for s in sents)
    try:
        result = complete_json(ctx, stage=STAGE, section="planner", max_tokens=5000, user=listing[:80000],
                               system=ICEBERG_SYSTEM)
    except Exception as error:  # the video is complete without them
        print(f"   Iceberg no disponible: {str(error)[:120]}")
        return []
    levels = [lv for lv in sorted((x for x in result.get("levels", []) if isinstance(x, dict)), key=lambda x: _as_int(x.get("sentence")))
              if 0 <= _as_int(lv.get("sentence")) < len(sents) and str(lv.get("title") or "").strip()][:8]
    if len(levels) < 2:
        return []
    titles = [str(lv["title"]).strip()[:40] for lv in levels]
    items = [{"name": str(i["name"]).strip()[:40], "level": _as_int(i.get("level")) - 1, "sentence": _as_int(i.get("sentence"))}
             for i in result.get("items", []) if isinstance(i, dict) and str(i.get("name") or "").strip()
             and 1 <= _as_int(i.get("level")) <= len(levels) and 0 <= _as_int(i.get("sentence")) < len(sents)
             and said_words(i["name"], " ".join(s["text"] for s in sents[max(0, _as_int(i["sentence"]) - 1): _as_int(i["sentence"]) + 2]), 0.5)]
    seconds = float(ctx.section("graphics").get("iceberg_seconds", 5))
    out: list[dict[str, Any]] = []
    for k, level in enumerate(levels):
        start = sents[_as_int(level["sentence"])]["start"]
        if out and start < out[-1]["end"] + 1:
            continue
        before = [{"name": i["name"], "level": i["level"]} for i in items if i["level"] < k and sents[i["sentence"]]["start"] < start]
        out.append({"start": start, "end": start + seconds, "ranked": True, "graphic": {
            "type": "iceberg", "levels": titles, "current": k, "items": before[:24]}})
    return out


DATA_FILE = "datos.csv"


def _data_number(text: str) -> float | None:
    """'1.234,5' / '1,234.5' / '1234.5' / '12 %' → float (None if it is not a number)."""

    value = re.sub(r"[^\d,.\-]", "", str(text))
    if not re.search(r"\d", value):
        return None
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".") if len(value.split(",")[-1]) != 3 else value.replace(",", "")
    elif value.count(".") > 1 or (value.count(".") == 1 and len(value.split(".")[-1]) == 3
                                  and value.split(".")[0].lstrip("-") not in ("", "0")):
        value = value.replace(".", "")
    try:
        return float(value)
    except ValueError:
        return None


def read_data(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """materiales/<slug>/datos.csv: first row = header (label column, then one column per bar), then one row
    per step (year, date…). Returns (the label column's name, steps)."""

    import csv

    text = path.read_text("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(text.splitlines(), dialect) if any(c.strip() for c in r)]
    if len(rows) < 3 or len(rows[0]) < 2:
        raise ValueError(f"{path.name}: hacen falta una cabecera y al menos 2 filas con 2 columnas o más")
    names = [c.strip() for c in rows[0][1:]]
    steps = []
    for row in rows[1:]:
        values = {n: v for n, cell in zip(names, row[1:]) if n and (v := _data_number(cell)) is not None}
        if row and row[0].strip() and values:
            steps.append({"label": row[0].strip(), "values": values})
    return rows[0][0].strip(), steps


def data_race(ctx: RunContext, sents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Data videos (format "datos"): the bar chart race of materiales/<slug>/datos.csv comes in each time the
    narration says one of its steps ("en 1990…"), animating from the last step shown to that one; footage
    plays in between. The last step shown stays a little longer."""

    path = ctx.materials_dir / DATA_FILE
    if not path.is_file():
        print(f"   Formato de datos sin {path.relative_to(ctx.root)}: no hay carrera de barras")
        return []
    column, steps = read_data(path)
    cfg = ctx.section("datos")
    title = str(cfg.get("titulo") or cfg.get("title") or column or "")
    unit = cfg.get("unidad") or cfg.get("unit")
    seconds, gap = float(cfg.get("segundos", 7)), float(cfg.get("separacion", 3))
    out: list[dict[str, Any]] = []
    shown, cursor = -1, 0
    for i, step in enumerate(steps):
        wanted = set(re.findall(r"\w+", step["label"].lower()))
        found = next((s for s in sents[cursor:] if wanted <= set(re.findall(r"\w+", s["text"].lower()))), None)
        if found is None:
            continue
        cursor = found["n"] + 1
        start = found["start"]
        if out and start < out[-1]["end"] + gap:
            continue
        span = steps[max(0, shown if shown >= 0 else i - 2): i + 1]
        if len(span) < 2:
            span = [step, step]
        out.append({"start": start, "end": start + min(seconds, 2.5 + 1.5 * len(span)), "ranked": True,
                    "graphic": {"type": "race", "title": title, "unit": unit, "steps": span}})
        shown = i
    if out:
        out[-1]["end"] += float(cfg.get("final_extra", 3))
    return out


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


WEAK_HINT = ("Las frases marcadas con ⚠ no tienen buen metraje (imagen floja o de relleno): pon los gráficos PRIMERO "
             "ahí, con el tipo que mejor explique esa frase (kinetic para una idea abstracta, chart/scale/compare para "
             "cifras). Solo después reparte el resto.")
STRONG_HINT = ("Las frases marcadas con ★ tienen el MEJOR metraje del vídeo (el momento que el espectador quiere ver): "
               "no pongas gráficos encima, salvo strobe, replay o split, que usan ese mismo metraje.")
CANDIDATES_HINT = ("Propón hasta {ask} candidatos ordenados de mejor a peor: después se eligen {count} con variedad "
                   "de tipos y bien repartidos, así que propón tipos distintos.")
FOOTAGE_TYPES = {"strobe", "replay", "split", "spotlight"}      # these show the shot's own footage: welcome over the best clips


def reading_seconds(graphic: dict[str, Any]) -> float:
    """Time to take a graphic in: a couple of seconds to land plus ~0.3 s per word on screen."""

    words = 0

    def walk(value: Any) -> None:
        nonlocal words
        if isinstance(value, dict):
            for k, v in value.items():
                if k not in ("type", "media", "focus", "query", "board", "flip", "chart", "axis", "better", "sign"):
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str):
            words += len(value.split())
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            words += 1

    walk(graphic)
    return 2.0 + 0.3 * words


def choose(candidates: list[dict[str, Any]], count: int, duration: float, cfg: dict[str, Any],
           taken: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The best `count` graphics among the candidates: the LLM's order, over weak footage first, never over
    the best footage (unless the graphic shows it), at most `max_per_type` of a kind, never the same kind
    twice in a row, ≥ 25 s apart, and spread: a stretch of the video without graphics is preferred."""

    most = int(cfg.get("max_per_type", 2))
    bins = max(1, count)
    where = lambda c: min(bins - 1, int(c["start"] / max(duration, 1.0) * bins))  # noqa: E731

    def value(rank: int, c: dict[str, Any]) -> float:
        v = 1.0 - 0.6 * rank / max(1, len(candidates)) + 0.6 * min(1.0, c["weak"] / 2)
        if c["strong"]:
            v += 0.3 if c["graphic"]["type"] in FOOTAGE_TYPES else -1.5
        return v

    def fits(c: dict[str, Any], chosen: list[dict[str, Any]]) -> bool:
        kind = c["graphic"]["type"]
        if sum(o["graphic"]["type"] == kind for o in chosen) >= (2 if kind == "kinetic" else most):
            return False
        if any(c["start"] < o["end"] + 25 and o["start"] < c["end"] + 25 for o in chosen) \
                or any(c["start"] < o["end"] + 3 and o["start"] < c["end"] + 3 for o in taken):
            return False
        before = max((o for o in chosen if o["start"] < c["start"]), key=lambda o: o["start"], default=None)
        after = min((o for o in chosen if o["start"] > c["start"]), key=lambda o: o["start"], default=None)
        return not ((before and before["graphic"]["type"] == kind) or (after and after["graphic"]["type"] == kind))

    base = [(value(rank, c), rank, c) for rank, c in enumerate(candidates)]
    chosen: list[dict[str, Any]] = []
    while len(chosen) < count:
        filled = {where(o) for o in chosen}
        options = [(v + (0.4 if where(c) not in filled else 0.0), rank, c) for v, rank, c in base
                   if c not in chosen and fits(c, chosen)]
        if not options:
            break
        best = max(options, key=lambda x: (x[0], -x[1]))
        if best[0] < -0.2:
            break
        chosen.append(best[2])
    return [{"start": c["start"], "end": c["end"], "graphic": c["graphic"]} for c in chosen]


def plan(ctx: RunContext, sents: list[dict[str, Any]], duration: float, weak: set[int] | None = None,
         strong: set[int] | None = None) -> list[dict[str, Any]]:
    """[{"start": voice s, "end": voice s, "graphic": {...}}] validated against the narration.

    `weak`: sentences with poor footage (graphics.cover_weak), offered to the LLM first; `strong`: the best
    footage, kept clear. The LLM proposes about twice as many as needed and `choose` keeps the best mix."""

    cfg = ctx.section("graphics")
    if not cfg.get("enabled", True) or not sents:
        return []
    passes = {"ranking": ranking, "prohibidos": banned, "tier-list": tier, "iceberg": iceberg, "datos": data_race}
    ranked = passes[ctx.config.get("format")](ctx, sents) if ctx.config.get("format") in passes else []
    fmt = str(ctx.config.get("format") or "")
    every = float((cfg.get("seconds_per_format") or {}).get(fmt)
                  or ctx.format.get("segundos_por_grafico") or cfg.get("seconds_per_graphic", 100))
    count = max(1, round(duration / every))
    count = min(count, int(cfg.get("max", 8)))
    own = [str(t) for t in ctx.format.get("tipos") or []]             # graphics the format needs, whatever the channel
    allowed = [t for t in dict.fromkeys([*cfg.get("types", TYPES), *own]) if t in TYPES and not (ranked and t == "rank")]
    weak, strong = weak or set(), (strong or set()) - (weak or set())
    if weak:   # one more graphic per 3 weak sentences, within the channel's maximum
        count = min(int(cfg.get("max", 8)), count + len(weak) // 3)
    ask = min(2 * count, count + 8)
    mark = lambda n: "⚠ " if n in weak else "★ " if n in strong else ""  # noqa: E731
    listing = "\n".join(f"[{s['n']}] ({s['start']:.0f}s) {mark(s['n'])}{s['text']}" for s in sents)
    try:
        proposed = complete_json(ctx, stage=STAGE, section="planner", max_tokens=8000, user=listing[:80000],
                                 system=SYSTEM.format(count=ask, refs=", ".join(REFERENCES))
                                 + f"\nTipos permitidos en este canal: {', '.join(allowed)}."
                                 + (f"\n{str(ctx.format['graficos']).strip()}" if ctx.format.get("graficos") else "")
                                 + (f"\n{cfg['hint']}" if cfg.get("hint") else "")
                                 + "\n" + CANDIDATES_HINT.format(ask=ask, count=count)
                                 + (f"\n{WEAK_HINT}" if weak else "")
                                 + (f"\n{STRONG_HINT}" if strong else "")).get("graphics", [])
    except Exception as error:  # graphics are a bonus: the video is complete without them
        print(f"   Gráficos no disponibles: {str(error)[:120]}")
        return []
    countries = country_names(ctx.root)
    min_s, max_s = float(cfg.get("min_seconds", 4)), float(cfg.get("max_seconds", 12))
    candidates: list[dict[str, Any]] = []
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
        graphic = clean(kind, item.get("data") or {}, nearby, ctx, countries)
        if not graphic:
            continue
        need = min(max_s, max(min_s, reading_seconds(graphic)))      # long enough to be read, no longer
        while last > first and sents[last]["end"] - sents[first]["start"] > max_s:
            last -= 1
        while last + 1 < len(sents) and sents[last]["end"] - sents[first]["start"] < need:
            last += 1
        start, end = sents[first]["start"], min(sents[last]["end"], sents[first]["start"] + max_s)   # long sentences: first 12 s
        if start < 20 or end - start < min_s * 0.8:
            continue
        span = range(first, last + 1)
        candidates.append({"start": start, "end": end, "graphic": graphic,
                           "weak": sum(n in weak for n in span), "strong": any(n in strong for n in span)})
    out = choose(candidates, count, duration, cfg, ranked)
    if candidates:
        kinds = ", ".join(o["graphic"]["type"] for o in sorted(out, key=lambda o: o["start"]))
        print(f"   Gráficos: {len(out)} elegidos de {len(candidates)} candidatos ({kinds})")
    return sorted([*ranked, *out], key=lambda g: g["start"])


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
