"""Simulation videos: the whole video is a simulation drawn in code, no footage (canales/<canal>.yaml →
visual: {style: simulacion, worlds: [...], theme: day|night|sepia}).

Like the «simulation explainers» (a city seen from above, cars that really drive, live counters and charts):
nothing is searched or downloaded — the footage stages leave empty results, as for stickman videos — and in the
edit (timeline.py) every line of the script gets a scene the LLM picks from the worlds the channel uses. Each world
describes itself in remotion/sim/worlds.json (what it shows, its camera focuses, its panels, the parameters the
script may set within limits, and the moments the voice can cue): the LLM's instructions are built from it, its
answers are cleaned to it, and remotion/sim/worlds.tsx draws it. Adding a niche is adding a world there.

The simulation runs on its own and continuously while one world stays on screen with the same parameters (its
clock starts when that world comes in), so the voice only moves the camera, brings the panels and cues the
world's events. Scenes cached in work/<slug>/simulacion.json.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .context import RunContext
from .sourcing.common import key

MANIFEST = Path(__file__).resolve().parent.parent / "remotion" / "sim" / "worlds.json"
VERSION = 7


@lru_cache(maxsize=1)
def worlds() -> dict[str, dict[str, Any]]:
    return json.loads(MANIFEST.read_text("utf-8"))


def allowed(ctx: RunContext) -> dict[str, dict[str, Any]]:
    """The worlds this channel uses (visual.worlds), all of them when it does not say."""

    every = worlds()
    chosen = [str(w) for w in (ctx.section("visual").get("worlds") or []) if str(w) in every]
    return {w: every[w] for w in chosen} if chosen else every


def describe(spec: dict[str, dict[str, Any]]) -> str:
    """The worlds as the LLM reads them: what each one is, its focuses, panels and parameters."""

    out = []
    for name, w in spec.items():
        out.append(f'- "{name}": {w["describe"]}.')
        out.append("  focus: " + "; ".join(f'"{k}" ({v})' for k, v in w["focus"].items()))
        out.append("  overlay: " + "; ".join(f'"{k}" ({v})' for k, v in w["overlay"].items()) + '; "none"')
        if w.get("params"):
            parts = []
            for k, p in w["params"].items():
                values = "|".join(map(str, p["options"])) if "options" in p else f'{p["min"]}-{p["max"]}'
                parts.append(f'"{k}" ({values}, por defecto {p["default"]}: {p["describe"]})')
            out.append("  params: " + "; ".join(parts))
    return "\n".join(out)


SYSTEM = """
Eres el realizador de un canal que explica cómo funciona el mundo con simulaciones vistas desde arriba. Te paso las
frases del guion, numeradas, una por plano. Para CADA plano elige qué se ve, SOLO con estos mundos:
{worlds}
Además, en cada plano:
- "params": solo los parámetros del mundo que la frase cambia (p. ej. «con el doble de tráfico»), si no {{}}. Un
  cambio de parámetros reinicia la simulación: úsalo solo cuando el guion propone un experimento nuevo.
- "title": título de sección de 2-5 palabras cuando empieza una idea nueva, si no "".
- "stat": {{"label": "2-5 palabras", "value": "cifra o 1-3 palabras"}} SOLO si la frase da una cifra concreta, o null.
- "source": el estudio o la fuente que la frase cita («Sugiyama et al., 2008»), si no "".
- "list": 2-4 frases muy cortas SOLO para el resumen final, o [].
- "rules": SOLO cuando la frase enumera las reglas del sistema o apaga una: la lista de reglas que se ven en pantalla
  hasta ese momento, cada una {{"text": "2-4 palabras", "off": false}}; la que la frase apaga, con "off": true (y en
  "params" el cambio que la apaga en el mundo, si lo hay). Si no, [].
- "ask": SOLO cuando la frase le pregunta al espectador qué haría o qué va a pasar («¿qué cola eliges?», «¿frenas o
  dejas hueco?»): esa pregunta en 2-6 palabras; la simulación se para 3 segundos con ella en pantalla y luego enseña
  la respuesta. Como mucho dos en todo el vídeo, nunca en la primera frase; si no, "".
- "replay": true SOLO en la frase del momento clave que merece verse otra vez (el frenazo que lo empieza todo, el
  primer coche que se para…): la imagen se congela con «PAUSA», se rebobina y se repite a cámara lenta. Como mucho
  dos en todo el vídeo; si no, false.
Reglas: elige el mundo cuyo TEMA es el de la frase (lee bien qué enseña cada uno; una frase sobre atascos en
general no va al mundo de un carril que se cierra ni al de un cruce); si ningún mundo enseña la frase, sigue en el
mundo de la frase anterior; mantén el mismo mundo, foco y parámetros en frases seguidas de la misma
idea (la cámara no salta sin motivo); el panel tiene que mostrar lo que dice la frase en ese momento; no inventes
cifras ni fuentes: solo las que dice la frase. Escribe "title", "stat" y "list" en el idioma del guion.
Devuelve SOLO JSON: {{"scenes": [{{"n": 1, "world": "...", "focus": "...", "overlay": "...", "params": {{}},
"title": "", "stat": null, "source": "", "list": [], "rules": [], "ask": "", "replay": false}}]}}
""".strip()


def active(ctx: RunContext) -> bool:
    return str(ctx.section("visual").get("style") or "").lower() in ("simulacion", "simulación", "simulation")


def _words(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split()[:limit])


def _params(spec: dict[str, Any], given: Any) -> dict[str, Any]:
    """Every parameter of the world: the one asked for within its limits, else its default."""

    given = given if isinstance(given, dict) else {}
    out: dict[str, Any] = {}
    for name, p in (spec.get("params") or {}).items():
        value = given.get(name, p["default"])
        if "options" in p:
            out[name] = next((o for o in p["options"] if str(o) == str(value)), p["default"])
        else:
            try:
                out[name] = round(min(float(p["max"]), max(float(p["min"]), float(value))), 3)
            except (TypeError, ValueError):
                out[name] = p["default"]
    return out


def clean(scene: dict[str, Any], line: str, before: dict[str, Any] | None,
          spec: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """A scene the component can draw: only the vocabulary; parameters within their limits; a figure or a source
    only when the line says it. With no answer, the world (and its parameters) go on."""

    spec = spec or worlds()
    world = str(scene.get("world") or (before or {}).get("world") or next(iter(spec))).lower()
    world = world if world in spec else ((before or {}).get("world") if (before or {}).get("world") in spec else next(iter(spec)))
    w = spec[world]
    focus = str(scene.get("focus") or "").lower()
    focus = focus if focus in w["focus"] else ((before or {}).get("focus") if (before or {}).get("world") == world
                                               and (before or {}).get("focus") in w["focus"] else next(iter(w["focus"])))
    overlay = str(scene.get("overlay") or "none").lower()
    overlay = overlay if overlay in w["overlay"] else "none"
    asked = scene.get("params") if isinstance(scene.get("params"), dict) and scene.get("params") else None
    params = _params(w, asked if asked is not None else ((before or {}).get("params") if (before or {}).get("world") == world else {}))
    stat = scene.get("stat") if isinstance(scene.get("stat"), dict) else None
    if stat:
        value = _words(stat.get("value"), 3)
        digits = re.findall(r"\d+(?:[.,]\d+)?", value)
        said = set(re.findall(r"\d+(?:[.,]\d+)?", line))
        # a figure must be one the narrator says (or a word for it): never one the LLM made up
        stat = {"label": _words(stat.get("label"), 5).upper()[:40], "value": value.upper()[:18]} \
            if value and (not digits or set(digits) <= said) else None
    source = _words(scene.get("source"), 8)[:60]
    named = {t for t in re.findall(r"\w{4,}", source.lower())}
    if source and not (named & set(re.findall(r"\w{4,}", line.lower()))):
        source = ""                       # a source the line does not name is not shown
    items = [_words(x, 9).upper() for x in (scene.get("list") or []) if str(x).strip()][:4]
    if stat and overlay in (w.get("panels") or []):
        overlay = "none"                  # one panel at a time: the figure the voice says wins over the world's counter
    rules = [{"text": _words(r.get("text"), 5).upper()[:36], "off": r.get("off") is True}
             for r in (scene.get("rules") or []) if isinstance(r, dict) and str(r.get("text") or "").strip()][:5]
    ask = _words(scene.get("ask"), 8).strip(" ¿?")[:60]
    out = {"type": "sim", "world": world, "focus": focus, "overlay": overlay, "params": params,
           "title": _words(scene.get("title"), 5).upper()[:40], "stat": stat, "source": source, "list": items,
           "rules": rules, "replay": scene.get("replay") is True}
    if ask and "?" in line:               # «¿tú qué harías?»: only on a line that asks
        out["ask"] = f"¿{ask.upper()}?" if "¿" in line else f"{ask.upper()}?"
    return out


DIRECTOR = "escenas.txt"


def director_scenes(ctx: RunContext) -> str:
    """The scene list written for this video (materiales/<vídeo>/escenas.txt), if any."""

    path = ctx.materials_dir / DIRECTOR
    try:
        return path.read_text("utf-8").strip() if path.is_file() else ""
    except OSError:
        return ""


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    """shot id → scene, from the LLM in batches of 40 lines (cached by the lines and the channel's worlds)."""

    from .llm import complete_json

    spec = allowed(ctx)
    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    cache = ctx.work_dir / "simulacion.json"
    digest = key(VERSION, lines, spec, str(ctx.section("visual").get("guide") or ""), director_scenes(ctx), series_guide(ctx))
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if saved.get("key") == digest:
            return saved["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    system = SYSTEM.format(worlds=describe(spec))
    guide = str(ctx.section("visual").get("guide") or "").strip()
    if guide:                                    # the channel's own rules for turning a script into scenes
        system += "\n\nGUÍA DEL CANAL:\n" + guide
    serie = series_guide(ctx)
    if serie:                                    # a series of the channel («¿Y si…?»: one world, one dial)
        system += "\n\n" + serie
    director = director_scenes(ctx)
    if director:                                 # the scene list written for this script: followed line by line
        system += ("\n\nLISTA DE ESCENAS DEL DIRECTOR para este guion (síguela: cada bloque del guion con la escena que pide, "
                   "traducida a los mundos, focos, paneles, parámetros y escenas que hay; lo que no exista, con lo más parecido):\n"
                   + director[:20000])
    out: dict[str, dict[str, Any]] = {}
    before: dict[str, Any] | None = None
    for start in range(0, len(lines), 40):
        batch = lines[start:start + 40]
        listing = "\n".join(f"[{n}] {text}" for n, (_, text) in enumerate(batch, 1))
        try:
            result = complete_json(ctx, stage="simulacion", section="planner", system=system, user=listing,
                                   max_tokens=260 * len(batch))
            found = {int(s.get("n", 0)): s for s in result.get("scenes", []) if isinstance(s, dict)}
        except Exception as error:      # the simulation alone rather than no video
            print(f"   Escenas de simulación no disponibles ({str(error)[:100]}): la simulación sin paneles")
            found = {}
        for n, (shot_id, text) in enumerate(batch, 1):
            before = out[shot_id] = clean(found.get(n) or {}, text, before, spec)
    recap(out, [shot_id for shot_id, _ in lines])
    replays = [shot_id for shot_id, _ in lines if out[shot_id].get("replay")]
    for shot_id in replays[REPLAYS:]:                 # a pause is special: two at most
        out[shot_id]["replay"] = False
    if lines:
        out[lines[0][0]].pop("ask", None)            # never on the opening line
    for shot_id in [shot_id for shot_id, _ in lines if out[shot_id].get("ask")][ASKS:]:
        out[shot_id].pop("ask", None)                # «¿tú qué harías?» is special: two at most
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


REPLAYS = 2
ASKS = 2
ASK_SECONDS = 3.0     # «¿tú qué harías?»: the world stops this long with the question, the voice too
TEASER_SECONDS = 5.0  # the opening: the strongest moment of the video before the voice's hook
MIN_WORLD = 12.0      # seconds: a world stays at least this long (hora1 jumped ring → merge → crossroads in 10 s)
RECAP = 0.85          # the summary list only in the last 15 % of the lines


def recap(scenes: dict[str, dict[str, Any]], order: list[str]) -> None:
    """The checklist is the closing summary: earlier lists go (hora1: «lo que hemos visto» at 1:36, over a blurred
    ring, and again over the crossroads)."""

    for n, shot_id in enumerate(order):
        if n < RECAP * len(order) and shot_id in scenes:
            scenes[shot_id]["list"] = []


# assets/sfx/sim/: street hum, relay click, soft tick; each world's own place (indoor murmur, rain, a crowd, a kitchen)
# and events (a till's beep, a lift's bell); a hit on the key moments (the replay, a rule switched off, the opening)
SOUNDS = {"ambient": "ambiente", "click": "clic", "tick": "tic", "murmur": "murmullo", "rain": "lluvia", "crowd": "gentio",
          "kitchen": "cocina", "beep": "pitido", "ding": "campana", "impact": "golpe"}


def sounds(ctx: RunContext, publish: Any) -> dict[str, str]:
    """The simulation's sounds, published next to the voice (`publish`: timeline.py's copy into the render's folder)."""

    folder = ctx.root / "assets" / "sfx" / "sim"
    out = {}
    for name, stem in SOUNDS.items():
        found = next((p for p in sorted(folder.glob(f"{stem}.*")) if p.suffix in (".mp3", ".wav", ".m4a")), None)
        if found:
            out[name] = publish(found)
    return out


def look(ctx: RunContext) -> dict[str, str]:
    """The channel's language (the panels' words), accent colour and map theme, for every shot."""

    return {"lang": str(ctx.section("align").get("language", "es"))[:2],
            "accent": str(ctx.section("brand").get("accent") or ""),
            "theme": str(ctx.section("visual").get("theme") or "day")}


def groups(ctx: RunContext, shots: list[Any], fps: int, taken: list[Any]) -> list[dict[str, Any]]:
    """The simulation on every shot nothing else covers (graphics, chapter cards stay on top). Shots in a row with the
    same scene become one group (a panel does not blink between two shots of one sentence); each group knows when its
    world came on screen with these parameters (`since`: the simulation's clock), the focus it comes from, and the
    run's cues (the first line of the run with a cue's overlay: the world paces its events to it)."""

    # a question is see-through text: the world keeps running under it (hora1: «¿qué te ha parado?» on black)
    solid = [g for g in taken if getattr(g, "kind", None) != "question"]

    def covered(a: int, b: int) -> bool:
        return any(g.from_ < b and a < g.from_ + g.durationInFrames for g in solid)

    todo = [(s, s.from_, s.from_ + s.durationInFrames) for s in shots
            if s.type != "endscreen" and not covered(s.from_, s.from_ + s.durationInFrames)]
    found = steady(scenes(ctx, [s for s, _, _ in todo]), [(s.id, a, b) for s, a, b in todo], fps,
                   float(ctx.section("visual").get("min_world_seconds", MIN_WORLD)))
    merged: list[list[Any]] = []
    for shot, a, b in todo:
        scene = found[shot.id]
        last = merged[-1] if merged else None
        if last and last[2] == a and last[3] == scene and not scene["title"] and not scene["stat"] and not scene.get("source") \
                and not scene.get("replay") and not scene.get("ask"):
            last[2] = b
        else:
            merged.append([shot.id, a, b, scene])
    extra = look(ctx)
    out = []
    since = 0.0
    previous: dict[str, Any] | None = None
    for shot_id, a, b, scene in merged:
        same = previous is not None and previous["world"] == scene["world"] and previous.get("params") == scene.get("params")
        if not same or out and out[-1]["from"] + out[-1]["durationInFrames"] < a - fps:
            since = a / fps                      # the world comes (back) on screen, or a new experiment: it starts
        prev = previous["focus"] if same else scene["focus"]
        out.append({"id": f"sim-{shot_id}", "kind": "graphic", "from": a, "durationInFrames": b - a,
                    "graphic": {**scene, **extra, "at": round(a / fps, 3), "since": round(since, 3), "prev": prev,
                                "prevOverlay": previous["overlay"] if same else "none"}})
        previous = scene
    every = worlds()
    carried: list[dict[str, Any]] = []
    for n, group in enumerate(out):
        g = group["graphic"]
        before = out[n - 1]["graphic"] if n else None
        if before is None or before["world"] != g["world"]:
            carried = []
        if g.get("rules"):
            # the ones already on screen do not come in again: only the new ones (and a rule switched off) animate
            known = [r["text"] for r in carried]
            g["rulesFrom"] = sum(1 for r in g["rules"] if r["text"] in known)
            g["rulesOff"] = [i for i, r in enumerate(g["rules"]) if r["off"]
                             and not any(c["text"] == r["text"] and c["off"] for c in carried)]
            carried = g["rules"]
        elif carried:
            g["rules"] = carried                 # the rules stay on screen while the world does
            g["rulesFrom"] = len(carried)
            g["rulesOff"] = []
        # the dial: a number of the same world turned up or down by this line
        if before is not None and before["world"] == g["world"]:
            spec_params = every.get(g["world"], {}).get("params") or {}
            for name, value in (g.get("params") or {}).items():
                old = (before.get("params") or {}).get(name)
                if isinstance(value, (int, float)) and isinstance(old, (int, float)) and old != value:
                    p = spec_params.get(name, {})
                    options = [o for o in p.get("options", []) if isinstance(o, (int, float))]
                    low = p.get("min", min(options) if options else min(old, value))
                    high = p.get("max", max(options) if options else max(old, value))
                    label = p.get("label") or name
                    label = label.get(str(g.get("lang") or "es"), label.get("es", name)) if isinstance(label, dict) else label
                    g["dial"] = {"label": str(label).upper()[:30], "from": old, "to": value,
                                 "min": low, "max": high, "percent": bool(p.get("percent"))}
                    break
    recap_scenes(out)
    if out and ctx.section("shorts").get("of") and ctx.section("visual").get("loop", True) is not False:
        # a Short loops: its last shot ends on its first scene, so watched again it does not jump
        first = out[0]["graphic"]
        out[-1]["graphic"]["loopTo"] = {**{k: first[k] for k in KEEP if k in first}, "type": "sim", "prev": first["focus"],
                                         "title": "", "stat": None, "source": "", "list": [], "overlay": "none"}
    legend = False
    for n, group in enumerate(out):
        g = group["graphic"]
        before = out[n - 1] if n else None
        after = out[n + 1] if n + 1 < len(out) else None
        joined = lambda x, y: x["from"] + x["durationInFrames"] >= y["from"] - 1     # noqa: E731
        # a world coming on screen zooms in from the last one; a world leaving zooms out (no blurred cut)
        g["enter"] = not (before and before["graphic"]["world"] == g["world"] and joined(before, group))
        g["exit"] = not (after and after["graphic"]["world"] == g["world"] and joined(group, after))
        if not legend and every.get(g["world"], {}).get("legend"):
            # the colours explained once, for the whole video, where that world has room (worlds.json → legend)
            g["legend"] = str(every[g["world"]]["legend"])
            legend = True
        names = (every.get(g["world"], {}).get("cues") or {}).keys()
        if names:
            run = [o["graphic"] for o in out if o["graphic"]["since"] == g["since"] and o["graphic"]["world"] == g["world"]]
            g["cues"] = {name: next(r["at"] for r in run if r["overlay"] == name) for name in names
                         if any(r["overlay"] == name for r in run)}
    return out


def steady(found: dict[str, dict[str, Any]], spans: list[tuple[str, int, int]], fps: int,
           least: float = MIN_WORLD) -> dict[str, dict[str, Any]]:
    """No world on screen for less than MIN_WORLD seconds: a short visit stays in the world before it (the first one,
    in the world after it), with that world's camera and no panel of its own; its title, figure, source and recap
    are kept. The scenes are copied, not changed."""

    out = {k: dict(v) for k, v in found.items()}

    def runs() -> list[list[int]]:
        result: list[list[int]] = []
        for i, (shot_id, _, _) in enumerate(spans):
            if result and out[spans[result[-1][-1]][0]]["world"] == out[shot_id]["world"]:
                result[-1].append(i)
            else:
                result.append([i])
        return result

    for _ in range(len(spans)):
        current = runs()
        if len(current) < 2:
            break
        short = next((r for r in current if (spans[r[-1]][2] - spans[r[0]][1]) / fps < least), None)
        if short is None:
            break
        k = current.index(short)
        host = current[k - 1][-1] if k else current[1][0]
        model = out[spans[host][0]]
        for i in short:
            scene = out[spans[i][0]]
            scene.update(world=model["world"], focus=model["focus"], params=model["params"], overlay="none")
    return out


def _plain(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if c.isalnum() or c.isspace())


def sync(groups: list[Any], words: list[Any], frame_of: Any, fps: int) -> None:
    """With the voice's word times: the figure of a shot comes in on the word that says it (statAt), and the things
    the voice points at («este coche», «la onda», «el hueco») get an arrow with those words at that moment (marks:
    the world's vocabulary in worlds.json → marks). Changes the sim groups' graphics in place."""

    every = worlds()
    timed = [(frame_of(w.start), _plain(w.text)) for w in words if w.text.strip()]
    for group in groups:
        g = group.graphic if hasattr(group, "graphic") else group.get("graphic")
        if not isinstance(g, dict) or g.get("type") != "sim":
            continue
        a = group.from_ if hasattr(group, "from_") else group["from"]
        b = a + (group.durationInFrames if hasattr(group, "durationInFrames") else group["durationInFrames"])
        said = [(f, t) for f, t in timed if a <= f < b]
        if g.get("stat"):
            digits = re.findall(r"\d+", str(g["stat"].get("value") or ""))
            hit = next((f for f, t in said if digits and any(d in t for d in digits)), None)
            if hit is None:
                value = _plain(str(g["stat"].get("value") or "")).split()
                hit = next((f for f, t in said if value and t == value[0]), None)
            if hit is not None:
                g["statAt"] = round((hit - a) / fps, 2)
        vocab = every.get(g["world"], {}).get("marks") or {}
        marks = []
        for kind, phrases in vocab.items():
            for phrase in phrases:
                parts = _plain(phrase).split()
                found = next((i for i in range(len(said)) if [t for _, t in said[i:i + len(parts)]] == parts), None)
                if found is not None:
                    text = " ".join(t for _, t in said[found:found + len(parts)])
                    marks.append({"kind": kind, "at": round((said[found][0] - a) / fps, 2), "text": text.upper()})
                    break
        if marks:
            g["marks"] = sorted(marks, key=lambda m: m["at"])[:3]


REVIEW = """
Eres el realizador de un canal que explica cosas con simulaciones. Te paso los mundos que el canal puede enseñar y el
guion numerado por frases. Para cada frase di si algún mundo la puede ENSEÑAR (no solo acompañar):
{worlds}
Devuelve SOLO JSON: {{"lines": [{{"n": 1, "ok": true, "world": "…", "why": "", "fix": ""}}]}}
- "ok": false solo si ningún mundo enseña lo que dice la frase (un dato histórico suelto, una idea abstracta, algo
  que pasa fuera de lo simulado); entonces "why" en 1 frase y "fix": la frase reescrita para que se pueda enseñar,
  o "quitar".
""".strip()


def review_script(ctx: RunContext, script: str) -> dict[str, Any]:
    """Before recording: the lines of the script no world can show, with a fix for each."""

    from .llm import complete_json

    lines = [l.strip() for l in re.split(r"(?<=[.!?…])\s+", " ".join(
        l for l in script.splitlines() if not l.strip().startswith("## "))) if len(l.strip()) > 3]
    if not lines:
        raise ValueError("El guion está vacío")
    listing = "\n".join(f"[{n}] {l}" for n, l in enumerate(lines, 1))
    result = complete_json(ctx, stage="simulacion", section="planner", system=REVIEW.format(worlds=describe(allowed(ctx))),
                           user=listing, max_tokens=120 * len(lines) + 400)
    flagged = []
    for item in result.get("lines") or []:
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        if item.get("ok") is False and 1 <= n <= len(lines):
            flagged.append({"n": n, "line": lines[n - 1], "why": str(item.get("why") or "")[:200],
                            "fix": str(item.get("fix") or "")[:400]})
    return {"lines": len(lines), "flagged": flagged,
            "verdict": "✅ Todas las frases se pueden enseñar" if not flagged
            else f"⚠️ {len(flagged)} de {len(lines)} frases no las enseña ningún mundo"}


def review_file(ctx: RunContext) -> Path:
    """--check: escenas.md next to the other checks."""

    result = review_script(ctx, (ctx.materials_dir / "guion.txt").read_text("utf-8"))
    out = [f"# Escenas · {ctx.slug}", "", result["verdict"], ""]
    for item in result["flagged"]:
        out += [f"- **[{item['n']}]** «{item['line']}»", f"  - Por qué: {item['why']}", f"  - Propuesta: {item['fix']}", ""]
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.out_dir / "escenas.md"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def qa(ctx: RunContext, timeline: dict[str, Any], final: Path | None = None) -> list[str]:
    """After the render of a simulation video: stretches with nothing moving for more than `still` seconds (in the
    finished picture), worlds that come and go in less than MIN_WORLD seconds, and words that land on top of each
    other (a figure and the recap, the pause sign and a title, two arrows at once). out/<slug>/qa/simulacion.md."""

    fps = int(timeline.get("fps", 30))
    still = float(ctx.section("visual").get("qa_still_seconds", 6))
    least = float(ctx.section("visual").get("min_world_seconds", MIN_WORLD))
    found: list[str] = []
    stamp = lambda frames: f"{int(frames / fps) // 60}:{int(frames / fps) % 60:02d}"   # noqa: E731
    if final is not None and final.is_file():
        from .doctor import detect

        for p in detect(final, {"freeze_seconds": still, "black_seconds": 99, "freeze_noise": 0.003}):
            if p["kind"] == "frozen":
                end = p["end"] if p["end"] is not None else timeline["durationInFrames"] / fps
                found.append(f"{stamp(p['start'] * fps)} · {end - p['start']:.0f} s sin movimiento")
    sims = [g for g in timeline.get("groups", []) if (g.get("graphic") or {}).get("type") == "sim"
            and not g["graphic"].get("teaser")]                    # the opening is short on purpose
    runs: list[list[dict[str, Any]]] = []
    for g in sims:
        if runs and runs[-1][-1]["graphic"]["world"] == g["graphic"]["world"]:
            runs[-1].append(g)
        else:
            runs.append([g])
    for n, run in enumerate(runs):
        seconds = (run[-1]["from"] + run[-1]["durationInFrames"] - run[0]["from"]) / fps
        if len(runs) > 1 and seconds < least:
            found.append(f"{stamp(run[0]['from'])} · «{run[0]['graphic']['world']}» solo {seconds:.0f} s en pantalla")
    for g in sims:
        x = g["graphic"]
        at = stamp(g["from"])
        if x.get("stat") and x.get("list"):
            found.append(f"{at} · la cifra y el resumen a la vez")
        if x.get("replay") and x.get("title"):
            found.append(f"{at} · el rótulo de pausa y el título a la vez")
        if x.get("legend") == "bottom" and x.get("stat"):
            found.append(f"{at} · la leyenda y la cifra en la misma zona")
        marks = sorted(m["at"] for m in x.get("marks") or [])
        if any(b - a < 1.0 for a, b in zip(marks, marks[1:])):
            found.append(f"{at} · dos flechas casi a la vez")
    lines = [f"# Control de la simulación · {ctx.slug}", "",
             "✅ Sin tramos quietos, saltos de mundo ni textos que se pisen" if not found
             else f"⚠️ {len(found)} avisos:", "", *[f"- {x}" for x in found]]
    (ctx.out_dir / "qa").mkdir(parents=True, exist_ok=True)
    (ctx.out_dir / "qa" / "simulacion.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return found


KEEP = ("world", "focus", "overlay", "params", "at", "since", "cues", "lang", "accent", "theme")


def recap_scenes(out: list[dict[str, Any]]) -> None:
    """The closing summary (a group with "list") replays the video's key scenes in order, one per idea: from each
    experiment (a world with its parameters) its key shot — the replayed moment, a rule switched off, a figure, else
    its longest shot — as it was on screen (graphic.recap). Changes the groups in place."""

    for n, group in enumerate(out):
        g = group["graphic"]
        if not g.get("list"):
            continue
        runs: list[list[dict[str, Any]]] = []
        for x in out[:n]:
            if runs and runs[-1][-1]["graphic"]["world"] == x["graphic"]["world"] \
                    and runs[-1][-1]["graphic"]["since"] == x["graphic"]["since"]:
                runs[-1].append(x)
            else:
                runs.append([x])
        if not runs:
            continue

        def weight(x: dict[str, Any]) -> tuple[int, int]:
            y = x["graphic"]
            return (3 if y.get("replay") else 2 if y.get("rulesOff") else 1 if y.get("stat") else 0, x["durationInFrames"])

        keys = [max(run, key=weight) for run in runs]
        want = max(2, min(4, len(g["list"])))
        if len(keys) > want:                     # the strongest ones, kept in the order of the video
            best = sorted(range(len(keys)), key=lambda i: (weight(keys[i]), sum(x["durationInFrames"] for x in runs[i])),
                          reverse=True)[:want]
            keys = [keys[i] for i in sorted(best)]
        g["recap"] = [{**{k: x["graphic"][k] for k in KEEP if k in x["graphic"]}, "type": "sim",
                       "prev": x["graphic"]["focus"], "title": "", "stat": None, "source": "", "list": []} for x in keys]


def retime_sim(old: dict[str, Any], new: dict[str, Any], lang: str) -> None:
    """A dubbed simulation video (pipeline/dub.py): the shots moved with the new voice, so each world's clock moves
    with them — a shot starts at its new second, a world's run starts where its first shot now starts, the voice's cues
    fall on the same lines, a figure or an arrow keeps its place inside its shot — and every panel speaks `lang`."""

    fps = int(new.get("fps", 30))
    before = {g["id"]: g for g in old.get("groups", []) if (g.get("graphic") or {}).get("type") == "sim"}
    moved: dict[float, float] = {}                       # old second where a shot started → its new second
    for g in new.get("groups", []):
        if g["id"] in before:
            moved[round(float(before[g["id"]]["graphic"]["at"]), 3)] = round(g["from"] / fps, 3)

    def when(t: float) -> float:
        t = round(float(t), 3)
        if t in moved:
            return moved[t]
        keys = sorted(moved)                               # between two shots: in proportion
        lower = max((k for k in keys if k <= t), default=None)
        upper = min((k for k in keys if k > t), default=None)
        if lower is None or upper is None:
            return moved[lower if lower is not None else upper] if moved else t
        return round(moved[lower] + (t - lower) * (moved[upper] - moved[lower]) / (upper - lower), 3)

    def fix(graphic: dict[str, Any]) -> dict[str, Any]:
        out = {**graphic, "lang": lang, "at": when(graphic["at"]), "since": when(graphic["since"])}
        if graphic.get("cues"):
            out["cues"] = {k: when(v) for k, v in graphic["cues"].items()}
        if graphic.get("recap"):
            out["recap"] = [fix(r) for r in graphic["recap"]]
        return out

    for g in new.get("groups", []):
        if g["id"] not in before:
            continue
        o = before[g["id"]]
        k = g["durationInFrames"] / max(1, o["durationInFrames"])
        graphic = fix(g["graphic"])
        if graphic.get("statAt") is not None:
            graphic["statAt"] = round(graphic["statAt"] * k, 2)
        if graphic.get("marks"):
            graphic["marks"] = [{**m, "at": round(m["at"] * k, 2)} for m in graphic["marks"]]
        if graphic.get("dial"):
            label = (worlds().get(graphic["world"], {}).get("params") or {})
            for name, p in label.items():
                if isinstance(p.get("label"), dict) and graphic["dial"]["label"] == str(p["label"].get("es", "")).upper()[:30]:
                    graphic["dial"]["label"] = str(p["label"].get(lang, p["label"]["es"])).upper()[:30]
        g["graphic"] = graphic


def series_guide(ctx: RunContext) -> str:
    """The rules of the video's series (canales/<canal>.yaml → series.<serie>.visual.serie), if any."""

    return str(ctx.section("visual").get("serie") or "").strip()


def writing(ctx: RunContext) -> str:
    """For the script draft (organizar.draft_script): what the simulation can show, so the narration asks for it."""

    if not active(ctx):
        return ""
    return ("ESTE CANAL SE HACE CON SIMULACIONES VISTAS DESDE ARRIBA, SIN METRAJE. Escribe el guion para que cada idea "
            "se pueda ENSEÑAR con estos mundos (y sus paneles y parámetros):\n" + describe(allowed(ctx)) + "\n"
            "Estructura: una pregunta gancho que la simulación responde; montas el experimento (qué hay, qué reglas); "
            "lo dejas correr y narras lo que pasa en el momento en que pasa («ahora, este coche frena»); el giro (lo "
            "inesperado); un dato real de un estudio, citando quién y cuándo; un segundo experimento cambiando un "
            "parámetro («¿y si hubiera el doble de coches?»); y un resumen final de 3-4 ideas. Frases cortas, en "
            "presente, señalando lo que se ve. Si pide a quien mira que prediga o elija («¿qué cola eliges?»), "
            "deja esa pregunta sola en su frase: el vídeo se para 3 segundos con ella."
            + ("\n\n" + series_guide(ctx) if series_guide(ctx) else ""))


def moments(groups: list[Any], fps: int, count: int) -> list[float]:
    """Seconds of the video for thumbnails: one per experiment (a world with its parameters), the longest first, late
    in its last shot — the simulation has played out (the jam formed, the fire spread) and its comparison is on."""

    runs: dict[tuple[str, float], list[Any]] = {}
    for group in groups:
        g = (group.graphic if hasattr(group, "graphic") else group.get("graphic")) or {}
        if g.get("type") == "sim":
            runs.setdefault((g["world"], g["since"]), []).append(group)

    def span(group: Any) -> tuple[int, int]:
        return (group.from_, group.durationInFrames) if hasattr(group, "from_") else (group["from"], group["durationInFrames"])

    ordered = sorted(runs.values(), key=lambda run: -sum(span(g)[1] for g in run))
    late = lambda group: round((span(group)[0] + span(group)[1] * 0.75) / fps, 2)
    out = [late(run[-1]) for run in ordered[:count]]
    rest = [g for run in ordered for g in run[:-1]]          # fewer experiments than frames asked: other shots, spread
    step = max(1, len(rest) // max(1, count - len(out)))
    out += [late(g) for g in rest[::step]][: count - len(out)]
    return out


def _shift_graphic(g: dict[str, Any], seconds: float, after: float = -1.0) -> dict[str, Any]:
    """A sim graphic `seconds` later in the video (its clock, its cues and its recap's scenes with it): only the
    parts at or after `after` (video seconds) move."""

    out = dict(g)
    if float(g.get("at", 0)) >= after:
        out["at"] = round(float(g["at"]) + seconds, 3)
        out["since"] = round(float(g["since"]) + seconds, 3)
        if g.get("cues"):
            out["cues"] = {k: round(float(v) + seconds, 3) for k, v in g["cues"].items()}
    if g.get("recap"):
        out["recap"] = [_shift_graphic(r, seconds, after) for r in g["recap"]]
    if g.get("teaser"):
        out["teaser"] = _shift_graphic(g["teaser"], seconds, after)
    return out


def with_asks(timeline: Any, fps: int, seconds: float = ASK_SECONDS) -> Any:
    """«¿Tú qué harías?»: after a line that asks the viewer (graphic.ask) the voice stops `seconds` and its shot holds
    that long (the world frozen with the question and a countdown, SimScene); everything after it moves, the world's
    clock with it (it goes on where it stopped). Run while timeline frames are still voice frames plus gaps."""

    from .camera import voice_frame_at
    from .schemas import Timeline

    frames = round(seconds * fps)
    if frames <= 0:
        return timeline
    for gid in [g.id for g in timeline.groups if (g.graphic or {}).get("type") == "sim" and (g.graphic or {}).get("ask")]:
        group = next(g for g in timeline.groups if g.id == gid)
        end = group.from_ + group.durationInFrames
        if not any(s.from_ + s.durationInFrames == end for s in timeline.shots):
            continue
        voice_at = voice_frame_at(list(timeline.audio.voiceGaps), end)
        moved_s = end / fps

        def moved(item: Any) -> Any:
            if item.from_ >= end:
                update: dict[str, Any] = {"from_": item.from_ + frames}
                graphic = getattr(item, "graphic", None)
                if isinstance(graphic, dict) and graphic.get("type") == "sim":
                    update["graphic"] = _shift_graphic(graphic, seconds, moved_s)
                return item.model_copy(update=update)
            if item.from_ + getattr(item, "durationInFrames", 0) >= end and hasattr(item, "durationInFrames"):
                update = {"durationInFrames": item.durationInFrames + frames}
                if getattr(item, "id", None) == gid:
                    update["graphic"] = {**item.graphic, "askHold": round(frames / fps, 3)}
                return item.model_copy(update=update)
            return item

        speech = []
        for a, b in timeline.audio.speech:
            if b <= end:
                speech.append((a, b))
            elif a >= end:
                speech.append((a + frames, b + frames))
            else:
                speech += [(a, end), (end + frames, b + frames)]
        audio = timeline.audio.model_copy(update={
            "clips": [c.model_copy(update={"from_": c.from_ + frames}) if c.from_ >= end else c for c in timeline.audio.clips],
            "sfx": [x.model_copy(update={"from_": x.from_ + frames}) if x.from_ >= end else x for x in timeline.audio.sfx],
            "speech": speech, "voiceGaps": sorted([*timeline.audio.voiceGaps, (voice_at, frames)]),
        })
        shots = [s.model_copy(update={"durationInFrames": s.durationInFrames + frames}) if s.from_ + s.durationInFrames == end
                 else s.model_copy(update={"from_": s.from_ + frames}) if s.from_ >= end else s for s in timeline.shots]
        timeline = Timeline.model_validate({
            **timeline.model_dump(by_alias=True),
            "durationInFrames": timeline.durationInFrames + frames,
            "shots": [s.model_dump(by_alias=True) for s in shots],
            "groups": [moved(g).model_dump(by_alias=True) for g in timeline.groups],
            "labels": [moved(label).model_dump(by_alias=True) for label in timeline.labels],
            "audio": audio.model_dump(by_alias=True),
        })
    return timeline


def climax(groups: list[Any], fps: int) -> dict[str, Any] | None:
    """The strongest moment of the video, for its opening: the replayed moment, a rule switched off, a figure, else
    the longest experiment — late in its shot (the jam formed, the crowd pressed), not the closing recap. A sim graphic
    whose clock (at) is that moment."""

    def parts(group: Any) -> tuple[int, int, dict[str, Any]]:
        if hasattr(group, "from_"):
            return group.from_, group.durationInFrames, group.graphic or {}
        return group["from"], group["durationInFrames"], group.get("graphic") or {}

    sims = [parts(g) for g in groups if parts(g)[2].get("type") == "sim" and not parts(g)[2].get("list")]
    if not sims:
        return None
    end = max(a + n for a, n, _ in sims)
    runs: dict[tuple[str, float], int] = {}
    for a, n, g in sims:
        runs[(g["world"], g["since"])] = runs.get((g["world"], g["since"]), 0) + n

    def weight(item: tuple[int, int, dict[str, Any]]) -> tuple[int, int, int]:
        a, n, g = item
        early = 1 if a < 0.15 * end else 0                   # the opening's own world is no surprise
        key = 3 if g.get("replay") else 2 if g.get("rulesOff") else 1 if g.get("stat") else 0
        return (key - early, runs[(g["world"], g["since"])], n)

    a, n, g = max(sims, key=weight)
    seconds = n / fps
    if g.get("replay"):                                       # the frozen moment itself, from just before it
        moment = a / fps + max(0.0, min(1.5, seconds * 0.3) - 1.0)
    else:
        moment = a / fps + max(0.0, seconds * 0.75 - TEASER_SECONDS)
    keep = {k: g[k] for k in KEEP if k in g}
    return {**keep, "type": "sim", "at": round(moment, 3), "prev": g["focus"], "title": "", "stat": None, "source": "",
            "list": [], "overlay": "none", "enter": True, "exit": True, "sounds": g.get("sounds")}


def with_teaser(timeline: Any, fps: int, seconds: float = TEASER_SECONDS) -> Any:
    """The opening: the video's strongest moment (climax) for `seconds` before anything else, then the voice's hook.
    Everything — shots, panels, sounds, the voice — moves after it; the world's clocks with it."""

    from .schemas import Timeline

    key = climax(timeline.groups, fps)
    frames = round(seconds * fps)
    if key is None or frames <= 0:
        return timeline
    teaser_shot = {"id": "teaser", "type": "broll", "from": 0, "durationInFrames": frames, "text": ""}

    def moved(item: Any) -> Any:
        update: dict[str, Any] = {"from_": item.from_ + frames}
        graphic = getattr(item, "graphic", None)
        if isinstance(graphic, dict) and graphic.get("type") == "sim":
            update["graphic"] = _shift_graphic(graphic, seconds)
        return item.model_copy(update=update)

    shifted = _shift_graphic(key, seconds)
    group = {"id": "sim-teaser", "kind": "graphic", "from": 0, "durationInFrames": frames,
             "graphic": {**shifted, "since": round(shifted["since"], 3), "teaser": True}}
    audio = timeline.audio.model_copy(update={
        "voiceFrom": timeline.audio.voiceFrom + frames,
        "clips": [c.model_copy(update={"from_": c.from_ + frames}) for c in timeline.audio.clips],
        "speech": [(a + frames, b + frames) for a, b in timeline.audio.speech],
        "sfx": [x.model_copy(update={"from_": x.from_ + frames}) for x in timeline.audio.sfx],
        "musicParts": [p.model_copy(update={"from_": p.from_ + frames}) if hasattr(p, "from_") else p
                       for p in timeline.audio.musicParts],
    })
    return Timeline.model_validate({
        **timeline.model_dump(by_alias=True),
        "durationInFrames": timeline.durationInFrames + frames,
        "shots": [teaser_shot, *[moved(s).model_dump(by_alias=True) for s in timeline.shots]],
        "groups": [group, *[moved(g).model_dump(by_alias=True) for g in timeline.groups]],
        "labels": [moved(label).model_dump(by_alias=True) for label in timeline.labels],
        "captions": [moved(c).model_dump(by_alias=True) if hasattr(c, "from_") else c.model_dump(by_alias=True)
                     for c in timeline.captions],
        "audio": audio.model_dump(by_alias=True),
    })


def chapters(timeline: Any, intro: str = "Intro") -> list[tuple[float, str]]:
    """YouTube chapters of a simulation video (in the description, no cards on screen): a mark where each experiment
    starts (a world, or the same world with new parameters) with a section title, named by that title; the first at
    0:00. publish.chapter_lines applies YouTube's rules (≥ 3, ≥ 10 s apart)."""

    fps = timeline.fps if hasattr(timeline, "fps") else timeline["fps"]
    groups = timeline.groups if hasattr(timeline, "groups") else timeline["groups"]
    marks: list[tuple[float, str]] = []
    run: tuple[str, float] | None = None
    for group in sorted(groups, key=lambda g: g.from_ if hasattr(g, "from_") else g["from"]):
        g = (group.graphic if hasattr(group, "graphic") else group.get("graphic")) or {}
        if g.get("type") != "sim" or g.get("teaser"):
            continue
        a = (group.from_ if hasattr(group, "from_") else group["from"]) / fps
        current = (g["world"], g["since"])
        title = str(g.get("title") or "").strip()
        if g.get("list") and title:
            marks.append((a, title))
        elif current != run and title:
            marks.append((a, title))
        elif current != run and marks and marks[-1][0] >= a - 1.5:
            pass
        elif current != run and not title:
            marks.append((a, ""))                      # named by the first title of the run, if it has one
        elif title and marks and not marks[-1][1]:
            marks[-1] = (marks[-1][0], title)
        run = current
    marks = [(t, name) for t, name in marks if name]
    if not marks or marks[0][0] > 0:
        marks.insert(0, (0.0, intro))
    else:
        marks[0] = (0.0, marks[0][1])
    return marks
