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
import math
import shutil
import re
from pathlib import Path
from typing import Any

from .context import RunContext
from .sourcing.common import key

VERSION = 15
ICONS = ("plane", "twinjet", "ship", "train", "car", "truck", "thermometer", "fuel", "hospital", "building", "person",
         "people", "clock", "mountain", "snow", "factory", "money", "phone", "satellite", "lighthouse", "bridge", "warning")
CARDS = ("date", "quote", "list", "checks", "note", "clocks", "choice")
CHARTS = ("bars", "profile", "thermo")
VIEWS = ("globe", "chart", "icon", "sat", "flat", "size")
MOVERS = ("plane", "ship", "dot")

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
- "band": {{"country": "Brazil" (inglés, Natural Earth), "km": 150, "label": "150 KM", "lat": -23.9, "lon": -46.3 (un punto
  de esa costa para la etiqueta), "at": "palabra"}} la franja de la costa de un país hasta N km tierra adentro, pintada
  («dibujemos una línea a 150 km del mar», «la mitad vive a menos de 100 km de la costa»), o null
- "highlight": [{{"name": "Russia", "label": "RUSIA"}}] países ENTEROS tintados ("name" en inglés como en Natural Earth);
  nunca una región de un país (la región Norte de Brasil, el Sudeste): para eso puntos, un círculo o una etiqueta
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
- "tags": [{{"text": "14:42", "lat", "lon", "at": "palabra"}}] la cifra, la hora o el año que dice la frase, en DÍGITOS
  aunque la frase lo diga en palabras («las dos y cuarenta y dos» → "14:42"), como etiqueta de papel junto al sitio del que
  habla (máx. 3)
- "countries": [{{"name": "Spain" (inglés, como en Natural Earth), "label": "ESPAÑA", "at": "palabra"}}] cuando la frase
  NOMBRA un país (sobre todo la primera vez): sale su silueta rellena con su bandera, en una tarjeta (máx. 2: dos países
  que se comparan)
- "night": {{"date": "2026-06-21", "from": "21:30", "to": "22:30", "tz": "Europe/Madrid", "at": "palabra"}} la noche REAL
  sobre el globo (la sombra se calcula con la posición del sol): "from"/"to" en hora local de "tz"; si se mueven, la línea
  día-noche avanza durante la frase. Úsalo SIEMPRE que la frase hable de cuándo amanece, anochece o es de noche en un sitio.
  La noche se queda sola en las frases siguientes: no la repitas; cuando el guion ya no hable de ella, "night": {{"off": true}}
- "meridians": {{"step": 15, "labels": true, "at": "palabra"}} los meridianos cada N grados (husos horarios, «15 grados por
  hora»), o null
- en "highlight" puedes añadir "group": 0-3 para tintar países por grupos (husos horarios: 0 = UTC+0, 1 = UTC+1…)
- "card" de tipo "clocks": dos relojes iguales lado a lado, "big": "22:00" (la hora que marcan), "lines": ["VARSOVIA",
  "A CORUÑA"]; de tipo "choice" (la pregunta «¿Tú qué harías?»): "title": la pregunta, "lines": las 2 opciones,
  "source": "1" o "2" si la frase revela la respuesta, si no ""
- view "sat" (la frase habla de un sitio concreto que se ve desde el cielo: un puerto, una isla, un aeropuerto, una
  ciudad): "sat": {{"lat", "lon", "zoom": 9-13 (9 = una isla grande o una bahía, 11 = una ciudad o un puerto, 13 = un
  aeropuerto o un edificio), "label": "PUERTO DE ROTTERDAM", "at": "palabra"}}: el globo baja hasta la foto real de satélite.
  OBLIGATORIO: 2-4 escenas "sat" por vídeo, en los sitios concretos que nombra el guion (una ciudad, un puerto, un
  observatorio, una isla), en los momentos fuertes
- si el guion compara tamaños o dice que un mapa engaña, usa "size" o "flat" al menos una vez
- view "flat" («el mapa plano te engaña»): "flat": {{"from": [lat, lon], "to": [lat, lon], "straight": "LO QUE SUGIERE EL
  MAPA", "curve": "EL CAMINO MÁS CORTO", "at": "palabra"}}: el globo se desenrolla en un mapa plano con la línea recta, y
  aparece la curva real
- view "size" (el tamaño real de los países): "size": {{"country": "Greenland" (nombre inglés de Natural Earth), "to":
  [lat, lon] adonde se arrastra, "compare": "Algeria" o "", "label": "GROENLANDIA ≈ ARGELIA", "at": "palabra"}}: el país
  se arrastra por el mapa y encoge o crece con su tamaño real
- en cada ruta "mover": "plane" | "ship" | "dot" (un avión, un barco o un punto la recorre dejando estela; las rutas
  "many" llevan puntos solas)
- "counter": {{"value": 6500, "unit": "km", "label": "DISTANCIA", "at": "palabra"}} un contador que sube hasta la cifra
  mientras la voz la dice (distancias, personas, vuelos, años), o null
- en "night", "lights": true enciende las ciudades en el lado de noche
- "icon" (solo con view "icon"): {{"name": {icons}, "label": "DOS MOTORES", "at": "palabra"}}
- "lens": {{"lat", "lon", "zoom": 5-9, "label": "ESTRECHO DE GIBRALTAR", "at": "palabra"}} una lupa: un círculo en una
  esquina que amplía un sitio pequeño sin dejar el globo (un estrecho, una isla, dos ciudades juntas), o null
Si el guion RECORRE un camino (una carretera de país en país, un viaje, una expedición), dibuja cada tramo como una
"route" que empieza donde acabó la anterior (mover "dot"): el recorrido se queda dibujado mientras avanza.
Reglas: CADA frase añade al menos UNA cosa nueva en pantalla (un punto, una ruta, un círculo, un tag con su cifra, una
tarjeta…): nunca un globo sin nada nuevo. Zoom 1-2 cuando la frase habla de un país entero, un continente o el mundo; 4-6 (un mapa de cerca que llena
la pantalla) cuando la frase nombra una ciudad, un río, una sierra o una región y lo que dibujas está a menos de 10
grados de la cámara; nunca 3. Un dibujo ("icon") como mucho cada 8 frases y un sello cada 10. La cámara tiene que ENSEÑAR todo lo que dibujas (una ruta entre dos sitios lejanos: mira a su punto medio con
zoom 1-1,5; una ruta que pasa cerca de un polo: mira al polo); si la frase cita un documento, una ley o a alguien, pon la
cita en una "card" de tipo "quote" con su fuente; si niega o confirma algo con rotundidad («no está prohibido», «nadie
sobrevivió»), pon un "stamp"; si la frase da un año con un suceso, una "card" de tipo "date".
Un "counter" o un "sat" valen como «algo nuevo». "at" es SIEMPRE una palabra LITERAL de esa frase. Usa SOLO datos, cifras, nombres y fechas del guion. Máx. 3 elementos
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
           "primera no tiene nada que ver con X. Y la última costó N vidas»; 3) CINCO razones, SIN rótulos «## » "
           "(el vídeo nunca se para en un título): cada una se anuncia en la voz («Razón uno: no hay nadie a quien volar») y es: el dato o la regla con su cifra, el mapa que lo demuestra, el "
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
           "The first has nothing to do with X. The last one cost N lives»; 3) FIVE reasons, NO «## » headings (the video "
           "never stops on a title): each announced by the voice («Reason one: there's nobody to fly to») and made of: the fact or rule with its number, the map that proves it, the «in practice…» "
           "nuance; bridge each chapter to the next («but even if…, they'd hit the second problem»); 4) the last reason "
           "is a true story with its exact date and time; 5) halfway, ONE sentence: «If you like seeing the world through "
           "maps like this, subscribe»; 6) the twist «and yet, sometimes…»; 7) the close repeats the five reasons in one "
           "line each and returns to the hook's image. Every fact checkable: mark [CHECK] anything unsure."),
    "pt": ("ESTE CANAL SÃO MAPAS EXPLICADOS SOBRE UM GLOBO, SEM FILMAGEM: rotas, círculos de alcance, cartões de papel e "
           "algum gráfico. Estrutura (8-10 min, ~1.200 palavras, frases de 5-12 palavras): 1) o gancho olhando o mapa (um "
           "contraste: «lá em cima, centenas de voos; aqui embaixo, quase nada»), a pergunta do título, um experimento que "
           "o espectador pode fazer («pegue um mapa e coloque o dedo no Brasil») com seu número, e a explicação fácil "
           "negada («e não, não é proibido» + a citação literal da fonte); 2) a promessa: «São cinco motivos. O primeiro "
           "não tem nada a ver com X. E o último custou N vidas»; 3) CINCO motivos, SEM títulos «## » (o vídeo nunca para "
           "num título): cada um anunciado pela voz («Motivo número um: não há ninguém para quem voar») e feito de: o dado "
           "ou a regra com seu número, o mapa que o demonstra, a nuance «na prática…»; ligue cada motivo ao seguinte "
           "(«mas mesmo que…, esbarraria no segundo problema»); 4) o último motivo é uma história real com data exata; "
           "5) no meio, UMA frase: «Se você gosta de ver o mundo através de mapas como este, se inscreva»; 6) a virada «e "
           "mesmo assim, às vezes…»; 7) o fechamento repete os cinco motivos numa linha cada e volta à imagem do gancho. "
           "Português do Brasil. Cada dado verificável: marque [CONFERIR] o que não for seguro."),
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


ASK_KICKER = {"es": "¿Tú qué harías?", "pt": "E você, o que faria?", "en": "What would you do?", "fr": "Et vous, que feriez-vous ?",
              "it": "E tu cosa faresti?", "de": "Was würdest du tun?"}

REGION_WORD = re.compile(r"\b(regi[ãaoó]o?n?|norte|sul|sur|north|south|nordeste|noreste|northeast|sudeste|southeast|"
                         r"centro|center|central|oeste|west|leste|este|east|interior|litoral|costa|coast|amaz[ôo]nia|"
                         r"cerrado|estado|state|prov[ií]ncia|province)\b", re.I)


def _region_of(country: str, label: str) -> bool:
    """«Brazil» tinted with the label «REGIÃO NORTE» (atlas1pt 0:50): the whole country painted for a part of it. A
    label that is not one of the country's own names and speaks of a region → not a country highlight."""

    if not label.strip():
        return False
    names = {n.lower() for n in (places()["countries"].get(country) or {}).get("names", [])} | {country.lower()}
    return label.strip().lower() not in names and bool(REGION_WORD.search(label))


def clean(scene: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Only the vocabulary, numbers in range; a scene without a camera keeps the previous one."""

    prev_cam = (previous or {}).get("camera") or {"lat": 20.0, "lon": 0.0, "zoom": 1.0}
    cam = scene.get("camera") if isinstance(scene.get("camera"), dict) else {}
    point = _point(cam) if cam else None
    if point == (0.0, 0.0) and previous:        # «0, 0» is the model's blank, not the Gulf of Guinea: stay put
        point = None
    camera = {"lat": round(point[0], 4), "lon": round(point[1], 4), "zoom": round(_float(cam.get("zoom"), 1, 6, prev_cam["zoom"]), 2)} \
        if point else dict(prev_cam)
    # the whole globe most of the time (the reference never crops it under the chapter bar): up to 2, and closer only
    # for a line that names a city or a region (3.2 at most)
    named = bool(scene.get("points") or scene.get("tags"))
    if not named and previous and (previous.get("points") or previous.get("tags")) and \
            _angle((camera["lat"], camera["lon"]), (prev_cam["lat"], prev_cam["lon"])) < 4:
        named = True                        # still at the place the last line named: its close view stays
    # A globe between ~2.6 and ~4.4 is cut at the top and the bottom with paper at the sides: never. The whole globe
    # (up to 1.8, 2.6 when a place is named), or, for a region or a city the line names (the model asks 3+), a close
    # map that fills the screen (4.4-6: atlas1pt showed Serra do Mar, Salesópolis and Rio Paraná on one dot at 2.6).
    asked = camera["zoom"]
    camera["zoom"] = min(max(asked, REGION_ZOOM), 6.0) if named and asked >= 3 else min(asked, 2.6 if named else 1.8)
    view = str(scene.get("view") or "globe")
    out: dict[str, Any] = {"type": "atlas", "view": view if view in VIEWS else "globe",
                           "camera": camera, "dark": bool(scene.get("dark"))}
    out["tags"] = [{"text": _text(t.get("text"), 4, False, 26), "lat": _point(t)[0] if _point(t) else None,
                    "lon": _point(t)[1] if _point(t) else None, "at": _at(t.get("at"))}
                   for t in (scene.get("tags") or [])[:3] if isinstance(t, dict) and str(t.get("text") or "").strip()]
    points = [{"name": _text(p.get("name"), 3, True, 28), "lat": _point(p)[0], "lon": _point(p)[1], "at": _at(p.get("at"))}
              for p in (scene.get("points") or [])[:6] if isinstance(p, dict) and _point(p) and str(p.get("name") or "").strip()]
    # one dot per place: «MCMURDO» and «BASE MCMURDO» on the same spot are one (the last name wins)
    out["points"] = [p for i, p in enumerate(points)
                     if not any(_angle((p["lat"], p["lon"]), (q["lat"], q["lon"])) < SAME_SPOT for q in points[i + 1:])]
    # a bare small number («1», «3») says nothing on a map: a figure needs its unit, a year or a time
    out["tags"] = [t for t in out["tags"] if not re.fullmatch(r"\d", t["text"].strip())]
    routes = []
    for r in (scene.get("routes") or [])[:12]:
        if isinstance(r, dict) and _point(r.get("from")) and _point(r.get("to")):
            routes.append({"from": list(_point(r["from"])), "to": list(_point(r["to"])), "label": _text(r.get("label"), 3, False, 24),
                           "dashed": bool(r.get("dashed")), "style": "many" if r.get("style") == "many" else "main",
                           "mover": r.get("mover") if r.get("mover") in MOVERS else ("dot" if r.get("style") == "many" else ""),
                           "at": _at(r.get("at"))})
    out["routes"] = routes
    out["rings"] = [{"lat": _point(r)[0], "lon": _point(r)[1], "km": _float(r.get("km"), 50, 6000, 1000),
                     "label": _text(r.get("label"), 3, True, 24), "at": _at(r.get("at"))}
                    for r in (scene.get("rings") or [])[:6] if isinstance(r, dict) and _point(r)]
    band = scene.get("band") if isinstance(scene.get("band"), dict) else None
    out["band"] = {"country": str(band.get("country")).strip(), "km": _float(band.get("km"), 10, 1000, 100),
                   "at": _at(band.get("at"))} \
        if band and str(band.get("country") or "").strip() in places()["countries"] else None
    if out["band"] and str(band.get("label") or "").strip() and _point(band) and len(out["tags"]) < 3:
        out["tags"].append({"text": _text(band.get("label"), 4, False, 26), "lat": _point(band)[0], "lon": _point(band)[1],
                            "at": out["band"]["at"]})
    named_here = {p["name"] for p in out["points"]}
    for ring in out["rings"]:               # «CERRADO» twice on the same spot (atlas1pt 5:35): the dot keeps the name
        if ring["label"] in named_here:
            ring["label"] = ""
    out["tags"] = [t for t in out["tags"] if t["text"].upper() not in named_here]
    zone = scene.get("zone") if isinstance(scene.get("zone"), dict) else None
    out["zone"] = {"lat": _float(zone.get("lat"), -89, 89, -60), "label": _text(zone.get("label"), 4, False, 32),
                   "at": _at(zone.get("at"))} if zone and zone.get("lat") is not None else None
    out["highlight"] = [{"name": str(h.get("name")).strip(), "label": _text(h.get("label"), 3, True, 24),
                         "group": int(_float(h.get("group"), 0, 3, 0))}
                        for h in (scene.get("highlight") or [])[:12] if isinstance(h, dict) and str(h.get("name") or "").strip()
                        and not _region_of(str(h.get("name")), str(h.get("label") or ""))]
    for h in out["highlight"]:              # «COLÔMBIAÔMBIA» (atlas Darién 7:05): the country's label on a dot's name
        info = places()["countries"].get(h["name"]) or {}
        if h["label"] and (h["label"] in named_here or bool(info) and any(
                _angle((info["lat"], info["lon"]), (p["lat"], p["lon"])) < 4 for p in out["points"])):
            h["label"] = ""
    night = scene.get("night") if isinstance(scene.get("night"), dict) else None
    out["night"] = _night(night) if night and not night.get("off") else None
    out["nightOff"] = bool(night and night.get("off"))
    out["countries"] = [{"name": str(c.get("name")).strip(), "label": _text(c.get("label"), 3, True, 26), "at": _at(c.get("at"))}
                        for c in (scene.get("countries") or [])[:2]
                        if isinstance(c, dict) and str(c.get("name") or "").strip() in flag_codes()]
    meridians = scene.get("meridians") if isinstance(scene.get("meridians"), dict) else None
    out["meridians"] = {"step": int(_float(meridians.get("step"), 5, 45, 15)), "labels": bool(meridians.get("labels", True)),
                        "at": _at(meridians.get("at"))} if meridians else None
    card = scene.get("card") if isinstance(scene.get("card"), dict) else None
    if card and str(card.get("kind")) in CARDS and (card.get("title") or card.get("lines") or card.get("big")):
        long = card["kind"] == "choice"         # «¿Tú qué harías?»: the whole question
        out["card"] = {"kind": card["kind"], "big": _text(card.get("big"), 2, False, 14),
                       "title": _text(card.get("title"), 24 if long else 8, False, 140 if long else 60),
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
    if out["chart"] and out["chart"]["kind"] == "bars":
        # a bar of 0 is the model's blank for a figure the script never gives (atlas1pt 9:45: «Centro-Oeste 0 · média 0»)
        out["chart"]["bars"] = [b for b in out["chart"]["bars"] if b["value"]]
        if not out["chart"]["bars"]:
            out["chart"], out["view"] = None, "globe"
    if out["chart"] and out["chart"]["kind"] == "bars" and len(out["chart"]["bars"]) < 2:
        # one bar compares nothing: its figure counts up on the globe instead
        bar = out["chart"]["bars"][0]
        scene = {**scene, "counter": {"value": bar["value"], "unit": bar["unit"] or out["chart"]["unit"],
                                      "label": bar["label"] or out["chart"]["title"], "at": (scene.get("chart") or {}).get("at")}}
        out["chart"], out["view"] = None, "globe"
    icon = scene.get("icon") if isinstance(scene.get("icon"), dict) else None
    out["icon"] = {"name": icon["name"], "label": _text(icon.get("label"), 4, True, 28), "at": _at(icon.get("at"))} \
        if out["view"] == "icon" and icon and icon.get("name") in ICONS else None
    counter = scene.get("counter") if isinstance(scene.get("counter"), dict) else None
    out["counter"] = {"value": _float(counter.get("value"), -1e12, 1e12, 0), "unit": _text(counter.get("unit"), 2, False, 14),
                      "label": _text(counter.get("label"), 6, True, 40), "at": _at(counter.get("at"))} \
        if counter and _num(counter.get("value")) else None          # 0 counts nothing (atlas1pt 6:50: «0»)
    if out["night"] is not None:
        out["night"]["lights"] = bool((night or {}).get("lights", True))
    sat = scene.get("sat") if isinstance(scene.get("sat"), dict) else None
    out["sat"] = {"lat": _point(sat)[0], "lon": _point(sat)[1], "zoom": int(_float(sat.get("zoom"), 8, 13, 11)),
                  "label": _text(sat.get("label"), 4, True, 30), "at": _at(sat.get("at"))} \
        if out["view"] == "sat" and sat and _point(sat) else None
    flat = scene.get("flat") if isinstance(scene.get("flat"), dict) else None
    out["flat"] = {"from": list(_point(flat.get("from"))), "to": list(_point(flat.get("to"))),
                   "straight": _text(flat.get("straight"), 5, True, 36), "curve": _text(flat.get("curve"), 5, True, 36),
                   "at": _at(flat.get("at"))} \
        if out["view"] == "flat" and flat and _point(flat.get("from")) and _point(flat.get("to")) else None
    size = scene.get("size") if isinstance(scene.get("size"), dict) else None
    out["size"] = {"country": str(size.get("country")).strip(), "to": list(_point(size.get("to"))),
                   "compare": str(size.get("compare") or "").strip(), "label": _text(size.get("label"), 6, True, 40),
                   "at": _at(size.get("at"))} \
        if out["view"] == "size" and size and str(size.get("country") or "").strip() and _point(size.get("to")) else None
    if out["view"] == "chart" and not out["chart"] or out["view"] == "icon" and not out["icon"] \
            or out["view"] in ("sat", "flat", "size") and not out[out["view"]]:
        out["view"] = "globe"                     # nothing valid to show instead: the globe stays
    lens = scene.get("lens") if isinstance(scene.get("lens"), dict) else None
    out["lens"] = {"lat": _point(lens)[0], "lon": _point(lens)[1], "zoom": round(_float(lens.get("zoom"), 4, 10, 6), 2),
                   "label": _text(lens.get("label"), 4, True, 30), "at": _at(lens.get("at"))} \
        if out["view"] == "globe" and lens and _point(lens) else None
    if out["view"] == "sat" and not has_photo(out["sat"]["lat"]):    # nothing to see there (atlas2pt: McMurdo)
        out["points"] = [*out["points"], {"name": out["sat"]["label"], "lat": out["sat"]["lat"], "lon": out["sat"]["lon"],
                                          "at": out["sat"]["at"]}][-6:] if out["sat"]["label"] else out["points"]
        out["view"], out["sat"] = "globe", None
    if out["view"] == "sat":                  # the globe dives to the place: the camera ends there
        out["camera"] = {"lat": out["sat"]["lat"], "lon": out["sat"]["lon"], "zoom": 3.2}
    return out


def subsolar(when_utc: Any) -> tuple[float, float]:
    """Where the sun is overhead at a UTC moment (lat, lon), NOAA's approximation (within a few arc-minutes): the
    centre of the lit hemisphere; the night is everything more than 90° from it."""

    day = when_utc.timetuple().tm_yday
    hours = when_utc.hour + when_utc.minute / 60 + when_utc.second / 3600
    g = 2 * math.pi / 365 * (day - 1 + (hours - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eot = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                    - 0.040849 * math.sin(2 * g))                       # minutes
    lon = -15 * (hours - 12 + eot / 60)
    lon = (lon + 180) % 360 - 180
    return round(math.degrees(decl), 3), round(lon, 3)


def _night(night: dict[str, Any]) -> dict[str, Any] | None:
    """{"date", "from", "to", "tz"} → the sun's position at both moments (the terminator sweeps between them)."""

    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    try:
        zone = ZoneInfo(str(night.get("tz") or "Europe/Madrid"))
        day = datetime.strptime(str(night.get("date") or "2026-06-21")[:10], "%Y-%m-%d")
    except Exception:
        return None

    def at(clock: Any) -> Any:
        try:
            h, m = (int(x) for x in str(clock).split(":")[:2])
        except (TypeError, ValueError):
            return None
        return day.replace(hour=h % 24, minute=m % 60, tzinfo=zone).astimezone(timezone.utc)

    start = at(night.get("from") or night.get("time") or "21:00")
    if start is None:
        return None
    end = at(night.get("to")) or start
    return {"from": subsolar(start), "to": subsolar(end), "clock": [start.astimezone(zone).strftime("%H:%M"),
            end.astimezone(zone).strftime("%H:%M")], "at": _at(night.get("at")),
            "spec": [str(night.get("date")), str(night.get("from") or night.get("time")), str(night.get("to")), str(night.get("tz"))]}


_FLAGS: dict[str, str] | None = None


def flag_codes() -> dict[str, str]:
    """Natural Earth country name → the ISO code of its flag (assets/flags/countries.json, flag-icons, MIT)."""

    global _FLAGS
    if _FLAGS is None:
        try:
            _FLAGS = json.loads((Path(__file__).resolve().parents[1] / "assets" / "flags" / "countries.json").read_text("utf-8"))
        except (OSError, ValueError):
            _FLAGS = {}
    return _FLAGS


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


REST = re.compile(r"^(resto|restante|demais|outros|outras|otros|otras|rest|others|other|the rest|el resto|o resto)\b", re.I)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _said_numbers(text: str) -> set[float]:
    """The figures written in digits in a text («41,8 %», «1.845 m», «2.500») as numbers, both ways of reading a
    separator (1.845 is 1845 in Portuguese and 1.845 in English)."""

    out: set[float] = set()
    for raw in _NUMBER.findall(text):
        for candidate in (raw.replace(".", "").replace(",", "."), raw.replace(",", ""), raw.replace(",", ".")):
            try:
                out.add(round(float(candidate), 3))
            except ValueError:
                pass
    return out


def check_chart(scene: dict[str, Any], text: str) -> dict[str, Any]:
    """A bar chart only with what the script says: when the lines around write their figures in digits, a bar whose
    value is not among them goes (the model made it up); bars of a whole («Sudeste 41,8 % / Resto 55,2 %», atlas1pt)
    add up to 100, the «rest» bar recomputed; fewer than two bars left: no chart (one figure becomes a counter)."""

    chart = scene.get("chart")
    if not chart or chart.get("kind") != "bars":
        return scene
    bars = [dict(b) for b in chart["bars"]]
    said = _said_numbers(text)
    if said:
        bars = [b for b in bars if REST.match(b["label"] or "") or round(float(b["value"]), 3) in said]
    units = {(b["unit"] or chart["unit"] or "").strip() for b in bars}
    rest = [b for b in bars if REST.match(b["label"] or "")]
    if units == {"%"} and len(rest) == 1:
        others = sum(float(b["value"]) for b in bars if b is not rest[0])
        if 0 < others < 100:
            rest[0]["value"] = round(100 - others, 1)
        else:
            bars.remove(rest[0])
    if len(bars) >= 2:
        return {**scene, "chart": {**chart, "bars": bars}}
    out = {**scene, "chart": None, "view": "globe"}
    if bars and not scene.get("counter"):
        out["counter"] = {"value": bars[0]["value"], "unit": bars[0]["unit"] or chart["unit"],
                          "label": bars[0]["label"] or chart["title"], "at": ""}
    return out


def _xyz(lat: float, lon: float) -> tuple[float, float, float]:
    a, b = math.radians(lat), math.radians(lon)
    return math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)


def _angle(p: tuple[float, float], q: tuple[float, float]) -> float:
    x = sum(i * j for i, j in zip(_xyz(*p), _xyz(*q)))
    return math.degrees(math.acos(max(-1.0, min(1.0, x))))


def fit_camera(scene: dict[str, Any]) -> dict[str, Any]:
    """Everything drawn on the visible side of the globe: when a point, a route's end or its middle, or a ring's
    centre is more than 65° from where the camera looks, the camera moves to their mean and pulls out to fit them."""

    marks: list[tuple[float, float]] = [(p["lat"], p["lon"]) for p in scene.get("points") or []]
    for r in scene.get("routes") or []:
        a, b = tuple(r["from"]), tuple(r["to"])
        marks += [a, b]
        va, vb = _xyz(*a), _xyz(*b)
        mid = [x + y for x, y in zip(va, vb)]
        norm = math.sqrt(sum(m * m for m in mid))
        if norm > 1e-6:
            marks.append((math.degrees(math.asin(mid[2] / norm)), math.degrees(math.atan2(mid[1], mid[0]))))
    marks += [(r["lat"], r["lon"]) for r in scene.get("rings") or []]
    if scene.get("zone"):
        marks.append((-90.0 if scene["zone"]["lat"] < 0 else 90.0, 0.0))
    if not marks:
        return scene
    cam = scene["camera"]
    centre = (cam["lat"], cam["lon"])
    if cam["zoom"] >= REGION_ZOOM and len(marks) > 1:
        # a close map: centred on what it draws, as close as their spread allows (São Paulo, Santos and Salesópolis,
        # 80 km apart, are one dot at 4.4 and three at ~8)
        total = [sum(_xyz(*m)[i] for m in marks) for i in range(3)]
        norm = math.sqrt(sum(t * t for t in total)) or 1.0
        middle = (math.degrees(math.asin(total[2] / norm)), math.degrees(math.atan2(total[1], total[0])))
        spread = max(_angle(middle, m) for m in marks)
        if spread > REGION_SPAN:              # too far apart for a close map: the globe
            return fit_camera({**scene, "camera": {**cam, "zoom": 2.6}})
        zoom = 1 + math.log(CLOSE_PX / math.sin(math.radians(max(spread, 0.3))) / 350) / math.log(1.42)
        return {**scene, "camera": {"lat": round(middle[0], 4), "lon": round(middle[1], 4),
                                    "zoom": round(min(MAX_CLOSE, max(REGION_ZOOM, zoom)), 2)}}
    if max(_angle(centre, m) for m in marks) <= 65:
        return scene
    total = [sum(_xyz(*m)[i] for m in marks) for i in range(3)]
    norm = math.sqrt(sum(t * t for t in total))
    if norm < 1e-6:
        return scene
    lat, lon = math.degrees(math.asin(total[2] / norm)), math.degrees(math.atan2(total[1], total[0]))
    spread = max(_angle((lat, lon), m) for m in marks)
    zoom = 1.0 if spread > 55 else 1.3 if spread > 40 else 1.7 if spread > 25 else cam["zoom"]
    return {**scene, "camera": {"lat": round(lat, 4), "lon": round(lon, 4), "zoom": min(cam["zoom"], zoom)}}


LIMITS = {"points": 8, "routes": 12, "rings": 6}
SAME_SPOT = 0.3       # degrees (~30 km): two names this close are one place, one dot
REGION_ZOOM = 4.4     # the smallest close view: the globe fills the whole screen
REGION_SPAN = 14      # degrees from the camera a close view shows of what it draws; farther → back to the whole globe
MAX_CLOSE = 9.0       # the closest map (Remotion: radius 350·1.42^(zoom-1) px → ~1° = 100 px)
CLOSE_PX = 330        # on a close map, the farthest place this many px from the centre


def _same_place(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _angle((a["lat"], a["lon"]), (b["lat"], b["lon"])) < 4 and abs(a["zoom"] - b["zoom"]) < 0.3


def _key(kind: str, item: dict[str, Any]) -> Any:
    if kind == "points":
        return item.get("name")
    if kind == "routes":
        return (tuple(round(x) for x in item["from"]), tuple(round(x) for x in item["to"]))
    return (round(item["lat"]), round(item["lon"]))


def carry(scene: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """A line that stays where the last one was (about the same camera) keeps what is already drawn there, and adds its
    own on top: the dots, routes and rings pile up instead of vanishing and coming back at each cut (the LLM rarely
    repeats them). The zone and the night stay too. A new place starts clean."""

    scene = carry_night(scene, previous)
    # a camera drifting on a quiet stretch (drift()) is still at the place its lines asked for («ask»)
    if not previous or scene.get("view") != "globe" or previous.get("view") != "globe" \
            or not _same_place(scene["camera"], previous.get("ask") or previous["camera"]):
        return scene
    out = dict(scene)
    out["camera"] = dict(previous["camera"])            # the same place: no tiny turn of the globe between lines
    for kind, limit in LIMITS.items():
        new = list(scene.get(kind) or [])
        seen = {_key(kind, x) for x in new}
        kept = [{**x, "at": "", "kept": True} for x in previous.get(kind) or [] if _key(kind, x) not in seen
                and not (kind == "points" and any(_angle((x["lat"], x["lon"]), (p["lat"], p["lon"])) < SAME_SPOT for p in new))]
        out[kind] = (kept + new)[-limit:]
    for name in ("zone", "meridians", "band"):
        if not scene.get(name) and previous.get(name):
            out[name] = {**previous[name], "at": "", "kept": True}
    if not scene.get("highlight") and previous.get("highlight"):
        out["highlight"] = previous["highlight"]
    return out


TRIP_JOIN = 3.0       # degrees: a route that starts this close to where another ended continues the same trip
TRIP_NEAR = 60.0      # degrees from the camera: the trip so far stays drawn while the globe looks at its part of the world
TRIP_LEGS = 10        # the last legs kept


class Journey:
    """A trip told leg by leg (driving from Brazil to the United States): each route that starts where an earlier one
    ended joins the trip, and from then on every globe view near it keeps the whole road travelled so far drawn —
    instead of each leg vanishing when the camera moves on to the next place (carry() only keeps what stays put)."""

    def __init__(self) -> None:
        self.ends: list[dict[str, Any]] = []         # every route drawn so far (a trip can start from any of them)
        self.legs: list[dict[str, Any]] = []

    @staticmethod
    def _plain(route: dict[str, Any]) -> dict[str, Any]:
        return {"from": list(route["from"]), "to": list(route["to"]), "label": "", "dashed": bool(route.get("dashed")),
                "style": "main", "at": "", "kept": True, "trail": True}

    def add(self, scene: dict[str, Any]) -> dict[str, Any]:
        if scene.get("view") != "globe":
            return scene
        for route in scene.get("routes") or []:
            if route.get("kept") or route.get("style") == "many":
                continue
            joins = lambda r: _angle(tuple(route["from"]), tuple(r["to"])) < TRIP_JOIN   # noqa: E731
            if self.legs and joins(self.legs[-1]):
                self.legs.append(route)
            elif (earlier := next((r for r in reversed(self.ends) if joins(r)), None)) is not None:
                self.legs = [earlier, route]           # the first leg is known once the second starts at its end
            self.ends.append(route)
        self.legs = self.legs[-TRIP_LEGS:]
        if len(self.legs) < 2:
            return scene
        cam = scene["camera"]
        if not any(_angle((cam["lat"], cam["lon"]), tuple(x)) < TRIP_NEAR for leg in self.legs for x in (leg["from"], leg["to"])):
            return scene
        own = list(scene.get("routes") or [])
        have = {_key("routes", r) for r in own}
        behind = [self._plain(leg) for leg in self.legs if _key("routes", leg) not in have]
        return {**scene, "routes": (behind + own)[-max(LIMITS["routes"], len(own)):]} if behind else scene


NIGHT_LINES = 10      # how many lines a night stays on its own


def carry_night(scene: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """The night is not redrawn line by line (it came and went every 2-3 s, its sun jumping back to the first hour):
    once on, it stays — the sun where the last line left it — while the camera stays within 50° of it, for up to
    NIGHT_LINES lines, until a line sets another night or switches it off ("night": {"off": true})."""

    if scene.get("nightOff") or not previous or not previous.get("night"):
        return scene
    if scene.get("night") and scene["night"].get("spec") != previous["night"].get("spec"):
        return scene                              # another night: it starts its own sweep
    # (the same night written again by the LLM continues where it was, instead of sweeping again from the start)
    if scene.get("view") not in ("globe", "sat") or previous.get("view") not in ("globe", "sat"):
        return scene
    night = previous["night"]
    streak = int(night.get("streak", 0)) + 1
    cam, before = scene["camera"], previous["camera"]
    if streak > NIGHT_LINES or _angle((cam["lat"], cam["lon"]), (before["lat"], before["lon"])) > 50:
        return scene
    return {**scene, "night": {**night, "from": night["to"], "clock": [night["clock"][1], night["clock"][1]],
                               "at": "", "kept": True, "streak": streak}}


FIGURE = re.compile(r"\b(\d{1,2}[:.]\d{2}|1[5-9]\d{2}|20\d{2}|\d+(?:[.,]\d+)?\s?(?:%|km|kilómetros|kilometres|miles|millas|"
                    r"grados|degrees|°|minutos|minutes|horas|hours|metros|metres|meters|m\b))", re.I)


def auto_tag(scene: dict[str, Any], text: str, previous: dict[str, Any] | None) -> dict[str, Any]:
    """A line that draws nothing new but says a figure («14:42», «30 grados», «1940»): that figure as a paper tag, by the
    last place named (or the middle of the globe), at its word — never a globe with nothing new on it."""

    if scene.get("view") != "globe":
        return scene
    new = [k for k in ("points", "routes", "rings", "tags") if any(not x.get("kept") for x in scene.get(k) or [])]
    if new or any(scene.get(k) and not scene[k].get("kept") for k in ("card", "stamp", "headline", "zone", "night", "meridians", "counter")):
        return scene
    found = FIGURE.search(text)
    if not found:
        return scene
    figure = found.group(1)
    points = [p for p in scene.get("points") or [] if p.get("lat") is not None]
    said = text.casefold()
    # the place the line names, else the last one drawn
    place = next((p for p in points if str(p.get("name") or "").casefold() in said), points[-1] if points else None)
    first = figure.split()[0]
    return {**scene, "tags": [{"text": figure, "lat": place["lat"] if place else None, "lon": place["lon"] if place else None,
                               "at": first}]}


PHOTO_LATS = (-60.0, 75.0)    # Sentinel-2 cloudless has no picture south of here (Antarctica's tiles are blank) or north


def has_photo(lat: float) -> bool:
    return PHOTO_LATS[0] <= lat <= PHOTO_LATS[1]


def ensure_satellites(scenes: dict[str, dict[str, Any]], wanted: int = 2) -> None:
    """The dive to the real satellite photo is the format's strongest moment: when the LLM chose none, the lines that
    name exactly one new place (not in the hook's first lines, at least 8 lines apart) become dives, `wanted` of them
    (visual.satellites, 2)."""

    ids = list(scenes)
    have = [n for n, i in enumerate(ids) if scenes[i].get("view") == "sat"]
    wanted -= len(have)
    if wanted <= 0:
        return
    chosen: list[int] = []
    for n, shot_id in enumerate(ids):
        g = scenes[shot_id]
        new = [p for p in g.get("points") or [] if not p.get("kept") and has_photo(p["lat"])]
        if n < 3 or g.get("view") != "globe" or len(new) != 1 or (g.get("card") and not g["card"].get("kept")) \
                or (g.get("night") and not g["night"].get("kept")):
            continue
        if any(abs(n - m) < 8 for m in chosen + have):
            continue
        if "moment" in g and n and scenes[ids[n - 1]].get("moment") == g["moment"]:
            continue                    # a dive opens a moment, never cuts one in the middle
        chosen.append(n)
    if len(chosen) > wanted:                       # spread over the video
        step = len(chosen) / wanted
        chosen = [chosen[int(k * step)] for k in range(wanted)]
    for n in chosen:
        g = scenes[ids[n]]
        place = next(p for p in g["points"] if not p.get("kept") and has_photo(p["lat"]))
        g["view"] = "sat"
        g["sat"] = {"lat": place["lat"], "lon": place["lon"], "zoom": 11, "label": place["name"], "at": place.get("at", "")}
        g["camera"] = {"lat": place["lat"], "lon": place["lon"], "zoom": 3.2}


NEW_FIELDS = ("card", "stamp", "headline", "counter", "chart", "icon", "sat", "flat", "size", "band")


def stale(scene: dict[str, Any], previous: dict[str, Any] | None, asked: dict[str, Any] | None = None) -> bool:
    """The line adds nothing to the screen: the same place, every dot, route, ring and tag kept from before, no card,
    stamp, counter… of its own, the same night and countries (atlas1pt: 16-36 s of the same globe)."""

    if not previous or scene.get("view") != "globe" or previous.get("view") != "globe":
        return False
    # where the line asked to look (before carry put it on the drifting camera) against where the last one asked
    if not _same_place(asked or scene["camera"], previous.get("ask") or previous["camera"]):
        return False
    for kind in ("points", "routes", "rings", "tags", "countries"):
        if any(not x.get("kept") for x in scene.get(kind) or []):
            return False
    if any(scene.get(name) and not scene[name].get("kept") for name in NEW_FIELDS):
        return False
    if (scene.get("night") and not scene["night"].get("kept")) or scene.get("highlight") != previous.get("highlight"):
        return False
    return True


DRIFT = (0.5, 1.0, 0.5, 0.0, -0.5, -1.0, -0.5, 0.0)    # of the step: a slow back-and-forth
DRIFT_PX = 110        # how far the picture slides at the widest step (60 read as still on a pale ocean)
DRIFT_MAX = 14.0      # degrees, the whole globe (110 px there is ~14°)


def drift(anchor: dict[str, Any], run: int) -> dict[str, Any]:
    """The camera for the run-th line in a row with nothing new: it slides ~DRIFT_PX east and back and breathes in and
    out (zoom 0.2 lower every other line, never closer than the line asked). The scene keeps `anchor` (the camera its
    lines ask for) as «ask», so the next line is still «the same place» (carry) and keeps what is drawn."""

    radius = 350 * 1.42 ** (anchor["zoom"] - 1)
    step = min(DRIFT_MAX, math.degrees(math.asin(min(1.0, DRIFT_PX / radius))))
    # degrees on the globe, east: near a pole a degree of longitude is much shorter (McMurdo, 78° S)
    shift = step * DRIFT[(run - 1) % len(DRIFT)] / max(0.25, math.cos(math.radians(anchor["lat"])))
    return {"lat": anchor["lat"], "lon": round((anchor["lon"] + shift + 180) % 360 - 180, 4),
            "zoom": round(anchor["zoom"] - (0.2 if run % 2 else 0.0), 2)}


MOMENT_SYSTEM = """
Divides el guion de un vídeo de mapas explicados en MOMENTOS. Un momento es UNA idea contada en UN sitio del mapa:
normalmente 2-5 frases seguidas (a veces 1, rara vez más de 6). Mientras dura un momento la imagen se queda en el mismo
sitio y se le van añadiendo cosas; el momento cambia cuando el guion cambia de lugar, de tema, o pasa a un dato que
pide otra imagen (una cifra que se compara, una fecha con su historia). Nunca cortes una explicación a medias.
Devuelve SOLO JSON: {"starts": [1, 4, 9, ...]} con el número de la primera frase de cada momento (siempre empieza en 1).
""".strip()

REFILL_SYSTEM = """
AHORA SOLO RELLENAS. Estas frases del vídeo no añaden nada al mapa: el globo se queda quieto mientras la voz habla, y eso
aburre. Para CADA frase devuelve una escena con 1-2 elementos NUEVOS que enseñen lo que dice esa frase (un punto con su
nombre, una ruta, un círculo de alcance, una etiqueta "tags" con la cifra que dice, una tarjeta, un contador, un país
en "highlight", una lupa "lens"…), con coordenadas REALES y "at" = una palabra literal de la frase. La cámara NO cambia
(te la doy: no la devuelvas) y no repitas lo que ya está dibujado. Si una frase de verdad no da para nada, devuélvela
sin elementos.
""".strip()

BATCH = 25            # lines per request to the model
MIN_BATCH = 6         # a failed batch is split in halves down to this
ICON_EVERY = 8        # lines between two full-screen drawings
STAMP_EVERY = 10      # lines between two stamps
QUIET_SECONDS = 6.0   # this long with nothing new on the globe: the plan check asks the model to fill it


# --- places the script names, recognised without the model ----------------------------------------------------------

_PLACES: dict[str, Any] = {}
CITY_STOP = {"Natal", "Victoria", "Esperanza", "Concepción", "Rosario", "Mercedes", "Trinidad", "Valencia", "Florida",
             "Granada", "Córdoba", "Santa", "Salvador", "Paz", "Asunción", "Belo", "Campo", "Grande", "Nova", "Nuevo",
             "Bello", "Victória", "Vitória", "Esperança", "Luz", "Mar", "Sol", "Alto", "Real", "Monte", "Santos"}


# country names that are mostly something else in a script: Salvador (Bahia) drew El Salvador's flag (atlas1pt 2:35),
# Jordan Chiles drew Jordan; Georgia the US state, Granada the Spanish city, Chad a first name
COUNTRY_STOP = {"Salvador", "Jordan", "Chad", "Georgia", "Geórgia", "Granada", "Niger", "Jersey"}


def places() -> dict[str, Any]:
    """assets/geo/places.json (scripts/build_places.py): countries with their names in six languages, big cities."""

    if not _PLACES:
        path = Path(__file__).resolve().parent.parent / "assets" / "geo" / "places.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            data = {"countries": {}, "cities": []}
        country_of = {}
        for key_name, info in data["countries"].items():
            for name in info["names"]:
                if len(name) >= 4 and name not in COUNTRY_STOP:
                    country_of.setdefault(name, key_name)
        city_of = {c[0]: c for c in data["cities"] if len(c[0]) >= 4 and c[0] not in CITY_STOP and c[0] not in country_of}

        def pattern(names: Any) -> re.Pattern[str] | None:
            names = sorted(names, key=len, reverse=True)
            return re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in names) + r")(?![\w])") if names else None

        _PLACES.update({"countries": data["countries"], "country_of": country_of, "city_of": city_of,
                        "country_re": pattern(country_of), "city_re": pattern(city_of)})
    return _PLACES


def auto_places(scene: dict[str, Any], text: str, seen: set[str]) -> dict[str, Any]:
    """A country or a big city the line names that the model did not draw: the country tinted (its flag card the
    first time in the video), the city as a dot. Only on the globe; at most two cities a line."""

    if scene.get("view") != "globe" or not text:
        return scene
    data = places()
    out = dict(scene)
    tinted = {h["name"] for h in out.get("highlight") or []}
    flagged = {c["name"] for c in out.get("countries") or []}
    if data["country_re"] is not None:
        for match in data["country_re"].finditer(text):
            name = data["country_of"][match.group(1)]
            if name not in tinted:
                out["highlight"] = [*(out.get("highlight") or []), {"name": name, "label": "", "group": 0}]
                tinted.add(name)
            if name not in seen and name not in flagged and len(out.get("countries") or []) < 2 and name in flag_codes():
                out["countries"] = [*(out.get("countries") or []),
                                    {"name": name, "label": match.group(1).upper()[:26], "at": match.group(1)}]
                flagged.add(name)
            seen.add(name)
    if data["city_re"] is not None:
        added = 0
        for match in data["city_re"].finditer(text):
            name, lat, lon, _ = data["city_of"][match.group(1)]
            if added >= 2 or any(_angle((lat, lon), (p["lat"], p["lon"])) < 0.5 for p in out.get("points") or []):
                continue
            out["points"] = [*(out.get("points") or []), {"name": name.upper()[:28], "lat": lat, "lon": lon,
                                                          "at": match.group(1), "auto": True}][-6:]
            added += 1
    return out


def sentences(todo: list[tuple[Any, int, int]], max_shots: int = 6) -> list[dict[str, Any]]:
    """The voice's sentences: consecutive planner shots joined up to a full stop (a planner shot is ~3 s, often half a
    sentence: one atlas scene per shot changed the picture in the middle of an explanation). A chapter heading stands
    alone; a gap in the frames or `max_shots` shots also close a sentence."""

    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for shot, a, b in todo:
        if shot.type == "chapter":
            if current:
                out.append(current)
                current = None
            out.append({"chapter": shot, "from": a, "to": b})
            continue
        if current and current["to"] != a:
            out.append(current)
            current = None
        text = " ".join(str(shot.text or "").split())
        if current is None:
            current = {"id": shot.id, "shots": [shot], "from": a, "to": b, "text": text}
        else:
            current["shots"].append(shot)
            current["to"] = b
            current["text"] = f"{current['text']} {text}".strip()
        if END.search(text) or len(current["shots"]) >= max_shots:
            out.append(current)
            current = None
    if current:
        out.append(current)
    return out


END = re.compile(r"[.!?…][\"'»”)\]]*$")


def moment_camera(members: list[dict[str, Any]]) -> dict[str, Any]:
    """One camera for a whole moment: where its first line looks, as close as any of its lines asked, fitted so
    everything the moment draws is on screen (fit_camera)."""

    base = dict(members[0]["camera"])
    base["zoom"] = max(m["camera"]["zoom"] for m in members)
    union: dict[str, Any] = {"camera": base, "points": [], "routes": [], "rings": [], "zone": None}
    for m in members:
        for kind in ("points", "routes", "rings"):
            union[kind] += [x for x in m.get(kind) or [] if not x.get("kept")]
        union["zone"] = union["zone"] or m.get("zone")
    # a story in a small place (Yaviza and Turbo, 100 km apart: atlas Darién spent 2:40 on the whole globe with two
    # tiny names) goes close even when the model asked for the globe: what it draws all sits within a few degrees
    spots = _spots(union)
    if base["zoom"] < REGION_ZOOM and len(spots) >= 2 and not union["zone"]:
        total = [sum(_xyz(*m)[i] for m in spots) for i in range(3)]
        norm = math.sqrt(sum(t * t for t in total)) or 1.0
        middle = (math.degrees(math.asin(total[2] / norm)), math.degrees(math.atan2(total[1], total[0])))
        if max(_angle(middle, m) for m in spots) <= SMALL_PLACE:
            union["camera"] = {"lat": middle[0], "lon": middle[1], "zoom": REGION_ZOOM}
    return fit_camera(union)["camera"]


SMALL_PLACE = 6.0      # degrees: a moment drawing only within this of its middle is shown on a close map
MOMENT_FAR = 25.0      # degrees: a line drawing only this far from what its moment drew so far starts a new one


def _spots(scene: dict[str, Any]) -> list[tuple[float, float]]:
    out = [(p["lat"], p["lon"]) for p in scene.get("points") or []]
    out += [tuple(x) for r in scene.get("routes") or [] for x in (r["from"], r["to"])]
    out += [(r["lat"], r["lon"]) for r in scene.get("rings") or []]
    out += [(t["lat"], t["lon"]) for t in scene.get("tags") or [] if t.get("lat") is not None]
    return out


def split_far(cleaned: list[dict[str, Any]], starts: list[int]) -> list[int]:
    """A moment from the model that jumps across the world (atlas1pt 4:00: the Tietê and, two lines later, the
    Mississippi in one moment) had one camera for both: the whole globe, the Tietê a dot. It is cut where a line draws
    only things more than MOMENT_FAR from everything its moment drew before."""

    out = set(starts)
    bounds = [*sorted(starts), len(cleaned) + 1]
    for a, b in zip(bounds, bounds[1:]):
        drawn: list[tuple[float, float]] = []
        for n in range(a, b):
            scene = cleaned[n - 1]
            spots = _spots(scene) if scene.get("view") == "globe" else []
            if drawn and spots and all(min(_angle(s, d) for d in drawn) > MOMENT_FAR for s in spots):
                out.add(n)
                drawn = []
            drawn += spots
    return sorted(out)


def heuristic_starts(cleaned: list[dict[str, Any]]) -> list[int]:
    """Without the model's moments: a new one where a line looks at another place or shows something else."""

    starts = [1]
    for n in range(2, len(cleaned) + 1):
        a, b = cleaned[n - 2], cleaned[n - 1]
        if a.get("view") != b.get("view") or not _same_place(a["camera"], b["camera"]):
            starts.append(n)
    return starts


def _new_things(scene: dict[str, Any]) -> int:
    count = sum(1 for k in ("points", "routes", "rings", "tags", "countries") for x in scene.get(k) or [] if not x.get("kept"))
    return count + sum(1 for k in (*NEW_FIELDS, "lens") if scene.get(k) and not scene[k].get("kept"))


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    """The scene of every line (a sentence of the voice): the model draws each one, then (1) the lines are grouped into
    moments (one idea in one place) that share one camera, so the picture never changes in the middle of an
    explanation; (2) countries and cities the line names that the model left out are added; (3) the plan is checked
    for stretches with nothing new (QUIET_SECONDS) and the model is asked to fill those lines."""

    from .llm import complete_json

    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    seconds = [float(getattr(s, "seconds", 3.0) or 3.0) for s in shots]
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

    def ask(start: int, batch: list[tuple[str, str]]) -> None:
        """One batch of lines; a batch that fails (a cut or broken JSON) is asked again in halves, down to
        MIN_BATCH lines: atlas1pt lost its first 40 lines (1:49 of an empty globe) to one failed answer."""

        user = (f"EL GUION ENTERO:\n{story}\n\n" if len(lines) > len(batch) else "") + \
            f"FRASES {start + 1}-{start + len(batch)}:\n" + \
            "\n".join(f"[{start + n}] {text}" for n, (_, text) in enumerate(batch, 1))
        try:
            result = complete_json(ctx, stage="atlas", section="planner", system=system, user=user, max_tokens=550 * len(batch))
            got = {int(s.get("n", 0)): s for s in (result.get("scenes") or []) if isinstance(s, dict)}
            if len([n for n in got if start < n <= start + len(batch)]) < len(batch) // 2:
                raise ValueError(f"solo {len(got)} escenas de {len(batch)}")
            found.update(got)
        except Exception as error:
            if len(batch) <= MIN_BATCH:
                print(f"   Atlas: sin escenas de la IA para las frases {start + 1}-{start + len(batch)} ({str(error)[:100]})")
                return
            half = len(batch) // 2
            print(f"   Atlas: la IA falló en las frases {start + 1}-{start + len(batch)}; las pido en dos mitades")
            ask(start, batch[:half])
            ask(start + half, batch[half:])

    for start in range(0, len(lines), BATCH):
        ask(start, lines[start:start + BATCH])

    # 1. every line cleaned, with the places it names
    cleaned: list[dict[str, Any]] = []
    previous = None
    last_icon = last_stamp = -99
    seen: set[str] = set()
    for n, (_, text) in enumerate(lines, 1):
        raw = found.get(n) or {}
        if raw.get("view") == "icon":           # a drawing alone now and then, never a slideshow of drawings
            if n - last_icon < ICON_EVERY:
                raw = {**raw, "view": "globe", "icon": None}
            else:
                last_icon = n
        if isinstance(raw.get("stamp"), dict):
            if n - last_stamp < STAMP_EVERY:
                raw = {**raw, "stamp": None}
            else:
                last_stamp = n
        around = " ".join(t for _, t in lines[max(0, n - 3):n])
        scene = auto_places(check_chart(clean(raw, previous), around), text, seen)
        cleaned.append(scene)
        previous = scene

    # 2. moments: one camera for each
    try:
        result = complete_json(ctx, stage="atlas", section="planner", system=MOMENT_SYSTEM, user=story, max_tokens=1500)
        starts = sorted({int(x) for x in (result.get("starts") or []) if 1 <= int(x) <= len(lines)} | {1})
    except Exception as error:
        print(f"   Atlas: momentos por sitio (la IA no los dio: {str(error)[:80]})")
        starts = heuristic_starts(cleaned)
    starts = split_far(cleaned, starts)
    bounds = [*starts, len(lines) + 1]
    for m, (a, b) in enumerate(zip(bounds, bounds[1:])):
        members = [cleaned[i - 1] for i in range(a, b) if cleaned[i - 1]["view"] == "globe"]
        camera = moment_camera(members) if members else None
        for i in range(a, b):
            cleaned[i - 1]["moment"] = m
            if camera and cleaned[i - 1]["view"] == "globe":
                cleaned[i - 1]["camera"] = dict(camera)

    def build() -> list[dict[str, Any]]:
        out, before = [], None
        trip = Journey()
        for n, scene in enumerate(cleaned, 1):
            done = auto_tag(carry(fit_camera(scene) if scene["view"] != "globe" else scene, before), lines[n - 1][1], before)
            done = trip.add(done)
            out.append(done)
            before = done
        return out

    built = build()

    # 3. the plan checked before the render: stretches with nothing new are filled
    quiet: list[int] = []
    run: list[int] = []
    for n, scene in enumerate(built, 1):
        if n > 1 and scene["view"] == "globe" and built[n - 2]["view"] == "globe" and _new_things(cleaned[n - 1]) == 0 \
                and _new_things(scene) == 0:
            run.append(n)
            continue
        if sum(seconds[i - 1] for i in run) >= QUIET_SECONDS:
            quiet += run
        run = []
    if sum(seconds[i - 1] for i in run) >= QUIET_SECONDS:
        quiet += run
    if quiet:
        quiet_seconds = sum(seconds[i - 1] for i in quiet)
        ask_lines = []
        for n in quiet[:40]:
            scene = built[n - 1]
            cam = scene["camera"]
            drawn = ", ".join([p["name"] for p in scene.get("points") or []][:6]) or "nada"
            ask_lines.append(f"[{n}] {lines[n - 1][1]}\n    cámara {cam['lat']:.1f}, {cam['lon']:.1f}, zoom {cam['zoom']} · ya dibujado: {drawn}")
        filled = 0
        try:
            result = complete_json(ctx, stage="atlas", section="planner", system=system + "\n\n" + REFILL_SYSTEM,
                                   user="FRASES SIN NADA NUEVO:\n" + "\n".join(ask_lines), max_tokens=400 * len(ask_lines))
            for extra in result.get("scenes") or []:
                n = int(extra.get("n") or 0) if isinstance(extra, dict) else 0
                if n not in quiet:
                    continue
                target = cleaned[n - 1]
                add = clean({**extra, "camera": None, "view": "globe"}, target)
                for kind in ("points", "routes", "rings", "tags", "highlight"):
                    if add.get(kind):
                        target[kind] = [*(target.get(kind) or []), *add[kind]][-LIMITS.get(kind, 6):]
                for name in ("card", "stamp", "counter", "lens"):
                    if add.get(name) and not target.get(name):
                        target[name] = add[name]
                if _new_things(target):
                    filled += 1
        except Exception as error:
            print(f"   Atlas: el relleno del plan no salió ({str(error)[:80]})")
        print(f"   Atlas: plan revisado: {len(quiet)} frases sin nada nuevo ({quiet_seconds:.0f} s) → {filled} rellenadas")
        built = build()
    else:
        print("   Atlas: plan revisado: ninguna frase sin nada nuevo")

    out = {shot_id: scene for (shot_id, _), scene in zip(lines, built)}
    ensure_satellites(out, int(ctx.section("visual").get("satellites", 2)))
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


SAT_CREDIT = {"es": "Imagen: Sentinel-2 cloudless de EOX (CC BY 4.0), datos Copernicus Sentinel modificados",
              "en": "Imagery: Sentinel-2 cloudless by EOX (CC BY 4.0), contains modified Copernicus Sentinel data",
              "pt": "Imagem: Sentinel-2 cloudless da EOX (CC BY 4.0), dados Copernicus Sentinel modificados"}

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


MIN_VIEW = 4.5        # seconds: a chart, a drawing, the satellite… never on screen for less (it takes the next line too)
PUSH = 0.3            # zoom the camera gains over a globe scene (wide → closer → the next moment pulls out)
DRIFT_PER_S = 0.25    # degrees of longitude a second the globe turns on its own (Atlas.tsx cameraAt, from the start)
SINGLE = ("card", "stamp", "headline", "counter", "zone", "meridians", "night", "lens", "band")
VIEWS_ASIDE = ("chart", "icon")      # the globe moves aside for these instead of a cut


def _segments(lines: list[dict[str, Any]], fps: int) -> list[dict[str, Any]]:
    """Consecutive sentences of the same moment, the same place and the same kind of picture become ONE scene
    (the camera fixed, the elements coming in at their words); a chapter heading and every chart/drawing/satellite
    stand alone, a short one taking the next sentence too (MIN_VIEW)."""

    out: list[dict[str, Any]] = []
    for line in lines:
        if "chapter" in line:
            out.append(line)
            continue
        scene = line["scene"]
        current = out[-1] if out and "lines" in out[-1] else None
        if current is not None:
            first = current["lines"][0]["scene"]
            seconds = (current["lines"][-1]["to"] - current["lines"][0]["from"]) / fps
            if first["view"] != "globe":
                # a chart, a drawing… stays MIN_VIEW: it takes the next sentence when that one is part of the same
                # idea or brings nothing new (never a sentence with its own places: atlas e2e lost McMurdo so)
                same = scene.get("moment") == first.get("moment")
                if seconds < MIN_VIEW and scene["view"] == "globe" and (same or _new_things(scene) == 0):
                    current["lines"].append(line)
                    continue
                if scene["view"] == first["view"] and same and scene.get(first["view"]) == first.get(first["view"]):
                    current["lines"].append(line)     # the same chart said over two sentences: one scene
                    continue
            elif scene["view"] == "globe" and scene.get("moment") == first.get("moment") \
                    and _same_place(scene["camera"], first["camera"]) and bool(scene.get("dark")) == bool(first.get("dark")) \
                    and not any(scene.get(name) and not scene[name].get("kept")
                                and any(x["scene"].get(name) and not x["scene"][name].get("kept") for x in current["lines"])
                                for name in SINGLE):
                current["lines"].append(line)
                continue
        out.append({"lines": [line]})
    return out


def _segment_graphic(segment: dict[str, Any], spoken: list[tuple[int, str]], fps: int) -> dict[str, Any]:
    """The scene of a segment: the last sentence's (everything piled up), every element with the frame of its word in
    the sentence that brought it ("at") and the end of that sentence ("until": what grows with the voice grows until
    then); what was already on screen before the segment at -2 s."""

    lines = segment["lines"]
    a = lines[0]["from"]
    first = lines[0]["scene"]
    if first["view"] != "globe":
        g = json.loads(json.dumps(first))
        end = lines[0]["to"] - a
        words = [(f - a, t) for f, t in spoken if lines[0]["from"] <= f < lines[0]["to"]]
        stagger = 0
        for name in (*SINGLE, "icon", "sat", "flat", "size"):
            if g.get(name):
                g[name]["at"] = -2 * fps if g[name].get("kept") else _frame_of(g[name].get("at", ""), words, round(end * 0.2) + stagger)
                g[name]["until"] = end
                stagger += round(0.35 * fps)
        for name in ("points", "routes", "rings", "tags", "countries"):
            for i, item in enumerate(g.get(name) or []):
                item["at"] = -2 * fps if item.get("kept") else _frame_of(item.get("at", ""), words, round(end * 0.15) + i * round(0.25 * fps))
                item["until"] = end
        return g
    g = json.loads(json.dumps(lines[-1]["scene"]))
    intro: dict[tuple[str, Any], tuple[int, int]] = {}
    singles: dict[str, dict[str, Any]] = {}
    tags: list[dict[str, Any]] = []
    countries: list[dict[str, Any]] = []
    highlight: dict[str, dict[str, Any]] = {}
    for line in lines:
        off, end = line["from"] - a, line["to"] - a
        words = [(f - a, t) for f, t in spoken if line["from"] <= f < line["to"]]
        scene = line["scene"]
        span = end - off
        for kind in ("points", "routes", "rings"):
            for i, item in enumerate(scene.get(kind) or []):
                if not item.get("kept"):
                    intro.setdefault((kind, _key(kind, item)),
                                     (_frame_of(item.get("at", ""), words, off + round(span * 0.15) + i * round(0.25 * fps)), end))
        for i, t in enumerate(scene.get("tags") or []):
            if not t.get("kept") and t["text"] not in {x["text"] for x in tags}:
                tags.append({**t, "at": _frame_of(t.get("at", ""), words, off + round(span * 0.2) + i * 8), "until": end})
        for c in scene.get("countries") or []:
            if not c.get("kept") and c["name"] not in {x["name"] for x in countries} and len(countries) < 2:
                countries.append({**c, "at": _frame_of(c.get("at", ""), words, off + round(span * 0.2)) if isinstance(c.get("at"), str) else off})
        for h in scene.get("highlight") or []:
            highlight.setdefault(h["name"], h)
        stagger = 0
        for name in SINGLE:
            item = scene.get(name)
            if item and not item.get("kept") and name not in singles:
                singles[name] = {**item, "at": _frame_of(item.get("at", ""), words, off + round(span * 0.2) + stagger), "until": end}
                stagger += round(0.35 * fps)
    for kind in ("points", "routes", "rings"):
        for item in g.get(kind) or []:
            at_until = intro.get((kind, _key(kind, item)))
            item["at"], item["until"] = at_until if at_until else (-2 * fps, 0)
            item.pop("kept", None)
    for name in SINGLE:
        if name in singles:
            g[name] = singles[name]
        elif g.get(name):
            g[name] = {**g[name], "at": -2 * fps, "until": 0}
    g["tags"] = tags
    g["countries"] = countries
    g["highlight"] = list(highlight.values())
    for route in g.get("routes") or []:              # something always travels a main route (the eye follows it)
        if route.get("style") != "many" and not route.get("mover") and not route.get("trail"):
            route["mover"] = "dot"
    lens_auto(g)
    return g


def lens_auto(g: dict[str, Any]) -> None:
    """Two or more new places too close together for the camera (under ~2 % of the screen apart on the whole globe):
    a magnifying lens on them, unless the scene has one."""

    if g.get("lens") or g["camera"]["zoom"] >= REGION_ZOOM:
        return
    new = [p for p in g.get("points") or [] if p.get("at", -1) >= 0]
    radius = 350 * 1.42 ** (g["camera"]["zoom"] - 1)
    for i, p in enumerate(new):
        close = [q for q in new[i + 1:] if 0.05 < _angle((p["lat"], p["lon"]), (q["lat"], q["lon"])) < math.degrees(45 / radius)]
        if close:
            group = [p, *close]
            lat = sum(x["lat"] for x in group) / len(group)
            lon = sum(x["lon"] for x in group) / len(group)
            spread = max(_angle((lat, lon), (x["lat"], x["lon"])) for x in group)
            zoom = 1 + math.log(150 / math.sin(math.radians(max(spread, 0.2))) / 350) / math.log(1.42)
            g["lens"] = {"lat": round(lat, 3), "lon": round(lon, 3), "zoom": round(min(10.0, max(REGION_ZOOM, zoom)), 2),
                         "label": "", "at": max(x["at"] for x in group), "until": 0}
            return


def place_photo(ctx: RunContext, name: str, lat: float, lon: float) -> dict[str, Any] | None:
    """A photo of the place from Wikimedia Commons (free licences only, credited on the card), for a place the satellite
    has no picture of (Antarctica): work/<slug>/graphics/photos/."""

    from types import SimpleNamespace

    from .sourcing.images import ImageSources

    images = dict(ctx.section("sourcing").get("images") or {})
    only = {**images, "wikimedia": {**(images.get("wikimedia") or {}), "enabled": True}, "openverse": {"enabled": False},
            "pixabay": {"enabled": False}, "web": {"enabled": False}, "max_per_shot": 3}
    source = ImageSources(root=ctx.root, cache_dir=ctx.cache_dir, config=only)
    title = name.title()
    spec = SimpleNamespace(visualIntent=title, queries=[title], queriesLocal=[], entities=[title], mustContain=[], avoid=[],
                           preferredShot="wide", event=None, moment=None)
    try:
        _, found = source.search(spec, [])
    except Exception as error:
        print(f"   Atlas: foto de {title} no disponible ({str(error)[:80]})")
        return None
    for candidate in found:
        path = ctx.root / candidate.imagePath if candidate.imagePath else None
        if not path or not path.is_file():
            continue
        target = ctx.work_dir / "graphics" / "photos" / f"{key(candidate.id)[:12]}{path.suffix or '.jpg'}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            shutil.copyfile(path, target)
        credit = " · ".join(x for x in (candidate.channel or "", candidate.license or "", "Wikimedia Commons") if x)
        return {"kind": "photo", "title": title.upper(), "big": "", "lines": [], "source": credit[:90], "side": "right",
                "image": {"kind": "image", "src": str(target.relative_to(ctx.work_dir)).replace("\\", "/"), "source": "photo"}}
    return None


def groups(ctx: RunContext, shots: list[Any], fps: int, taken: list[Any], words: Any = None) -> list[dict[str, Any]]:
    """The atlas scenes of the video: the voice's sentences (sentences()), drawn line by line (scenes()), joined into
    scenes that last as long as their idea (_segments()), each with its elements at their words; a title card on every
    chapter heading."""

    from types import SimpleNamespace

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
    lines = sentences(todo)
    talk = [x for x in lines if "chapter" not in x]
    found = scenes(ctx, [SimpleNamespace(id=x["id"], text=x["text"], seconds=(x["to"] - x["from"]) / fps) for x in talk])
    for x in talk:
        x["scene"] = found.get(x["id"]) or clean({}, None)
    spoken = [(round(w.start * fps), w.text.strip()) for w in (words.words if words is not None else []) if w.text.strip()]
    brand = str(ctx.section("brand").get("name") or ctx.channel or "").strip()
    lang = str(ctx.section("align").get("language", "es"))[:2]
    photos_left = int(ctx.section("visual").get("place_photos", 2))
    out = []
    prev: dict[str, Any] | None = None             # where the camera ended in the last globe scene
    last_view = ""
    for n, segment in enumerate(_segments(lines, fps)):
        if "chapter" in segment:
            shot, a, b = segment["chapter"], segment["from"], segment["to"]
            current = chapter_of.get(shot.id, 0)
            title = _as_written(ctx, str(shot.chapterTitle or shot.text or ""))
            number = shot.chapterNumber or current or 1
            g: dict[str, Any] = {"type": "atlas", "view": "title", "camera": (prev or {"lat": 20, "lon": 0, "zoom": 1}),
                                 "dark": False, "title": {"number": ROMAN[number - 1] if number <= 10 else str(number), "text": title}}
            ident = shot.id
        else:
            a, b = segment["lines"][0]["from"], segment["lines"][-1]["to"]
            current = chapter_of.get(segment["lines"][0]["id"], 0)
            g = _segment_graphic(segment, spoken, fps)
            ident = segment["lines"][0]["id"]
        span = b - a
        for c in g.get("countries") or []:            # its flag in the video's files, and the country tinted on the globe
            code = flag_codes().get(c["name"])
            source = ctx.root / "assets" / "flags" / "4x3" / f"{code}.svg"
            if code and source.is_file():
                target = ctx.work_dir / "graphics" / "flags" / f"{code}.svg"
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.is_file():
                    shutil.copyfile(source, target)
                c["flag"] = {"kind": "image", "src": f"graphics/flags/{code}.svg", "source": "flag"}
            if not isinstance(c.get("at"), int):
                c["at"] = round(span * 0.2)
            if not any(h.get("name") == c["name"] for h in g.get("highlight") or []):
                g["highlight"] = [*(g.get("highlight") or []), {"name": c["name"], "label": "", "group": 0}]
        if g.get("view") == "sat" and g.get("sat"):
            from .mapas import satellite_layers

            try:
                layers = satellite_layers(ctx, g["sat"]["lat"], g["sat"]["lon"], g["sat"]["zoom"])
            except Exception as error:
                print(f"   Atlas: satélite no disponible ({str(error)[:80]}): se queda el globo")
                layers = []
            if layers:
                # the photo as it is (the map explainer's land-over-navy-sea cut paints green land as sea): the raw layer
                def raw(src: str) -> str:
                    candidate = src[:-4] + "-raw.jpg" if src.endswith(".jpg") else src
                    return candidate if (ctx.work_dir / candidate).is_file() else src

                g["sat"]["layers"] = [{"kind": "image", "src": raw(x["src"]), "z": x["z"], "source": "satellite"} for x in layers]
                g["sat"]["credit"] = SAT_CREDIT.get(str(ctx.section("align").get("language", "es"))[:2], SAT_CREDIT["en"])
            else:
                print(f"   Atlas: sin foto de satélite para {g['sat']['label'] or 'un sitio'}: se queda el globo")
                g["view"] = "globe"
                g["points"] = [*(g.get("points") or []), {"name": g["sat"]["label"] or "", "lat": g["sat"]["lat"],
                                                          "lon": g["sat"]["lon"], "at": g["sat"]["at"]}]
        if g.get("view") == "globe" and photos_left > 0 and not g.get("card"):
            # a place the satellite has no picture of: its photo on a paper card (Wikimedia Commons)
            spot = next((p for p in g.get("points") or [] if p.get("at", -1) >= 0 and not has_photo(p["lat"]) and not p.get("auto")), None)
            if spot:
                card = place_photo(ctx, spot["name"], spot["lat"], spot["lon"])
                if card:
                    g["card"] = {**card, "at": spot["at"] + round(0.6 * fps), "until": span}
                    photos_left -= 1
        g["prev"] = prev or g["camera"]
        g["push"] = PUSH if g.get("view") == "globe" and span >= 3 * fps and g["camera"]["zoom"] < 8.5 else 0.0
        g["enter"] = "aside" if g.get("view") == "globe" and last_view in VIEWS_ASIDE else ""
        g["chapters"] = chapters
        g["chapter"] = current
        g["brand"] = brand
        if g.get("card") and g["card"].get("kind") == "choice":     # the kicker in the video's language (atlas1pt: Spanish)
            g["card"]["kicker"] = ASK_KICKER.get(lang, ASK_KICKER["en"])
        g["seed"] = n
        out.append({"id": f"atlas-{ident}", "kind": "graphic", "from": a, "durationInFrames": span, "graphic": g})
        if g["view"] == "globe":
            cam = g["camera"]
            prev = {"lat": cam["lat"], "lon": round((cam["lon"] + DRIFT_PER_S * span / fps + 180) % 360 - 180, 4),
                    "zoom": round(cam["zoom"] + g["push"], 2)}
        elif prev is None:
            prev = g["camera"]
        last_view = g.get("view", "")
    dives = [g["graphic"]["sat"]["label"] for g in out if g["graphic"].get("view") == "sat"]
    scenes_n = sum(1 for g in out if g["graphic"].get("view") != "title")
    print(f"   Atlas: {scenes_n} escenas para {len(talk)} frases · {len(dives)} bajada(s) al satélite"
          + (f": {', '.join(d or '?' for d in dives)}" if dives else " (ningún sitio del guion con foto: la Antártida y el Ártico no tienen)"))
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
    if g.get("view") in ("sat", "flat", "size"):
        out.append(("whoosh-down" if g["view"] == "sat" else "swipe", 0, 0.35))
    if g.get("counter"):
        out.append(("data", int(g["counter"].get("at") or 0), 0.25))
    if g.get("view") == "title":
        out.append(("swipe", 0, 0.3))
    if g.get("view") == "chart":
        out.append(("data", round(fps * 0.4), 0.25))
    return out
