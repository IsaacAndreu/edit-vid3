"""Map explainers drawn in code (canales/<canal>.yaml → visual: {style: mapas}), in the Johnny Harris / RealLifeLore
look: real satellite imagery for the close-ups, a vintage paper map for everything wider, a red marker drawn on top,
and physical paper props (tags with tape, torn strips with a highlighter, tear-off calendar pages, a rubber stamp).

One continuous camera: every line of the script gets a camera target (a point and a zoom level, Web Mercator) and
the things it draws; the component (remotion/components/graphics/MapStory.tsx) flies from the previous line's camera
to this one, so there are no hard cuts. The satellite fades into the paper map as the camera pulls out (zoom 9.3 →
7.3). Every element is keyed to a WORD of the line («the red circle draws on "this"»), so a new voice re-times the
whole film.

Satellite: Sentinel-2 cloudless 2016 by EOX (CC BY 4.0; the credit stays in frame), stitched around each place at
two zoom levels; the land is cut out (it is redder than blue) and laid over a drawn navy sea with a soft teal
shallow-water halo. Nothing else is downloaded. Cached in work/<slug>/mapas.json and cache/satellite/.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .context import RunContext
from .sourcing.common import key

VERSION = 1
VIEWS = ("sat", "paper")
PROPS = ("calendar", "clock", "price", "flag", "note")
SAT_MAX = 13                     # EOX's sharpest level
SAT_FADE = (7.3, 9.3)            # below 7.3 only paper, above 9.3 only satellite

SYSTEM = """
Eres el animador de un canal de mapas explicados al estilo Johnny Harris / RealLifeLore: satélite real en los planos
cercanos, un mapa de papel antiguo para todo lo amplio, rotulador rojo dibujado encima y elementos de papel. UNA sola
cámara continua (sin cortes): para cada frase del guion (numerada) di adónde va la cámara y qué se dibuja, con este
vocabulario y nada más:
- "center": {{"lat": .., "lon": ..}} el punto al que mira (coordenadas REALES y exactas del lugar)
- "zoom": 2-13 (Web Mercator: 2 = continente/océano, 5 = país, 8 = región, 11 = isla o ciudad, 13 = un barrio)
  Por encima de 9 se ve el satélite; por debajo de 7, el mapa de papel. Alterna: cerca (el sitio), lejos (el contexto),
  y vuelve a entrar.
- "circle": {{"lat", "lon", "word": "1-2 palabras a mano junto al círculo", "at": "palabra de la frase en que se dibuja"}} o null
- "tags": [{{"name": "NOMBRE", "sub": "país o dato corto", "lat", "lon", "at": "palabra"}}] etiquetas de papel en cada sitio que se nombra
- "line": {{"points": [[lat, lon], ...], "label": "a mano, 1-3 palabras", "count": "la cifra con unidad: 3,8 KM",
  "dashed": true si es medida o frontera, "at": "palabra"}} o null — una medida, una ruta, una frontera, la línea de cambio de fecha
- "props": [{{"kind": {props}, "top": "DOMINGO", "big": "12:00", "sub": "MEDIODÍA", "flip": {{"top": "LUNES", "big": "9:00", "sub": ""}} o null,
  "side": "left"|"right", "at": "palabra"}}] objetos de papel que aparecen (máx. 2; uno puede girar a otro valor)
- "strips": [{{"text": "TIRA DE PAPEL", "lat", "lon", "at": "palabra"}}] tiras con subrayado amarillo (el giro local)
- "stamp": {{"text": "1987", "at": "palabra"}} o null — el sello rojo con golpe (el año de la historia)
- "split": {{"lon": la longitud de la línea, "left": "NOMBRE IZQUIERDA", "right": "NOMBRE DERECHA"}} o null — dos lados tintados
- "tracker": {{"title": "quién", "date": "fecha", "time": "hora", "counter": "dato"}} o null — tarjeta de seguimiento
- "path": {{"points": [[lat, lon], ...], "at": "palabra"}} o null — un camino de puntos con un marcador que lo recorre
- "highlight": [{{"name": "Russia", "label": "RUSIA"}}, ...] países tintados y rotulados en el mapa de papel ("name" en
  inglés como en Natural Earth, "label" en el idioma del guion)
- "end": {{"label": "EL DATO FINAL", "wrong": "lo que crees", "right": "la verdad"}} o null (solo la última frase)
"at" es SIEMPRE una palabra LITERAL de esa frase. No pongas más de 3 elementos nuevos por frase; lo de antes se queda si
la cámara sigue en el mismo sitio. Los textos, en el idioma del guion, en MAYÚSCULAS.
Devuelve SOLO JSON: {{"scenes": [{{"n": 1, "center": {{..}}, "zoom": .., "circle": null, "tags": [], "line": null,
"props": [], "strips": [], "stamp": null, "split": null, "tracker": null, "path": null, "highlight": [], "end": null}}]}}
""".strip()


def active(ctx: RunContext) -> bool:
    return str(ctx.section("visual").get("style") or "").lower() == "mapas"


def writing(ctx: RunContext) -> str:
    """For the script draft: how this channel's scripts are written."""

    if not active(ctx):
        return ""
    own = str(ctx.section("visual").get("writing") or "").strip()
    return ("ESTE CANAL SON MAPAS EXPLICADOS, SIN METRAJE: satélite real, mapa de papel y rotulador. Cada frase tiene "
            "que poder ENSEÑARSE en un mapa. Estructura: el gancho en la primera frase, mirando el sitio («Desde esta isla "
            "puedes ver el mañana»); los nombres de los sitios; la cifra clave (una distancia, una ruta, una frontera); "
            "el contexto, alejándose al continente o al océano; la consecuencia (dos objetos: calendarios, relojes, "
            "precios); el giro local; la historia con su año («En 1987…»); y el remate final con un dato que lo cambia "
            "todo. Comprueba cada dato (lugares, cifras, años) y marca [COMPROBAR] lo que no sea seguro. Frases cortas."
            + ("\n" + own if own else ""))


# --- geometry -----------------------------------------------------------------------------------------------------

def _float(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
        return default if math.isnan(v) else min(hi, max(lo, v))
    except (TypeError, ValueError):
        return default


def _point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict) and "lat" in value and "lon" in value:
        return _float(value["lat"], -85, 85, 0), _float(value["lon"], -180, 180, 0)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return _float(value[0], -85, 85, 0), _float(value[1], -180, 180, 0)
    return None


def _text(value: Any, words: int, upper: bool = True) -> str:
    text = " ".join(str(value or "").split()[:words]).strip()
    return text.upper() if upper else text


def clean(scene: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Only the vocabulary, coordinates in range; a scene without a camera keeps the previous one."""

    center = _point(scene.get("center")) or ((previous or {}).get("lat", 0.0), (previous or {}).get("lon", 0.0))
    out: dict[str, Any] = {"type": "mapa", "lat": round(center[0], 5), "lon": round(center[1], 5),
                           "zoom": round(_float(scene.get("zoom"), 2, SAT_MAX, (previous or {}).get("zoom", 5)), 2)}
    circle = scene.get("circle") if isinstance(scene.get("circle"), dict) else None
    if circle and _point(circle):
        lat, lon = _point(circle)
        out["circle"] = {"lat": lat, "lon": lon, "word": _text(circle.get("word"), 2, False), "at": _text(circle.get("at"), 1, False)}
    tags = []
    for t in (scene.get("tags") or [])[:3]:
        if isinstance(t, dict) and _point(t) and str(t.get("name") or "").strip():
            lat, lon = _point(t)
            tags.append({"name": _text(t["name"], 4), "sub": _text(t.get("sub"), 5), "lat": lat, "lon": lon, "at": _text(t.get("at"), 1, False)})
    out["tags"] = tags
    line = scene.get("line") if isinstance(scene.get("line"), dict) else None
    points = [p for p in (_point(x) for x in (line or {}).get("points") or []) if p][:40]
    if len(points) >= 2:
        out["line"] = {"points": points, "label": _text(line.get("label"), 3), "count": _text(line.get("count"), 3),
                       "dashed": bool(line.get("dashed")), "at": _text(line.get("at"), 1, False)}
    props = []
    for p in (scene.get("props") or [])[:2]:
        if isinstance(p, dict) and str(p.get("kind") or "") in PROPS:
            flip = p.get("flip") if isinstance(p.get("flip"), dict) else None
            props.append({"kind": p["kind"], "top": _text(p.get("top"), 3), "big": _text(p.get("big"), 2), "sub": _text(p.get("sub"), 3),
                          "flip": {"top": _text(flip.get("top"), 3), "big": _text(flip.get("big"), 2), "sub": _text(flip.get("sub"), 3)} if flip else None,
                          "side": "left" if p.get("side") == "left" else "right", "at": _text(p.get("at"), 1, False)})
    out["props"] = props
    strips = []
    for s in (scene.get("strips") or [])[:2]:
        if isinstance(s, dict) and str(s.get("text") or "").strip():
            point = _point(s) or center
            strips.append({"text": _text(s["text"], 4), "lat": point[0], "lon": point[1], "at": _text(s.get("at"), 1, False)})
    out["strips"] = strips
    stamp = scene.get("stamp") if isinstance(scene.get("stamp"), dict) else None
    if stamp and str(stamp.get("text") or "").strip():
        out["stamp"] = {"text": _text(stamp["text"], 2), "at": _text(stamp.get("at"), 1, False)}
    split = scene.get("split") if isinstance(scene.get("split"), dict) else None
    if split and "lon" in split:
        out["split"] = {"lon": _float(split["lon"], -180, 180, center[1]), "left": _text(split.get("left"), 2), "right": _text(split.get("right"), 2)}
    tracker = scene.get("tracker") if isinstance(scene.get("tracker"), dict) else None
    if tracker and any(tracker.get(k) for k in ("title", "date", "time", "counter")):
        out["tracker"] = {k: _text(tracker.get(k), 4) for k in ("title", "date", "time", "counter")}
    path = scene.get("path") if isinstance(scene.get("path"), dict) else None
    ppoints = [p for p in (_point(x) for x in (path or {}).get("points") or []) if p][:40]
    if len(ppoints) >= 2:
        out["path"] = {"points": ppoints, "at": _text(path.get("at"), 1, False)}
    out["highlight"] = [{"name": str(h.get("name") if isinstance(h, dict) else h).strip(),
                         "label": _text(h.get("label") if isinstance(h, dict) else h, 3)}
                        for h in (scene.get("highlight") or [])[:6] if str(h.get("name") if isinstance(h, dict) else h).strip()]
    end = scene.get("end") if isinstance(scene.get("end"), dict) else None
    if end and str(end.get("right") or "").strip():
        out["end"] = {"label": _text(end.get("label"), 6), "wrong": _text(end.get("wrong"), 3), "right": _text(end.get("right"), 3)}
    return out


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    from .llm import complete_json

    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    cache = ctx.work_dir / "mapas.json"
    digest = key(VERSION, lines)
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if saved.get("key") == digest:
            return saved["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    system = SYSTEM.format(props="|".join(PROPS))
    guide = str(ctx.section("visual").get("guide") or "").strip()
    if guide:
        system += "\n" + guide
    story = "\n".join(f"[{n}] {text}" for n, (_, text) in enumerate(lines, 1))
    found: dict[int, dict[str, Any]] = {}
    for start in range(0, len(lines), 40):
        batch = lines[start:start + 40]
        user = (f"EL GUION ENTERO:\n{story}\n\n" if len(lines) > 40 else "") + f"PLANOS {start + 1}-{start + len(batch)}:\n" + \
            "\n".join(f"[{start + n}] {text}" for n, (_, text) in enumerate(batch, 1))
        try:
            result = complete_json(ctx, stage="mapas", section="planner", system=system, user=user, max_tokens=500 * len(batch))
            found.update({int(s.get("n", 0)): s for s in (result.get("scenes") or []) if isinstance(s, dict)})
        except Exception as error:
            print(f"   Mapas: sin planos de la IA ({str(error)[:100]})")
    out: dict[str, dict[str, Any]] = {}
    previous = None
    for n, (shot_id, _) in enumerate(lines, 1):
        previous = clean(found.get(n) or {}, previous)
        out[shot_id] = previous
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


# --- satellite: land cut out over a drawn sea ---------------------------------------------------------------------

def land_over_sea(source: Path, target: Path) -> None:
    """The satellite with its sea replaced: the land (redder than blue, after a light blur; opened and closed, specks
    removed, holes filled) over a navy sea (#14304A in the middle, #0B1E31 at the edges) with a teal shallow halo."""

    import numpy as np
    from PIL import Image, ImageFilter

    image = Image.open(source).convert("RGB")
    blurred = np.asarray(image.filter(ImageFilter.GaussianBlur(1.5))).astype(np.int16)
    land = (blurred[..., 0] - blurred[..., 2]) > 5
    mask = Image.fromarray((land * 255).astype(np.uint8))
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))      # open: specks out
    mask = mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))      # close: holes in
    w, h = image.size
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
    centre, edge = np.array([0x14, 0x30, 0x4A]), np.array([0x0B, 0x1E, 0x31])
    sea = (centre[None, None, :] * (1 - r[..., None]) + edge[None, None, :] * r[..., None])
    halo = np.asarray(mask.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(14))).astype(np.float32) / 255
    teal = np.array([0x2A, 0x62, 0x74])
    sea = sea * (1 - 0.75 * halo[..., None]) + teal[None, None, :] * 0.75 * halo[..., None]
    alpha = np.asarray(mask.filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32)[..., None] / 255
    out = np.asarray(image).astype(np.float32) * alpha + sea * (1 - alpha)
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(target, quality=88)


def satellite_layers(ctx: RunContext, lat: float, lon: float, zoom: float) -> list[dict[str, Any]]:
    """The close views for a camera target: the imagery at its zoom (rounded up) and two levels wider, land over sea."""

    import requests

    from .satellite import layer

    top = min(SAT_MAX, max(8, math.ceil(zoom)))
    session = requests.Session()
    out = []
    for z in sorted({top - 2, top}):
        name = key(f"mapa:{lat:.4f}:{lon:.4f}:{z}")[:12]
        raw = ctx.work_dir / "graphics" / "mapa" / f"{name}-raw.jpg"
        final = ctx.work_dir / "graphics" / "mapa" / f"{name}.jpg"
        if not final.is_file():
            if not (raw.is_file() or layer(ctx, "eox", lat, lon, z, raw, session)):
                continue
            try:
                land_over_sea(raw, final)
            except Exception as error:          # the plain imagery rather than none
                print(f"   Satélite sin recortar ({str(error)[:80]})")
                final = raw
        out.append({"z": z, "lat": lat, "lon": lon, "src": str(final.relative_to(ctx.work_dir)).replace("\\", "/")})
    return out


def _at(word: str, line_words: list[tuple[int, str]], fallback: int) -> int:
    """Frame (within the shot) where the line says `word` (its first occurrence), else the fallback."""

    target = re.sub(r"[^\w]", "", word.lower())
    if target:
        for f, text in line_words:
            if re.sub(r"[^\w]", "", text.lower()) == target:
                return f
        for f, text in line_words:
            if target in re.sub(r"[^\w]", "", text.lower()):
                return f
    return fallback


def groups(ctx: RunContext, shots: list[Any], fps: int, taken: list[Any], words: Any = None) -> list[dict[str, Any]]:
    """A map shot for every line nothing else covers: the camera from the previous target to this one, satellite
    layers where it is close, every element at its word."""

    def covered(a: int, b: int) -> bool:
        return any(g.from_ < b and a < g.from_ + g.durationInFrames for g in taken)

    todo = [(shot, shot.from_, shot.from_ + shot.durationInFrames) for shot in shots
            if shot.type != "endscreen" and not covered(shot.from_, shot.from_ + shot.durationInFrames)]
    if not todo:
        return []
    found = scenes(ctx, [s for s, _, _ in todo])
    spoken = [(round(w.start * fps), w.text.strip()) for w in (words.words if words is not None else []) if w.text.strip()]
    lang = str(ctx.section("align").get("language", "es"))[:2]
    credit = {"es": "Imagen: Sentinel-2 cloudless 2016 de EOX (CC BY 4.0), datos Copernicus Sentinel modificados",
              "de": "Bild: Sentinel-2 cloudless 2016 von EOX (CC BY 4.0), enthält modifizierte Copernicus-Sentinel-Daten"}.get(
        lang, "Imagery: Sentinel-2 cloudless 2016 by EOX (CC BY 4.0), contains modified Copernicus Sentinel data")
    sat_cache: dict[tuple[float, float, float], list[dict[str, Any]]] = {}
    out = []
    prev_cam = None
    for n, (shot, a, b) in enumerate(todo):
        g = json.loads(json.dumps(found[shot.id]))
        line_words = [(f - a, t) for f, t in spoken if a <= f < b]
        span = b - a
        stagger = 0
        for name in ("circle", "line", "stamp", "path"):
            if g.get(name):
                g[name]["at"] = _at(g[name].get("at", ""), line_words, round(span * 0.25) + stagger)
                stagger += round(0.3 * fps)
        for name in ("tags", "props", "strips"):
            for i, item in enumerate(g.get(name) or []):
                item["at"] = _at(item.get("at", ""), line_words, round(span * 0.2) + i * round(0.4 * fps))
        cam = {"lat": g["lat"], "lon": g["lon"], "zoom": g["zoom"]}
        g["prev"] = prev_cam or cam
        if max(g["zoom"], g["prev"]["zoom"]) >= SAT_FADE[0]:          # the satellite shows somewhere in this shot
            layers = []
            for c in ([cam] if g["zoom"] >= SAT_FADE[0] else []) + ([g["prev"]] if g["prev"]["zoom"] >= SAT_FADE[0] else []):
                k = (round(c["lat"], 3), round(c["lon"], 3), math.ceil(max(c["zoom"], 8)))
                if k not in sat_cache:
                    try:
                        sat_cache[k] = satellite_layers(ctx, c["lat"], c["lon"], c["zoom"])
                    except Exception as error:
                        print(f"   Satélite no disponible ({str(error)[:80]}): mapa de papel")
                        sat_cache[k] = []
                layers += sat_cache[k]
            g["sat"] = layers
            g["credit"] = credit
        g["seed"] = n
        out.append({"id": f"mapa-{shot.id}", "kind": "graphic", "from": a, "durationInFrames": span, "graphic": g})
        prev_cam = cam
    return out


def moments(groups: list[Any], fps: int, count: int) -> list[float]:
    """Seconds for thumbnails: the shots with most drawn on them (late in the shot, everything is in)."""

    scored = []
    for group in groups:
        g = (group.graphic if hasattr(group, "graphic") else group.get("graphic")) or {}
        if g.get("type") != "mapa":
            continue
        start = group.from_ if hasattr(group, "from_") else group["from"]
        dur = group.durationInFrames if hasattr(group, "durationInFrames") else group["durationInFrames"]
        score = sum(1 for k in ("circle", "line", "stamp", "split", "end", "path") if g.get(k)) + len(g.get("tags") or []) \
            + len(g.get("props") or []) + (1 if g.get("zoom", 0) >= 9 else 0)
        scored.append((score, (start + dur * 0.85) / fps))
    return [t for _, t in sorted(scored, key=lambda x: -x[0])[:count]]
