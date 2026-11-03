"""Atlas explainers drawn in code (canales/<canal>.yaml → visual: {style: atlas}): the «look closer» map deep dive.

A paper page with a globe on it: an orthographic globe (d3-geo) with a relief-tinted ocean, beige land and white ice,
that turns from one line's camera to the next (no cuts), great-circle routes drawn as the voice says them, range rings
in km around a place, a latitude zone around a pole, dots with their names, and paper cards (a date, a quote with its
source, a list, a checklist) and a rubber stamp. Some lines leave the globe for a clean chart (bars, an altitude
profile, a thermometer) or a line drawing (a plane, a ship, a thermometer…). A chapter bar (I · II · III · IV · V)
sits top right with the current chapter's name in italics; each chapter opens with a serif title card whose key word is
in italics. The intro can be dark (navy page, slate globe).

Every line gets one scene from the LLM (work/<slug>/atlas.json, cached by the script's lines); every element is keyed
to a WORD of its line, so a new voice re-times the whole film. Nothing is downloaded: the world is world-atlas
(Natural Earth, public domain), drawn in remotion/components/graphics/Atlas.tsx.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .context import RunContext
from .sourcing.common import key

VERSION = 1
ICONS = ("plane", "twinjet", "ship", "train", "car", "truck", "thermometer", "fuel", "hospital", "building", "person",
         "people", "clock", "mountain", "snow", "factory", "money", "phone", "satellite", "lighthouse", "bridge", "warning")
CARDS = ("date", "quote", "list", "checks", "note")
CHARTS = ("bars", "profile", "thermo")

SYSTEM = """
Eres el director de arte de un canal de mapas explicados dibujados en código: una página de papel con un GLOBO
terráqueo (proyección ortográfica) que gira de una frase a la siguiente, rutas que se trazan, círculos de alcance,
tarjetas de papel y, a veces, un gráfico limpio o un dibujo lineal en lugar del globo. Para CADA frase numerada del
guion devuelve UNA escena que la enseña. Campos (los que no uses: null o []):
- "view": "globe" (casi siempre), "chart" (la frase compara cifras, una altitud o una temperatura) o "icon" (la frase
  habla de un objeto: un avión de dos motores, un barco, un termómetro…)
- "camera": {{"lat": .., "lon": .., "zoom": 1-6}} hacia dónde mira el globo (coordenadas REALES; 1 = el globo entero,
  2 = un océano o continente, 3-4 = un país o región, 5-6 = una ciudad o isla). Para el polo sur: lat -90; norte: 90.
  Repite la cámara anterior si la frase sigue en el mismo sitio: el globo solo gira cuando cambia el lugar.
- "dark": true solo en las frases del gancho inicial (página oscura); después false
- "points": [{{"name": "PERTH", "lat", "lon", "at": "palabra"}}] puntos con nombre (máx. 6)
- "routes": [{{"from": [lat, lon], "to": [lat, lon], "label": "6.500 km" o "", "dashed": true si es una ruta posible
  o una medida, "style": "main" (la ruta de la historia, roja) o "many" (muchos vuelos de fondo, finos), "at": "palabra"}}]
  (máx. 8; "many" para «cada día cientos de aviones cruzan el Ártico»)
- "rings": [{{"lat", "lon", "km": radio en km, "label": "USHUAIA", "at": "palabra"}}] círculos de alcance (máx. 6)
- "zone": {{"lat": -60, "label": "Zona Polar Sur", "at": "palabra"}} el paralelo que rodea un polo y lo que encierra, o null
- "highlight": [{{"name": "Russia", "label": "RUSIA"}}] países tintados ("name" en inglés como en Natural Earth)
- "card": {{"kind": {cards}, "big": "1954" (date) o "", "title": "Scandinavian Airlines" , "lines": ["Copenhague → Los
  Ángeles"] (máx. 4 líneas cortas; en "checks" cada línea es una casilla; en "quote" la cita LITERAL del guion),
  "source": "Tratado Antártico, art. VII" (quote) o "", "side": "left"|"right", "at": "palabra"}} o null
- "stamp": {{"text": "NO PROHIBIDO", "at": "palabra"}} el sello (1-2 palabras) o null
- "headline": {{"text": "¿Por qué los aviones *evitan* la Antártida?", "at": "palabra"}} la pregunta del título, con
  UNA palabra clave entre *asteriscos*, solo cuando la frase la formula; si no, null
- "chart" (solo con view "chart"): {{"kind": "bars", "title": "TIEMPO MÁXIMO HASTA UN AEROPUERTO CON UN MOTOR",
  "bars": [{{"label": "Por defecto", "value": 60, "unit": "min"}}, {{"label": "Boeing 787", "value": 330, "unit": "min"}}]}}
  o {{"kind": "profile", "title": "ALTITUD", "unit": "km", "points": [0, 1.5, 3, 4, 3.5, 2, 0] (alturas del terreno de un
  lado a otro), "line": {{"value": 3, "label": "SEGURO ≈ 3 KM"}}, "cruise": 11}} o {{"kind": "thermo", "title": "",
  "unit": "°C", "min": -90, "max": 0, "value": -47, "label": "JET A-1"}}
- "icon" (solo con view "icon"): {{"name": {icons}, "label": "DOS MOTORES", "at": "palabra"}}
"at" es SIEMPRE una palabra LITERAL de esa frase. Usa SOLO datos, cifras, nombres y fechas del guion. Máx. 3 elementos
nuevos por frase; lo anterior se queda si la frase sigue en el mismo sitio (repítelo). Textos en el idioma del guion.
Devuelve SOLO JSON: {{"scenes": [{{"n": 1, "view": "globe", "camera": {{..}}, "dark": false, "points": [], "routes": [],
"rings": [], "zone": null, "highlight": [], "card": null, "stamp": null, "headline": null, "chart": null, "icon": null}}]}}
""".strip()


def active(ctx: RunContext) -> bool:
    return str(ctx.section("visual").get("style") or "").lower() == "atlas"


WRITING = {
    "es": ("ESTE CANAL SON MAPAS EXPLICADOS SOBRE UN GLOBO, SIN METRAJE: rutas, círculos de alcance, tarjetas y algún "
           "gráfico. Estructura (8-10 min, ~1.200 palabras, frases de 5-12 palabras): 1) el gancho mirando el mapa (un "
           "contraste: «arriba cientos de vuelos; abajo, casi nada»), la pregunta del título, un experimento que el "
           "espectador puede hacer («coge un globo y estira una cuerda de A a B») con su cifra, y la explicación fácil "
           "negada («y no, no está prohibido» + la cita literal de la fuente); 2) la promesa: «Hay cinco razones. La "
           "primera no tiene nada que ver con X. Y la última costó N vidas»; 3) CINCO capítulos «## » de 2-4 palabras "
           "(«Nadie a quien volar»), cada uno una razón: el dato o la regla con su cifra, el mapa que lo demuestra, el "
           "matiz «en la práctica…»; enlaza cada capítulo con el siguiente («pero aunque…, chocaría con el segundo "
           "problema»); 4) la última razón es una historia real con fecha y hora exactas; 5) a mitad, UNA frase: «Si te "
           "gusta ver el mundo a través de mapas como este, suscríbete»; 6) el giro «y aun así, a veces…»; 7) el cierre "
           "repite las cinco razones en una línea cada una y vuelve a la imagen del gancho. Cada dato comprobable: marca "
           "[COMPROBAR] lo que no sea seguro."),
    "en": ("THIS CHANNEL IS MAP DEEP DIVES ON A GLOBE, NO FOOTAGE: routes, range rings, paper cards and the odd chart. "
           "Structure (8-10 min, ~1,200 words, sentences of 5-12 words): 1) the hook looking at the map (a contrast: "
           "«up top, hundreds of flights; down here, almost nothing»), the title's question, an experiment the viewer "
           "can do («take a globe and stretch a string from A to B») with its number, and the easy explanation denied "
           "(«and no, it isn't banned» + the source quoted word for word); 2) the promise: «There are five reasons why. "
           "The first has nothing to do with X. The last one cost N lives»; 3) FIVE «## » chapters of 2-4 words («Nobody "
           "to fly to»), each one reason: the fact or rule with its number, the map that proves it, the «in practice…» "
           "nuance; bridge each chapter to the next («but even if…, they'd hit the second problem»); 4) the last reason "
           "is a true story with its exact date and time; 5) halfway, ONE sentence: «If you like seeing the world through "
           "maps like this, subscribe»; 6) the twist «and yet, sometimes…»; 7) the close repeats the five reasons in one "
           "line each and returns to the hook's image. Every fact checkable: mark [CHECK] anything unsure."),
}


def writing(ctx: RunContext) -> str:
    """For the script draft: how this channel's scripts are written."""

    if not active(ctx):
        return ""
    lang = str(ctx.section("align").get("language", "es"))[:2]
    own = str(ctx.section("visual").get("writing") or "").strip()
    return WRITING.get(lang, WRITING["en"]) + ("\n" + own if own else "")


# --- cleaning the LLM's scenes ------------------------------------------------------------------------------------

def _float(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict) and "lat" in value and "lon" in value:
        return _float(value["lat"], -90, 90, 0), _float(value["lon"], -180, 180, 0)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return _float(value[0], -90, 90, 0), _float(value[1], -180, 180, 0)
        except (TypeError, ValueError):
            return None
    return None


def _text(value: Any, words: int, upper: bool = False, chars: int = 60) -> str:
    text = " ".join(str(value or "").split()[:words]).strip()[:chars]
    return text.upper() if upper else text


def _at(value: Any) -> str:
    return _text(value, 1)


def clean(scene: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Only the vocabulary, numbers in range; a scene without a camera keeps the previous one."""

    prev_cam = (previous or {}).get("camera") or {"lat": 20.0, "lon": 0.0, "zoom": 1.0}
    cam = scene.get("camera") if isinstance(scene.get("camera"), dict) else {}
    point = _point(cam) if cam else None
    camera = {"lat": round(point[0], 4), "lon": round(point[1], 4), "zoom": round(_float(cam.get("zoom"), 1, 6, prev_cam["zoom"]), 2)} \
        if point else dict(prev_cam)
    view = str(scene.get("view") or "globe")
    out: dict[str, Any] = {"type": "atlas", "view": view if view in ("globe", "chart", "icon") else "globe",
                           "camera": camera, "dark": bool(scene.get("dark"))}
    out["points"] = [{"name": _text(p.get("name"), 3, True, 28), "lat": _point(p)[0], "lon": _point(p)[1], "at": _at(p.get("at"))}
                     for p in (scene.get("points") or [])[:6] if isinstance(p, dict) and _point(p) and str(p.get("name") or "").strip()]
    routes = []
    for r in (scene.get("routes") or [])[:8]:
        if isinstance(r, dict) and _point(r.get("from")) and _point(r.get("to")):
            routes.append({"from": list(_point(r["from"])), "to": list(_point(r["to"])), "label": _text(r.get("label"), 3, False, 24),
                           "dashed": bool(r.get("dashed")), "style": "many" if r.get("style") == "many" else "main",
                           "at": _at(r.get("at"))})
    out["routes"] = routes
    out["rings"] = [{"lat": _point(r)[0], "lon": _point(r)[1], "km": _float(r.get("km"), 50, 6000, 1000),
                     "label": _text(r.get("label"), 3, True, 24), "at": _at(r.get("at"))}
                    for r in (scene.get("rings") or [])[:6] if isinstance(r, dict) and _point(r)]
    zone = scene.get("zone") if isinstance(scene.get("zone"), dict) else None
    out["zone"] = {"lat": _float(zone.get("lat"), -89, 89, -60), "label": _text(zone.get("label"), 4, False, 32),
                   "at": _at(zone.get("at"))} if zone and zone.get("lat") is not None else None
    out["highlight"] = [{"name": str(h.get("name")).strip(), "label": _text(h.get("label"), 3, True, 24)}
                        for h in (scene.get("highlight") or [])[:6] if isinstance(h, dict) and str(h.get("name") or "").strip()]
    card = scene.get("card") if isinstance(scene.get("card"), dict) else None
    if card and str(card.get("kind")) in CARDS and (card.get("title") or card.get("lines") or card.get("big")):
        out["card"] = {"kind": card["kind"], "big": _text(card.get("big"), 2, False, 14), "title": _text(card.get("title"), 8, False, 60),
                       "lines": [_text(x, 14, False, 90) for x in (card.get("lines") or [])[:4] if str(x or "").strip()],
                       "source": _text(card.get("source"), 8, False, 60), "side": "left" if card.get("side") == "left" else "right",
                       "at": _at(card.get("at"))}
    else:
        out["card"] = None
    stamp = scene.get("stamp") if isinstance(scene.get("stamp"), dict) else None
    out["stamp"] = {"text": _text(stamp.get("text"), 3, True, 22), "at": _at(stamp.get("at"))} \
        if stamp and str(stamp.get("text") or "").strip() else None
    headline = scene.get("headline") if isinstance(scene.get("headline"), dict) else None
    out["headline"] = {"text": _text(headline.get("text"), 12, False, 80), "at": _at(headline.get("at"))} \
        if headline and str(headline.get("text") or "").strip() else None
    out["chart"] = _chart(scene.get("chart")) if out["view"] == "chart" else None
    icon = scene.get("icon") if isinstance(scene.get("icon"), dict) else None
    out["icon"] = {"name": icon["name"], "label": _text(icon.get("label"), 4, True, 28), "at": _at(icon.get("at"))} \
        if out["view"] == "icon" and icon and icon.get("name") in ICONS else None
    if out["view"] == "chart" and not out["chart"] or out["view"] == "icon" and not out["icon"]:
        out["view"] = "globe"                     # nothing valid to show instead: the globe stays
    return out


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _chart(chart: Any) -> dict[str, Any] | None:
    if not isinstance(chart, dict) or chart.get("kind") not in CHARTS:
        return None
    kind = chart["kind"]
    out: dict[str, Any] = {"kind": kind, "title": _text(chart.get("title"), 10, True, 70), "unit": _text(chart.get("unit"), 1, False, 8)}
    if kind == "bars":
        bars = [{"label": _text(b.get("label"), 4, False, 28), "value": _num(b.get("value")), "unit": _text(b.get("unit"), 1, False, 8)}
                for b in (chart.get("bars") or [])[:5] if isinstance(b, dict) and _num(b.get("value")) is not None]
        if not bars:
            return None
        out["bars"] = bars
    elif kind == "profile":
        points = [p for p in (_num(x) for x in (chart.get("points") or [])[:40]) if p is not None]
        if len(points) < 3:
            return None
        out["points"] = points
        line = chart.get("line") if isinstance(chart.get("line"), dict) else None
        out["line"] = {"value": _num(line.get("value")), "label": _text(line.get("label"), 5, True, 32)} \
            if line and _num(line.get("value")) is not None else None
        out["cruise"] = _num(chart.get("cruise"))
    else:
        value, low, high = _num(chart.get("value")), _num(chart.get("min")), _num(chart.get("max"))
        if value is None:
            return None
        low = low if low is not None else min(value - 10, -50)
        high = high if high is not None else max(value + 10, 0)
        if high <= low:
            return None
        out.update({"value": value, "min": low, "max": high, "label": _text(chart.get("label"), 4, True, 24)})
    return out


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    from .llm import complete_json

    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    cache = ctx.work_dir / "atlas.json"
    digest = key(VERSION, lines)
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if saved.get("key") == digest:
            return saved["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    system = SYSTEM.format(cards="|".join(CARDS), icons="|".join(ICONS))
    guide = str(ctx.section("visual").get("guide") or "").strip()
    if guide:
        system += "\n" + guide
    story = "\n".join(f"[{n}] {text}" for n, (_, text) in enumerate(lines, 1))
    found: dict[int, dict[str, Any]] = {}
    for start in range(0, len(lines), 40):
        batch = lines[start:start + 40]
        user = (f"EL GUION ENTERO:\n{story}\n\n" if len(lines) > 40 else "") + f"FRASES {start + 1}-{start + len(batch)}:\n" + \
            "\n".join(f"[{start + n}] {text}" for n, (_, text) in enumerate(batch, 1))
        try:
            result = complete_json(ctx, stage="atlas", section="planner", system=system, user=user, max_tokens=550 * len(batch))
            found.update({int(s.get("n", 0)): s for s in result.get("scenes", []) if isinstance(s, dict)})
        except Exception as error:
            print(f"   Atlas: sin escenas de la IA ({str(error)[:100]})")
    out: dict[str, dict[str, Any]] = {}
    previous = None
    for n, (shot_id, _) in enumerate(lines, 1):
        previous = clean(found.get(n) or {}, previous)
        out[shot_id] = previous
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


# --- timing: every element at its word ----------------------------------------------------------------------------

def _frame_of(word: str, line_words: list[tuple[int, str]], fallback: int) -> int:
    target = re.sub(r"[^\w]", "", word.lower())
    if target:
        for f, text in line_words:
            if re.sub(r"[^\w]", "", text.lower()) == target:
                return f
        for f, text in line_words:
            if target in re.sub(r"[^\w]", "", text.lower()):
                return f
    return fallback


def _as_written(ctx: RunContext, title: str) -> str:
    """The chapter's name as the script writes it («## Nadie a quien *volar*»): the planner keeps it in upper case."""

    title = " ".join(title.split())
    script = ctx.materials_dir / "guion.txt"
    try:
        for line in script.read_text("utf-8").splitlines():
            if line.startswith("## "):
                heading = " ".join(line[3:].split())
                if heading.replace("*", "").upper()[:48] == title.replace("*", "").upper()[:48]:
                    return heading
    except OSError:
        pass
    return title[:1] + title[1:].lower() if title.isupper() else title


ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def groups(ctx: RunContext, shots: list[Any], fps: int, taken: list[Any], words: Any = None) -> list[dict[str, Any]]:
    """An atlas scene for every line nothing else covers: the globe turning from the previous camera to this one,
    every element at its word, the chapter bar, and a title card on every chapter heading."""

    def covered(a: int, b: int) -> bool:
        return any(g.from_ < b and a < g.from_ + g.durationInFrames for g in taken)

    chapters: list[str] = []
    chapter_of: dict[str, int] = {}
    for shot in shots:
        if shot.type == "chapter" and shot.chapterTitle:
            chapters.append(_as_written(ctx, str(shot.chapterTitle)))
        chapter_of[shot.id] = len(chapters)          # 0 = before the first chapter (the hook)
    todo = [(shot, shot.from_, shot.from_ + shot.durationInFrames) for shot in shots
            if shot.type != "endscreen" and not covered(shot.from_, shot.from_ + shot.durationInFrames)]
    if not todo:
        return []
    found = scenes(ctx, [s for s, _, _ in todo if s.type != "chapter"])
    spoken = [(round(w.start * fps), w.text.strip()) for w in (words.words if words is not None else []) if w.text.strip()]
    brand = str(ctx.section("brand").get("name") or ctx.channel or "").strip()
    out = []
    prev: dict[str, Any] | None = None
    for n, (shot, a, b) in enumerate(todo):
        span = b - a
        current = chapter_of.get(shot.id, 0)
        if shot.type == "chapter":
            title = _as_written(ctx, str(shot.chapterTitle or shot.text or ""))
            g: dict[str, Any] = {"type": "atlas", "view": "title", "camera": (prev or {}).get("camera") or {"lat": 20, "lon": 0, "zoom": 1},
                                 "dark": False, "title": {"number": ROMAN[(shot.chapterNumber or current or 1) - 1] if (shot.chapterNumber or current or 1) <= 10 else str(shot.chapterNumber),
                                                          "text": title}}
        else:
            g = json.loads(json.dumps(found.get(shot.id) or clean({}, prev)))
            line_words = [(f - a, t) for f, t in spoken if a <= f < b]
            stagger = 0
            for name in ("zone", "card", "stamp", "headline", "icon"):
                if g.get(name):
                    g[name]["at"] = _frame_of(g[name].get("at", ""), line_words, round(span * 0.2) + stagger)
                    stagger += round(0.35 * fps)
            for name in ("points", "routes", "rings"):
                for i, item in enumerate(g.get(name) or []):
                    item["at"] = _frame_of(item.get("at", ""), line_words, round(span * 0.15) + i * round(0.25 * fps))
        g["prev"] = (prev or g)["camera"]
        g["chapters"] = chapters
        g["chapter"] = current
        g["brand"] = brand
        g["seed"] = n
        out.append({"id": f"atlas-{shot.id}", "kind": "graphic", "from": a, "durationInFrames": span, "graphic": g})
        if g["view"] == "globe":
            prev = g
        elif prev is None:
            prev = g
    return out


def moments(groups: list[Any], fps: int, count: int) -> list[float]:
    """Seconds for thumbnails: the globe shots with most drawn on them (late in the shot, everything is in)."""

    scored = []
    for group in groups:
        g = (group.graphic if hasattr(group, "graphic") else group.get("graphic")) or {}
        if g.get("type") != "atlas" or g.get("view") != "globe":
            continue
        start = group.from_ if hasattr(group, "from_") else group["from"]
        dur = group.durationInFrames if hasattr(group, "durationInFrames") else group["durationInFrames"]
        score = sum(len(g.get(k) or []) for k in ("routes", "rings", "points")) + sum(1 for k in ("zone", "card", "stamp", "headline") if g.get(k))
        scored.append((score, (start + dur * 0.85) / fps))
    return [t for _, t in sorted(scored, key=lambda x: -x[0])[:count]]


def cues(g: dict[str, Any], fps: int) -> list[tuple[str, int, float]]:
    """Synthesized sounds for a scene (sfx_synth names): a soft whoosh when the globe turns far, a pen tick per route or
    ring, a thud for the stamp, paper for a card."""

    out: list[tuple[str, int, float]] = []
    a, b = g.get("prev") or {}, g.get("camera") or {}
    if a and b and (abs(a.get("lat", 0) - b.get("lat", 0)) + abs(a.get("lon", 0) - b.get("lon", 0)) > 25 or abs(a.get("zoom", 1) - b.get("zoom", 1)) > 1.5):
        out.append(("whoosh-down" if b.get("zoom", 1) > a.get("zoom", 1) else "whoosh-up", 0, 0.3))
    for item in [*(g.get("routes") or []), *(g.get("rings") or [])][:4]:
        out.append(("marker", int(item.get("at") or 0), 0.3))
    if g.get("stamp"):
        out.append(("stamp", int(g["stamp"].get("at") or 0) + 6, 0.7))
    if g.get("card"):
        out.append(("paper", int(g["card"].get("at") or 0), 0.4))
    if g.get("view") == "title":
        out.append(("swipe", 0, 0.3))
    if g.get("view") == "chart":
        out.append(("data", round(fps * 0.4), 0.25))
    return out
