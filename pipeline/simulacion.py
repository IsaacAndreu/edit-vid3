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
VERSION = 4


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
Reglas: elige el mundo cuyo TEMA es el de la frase (lee bien qué enseña cada uno; una frase sobre atascos en
general no va al mundo de un carril que se cierra ni al de un cruce); si ningún mundo enseña la frase, sigue en el
mundo de la frase anterior; mantén el mismo mundo, foco y parámetros en frases seguidas de la misma
idea (la cámara no salta sin motivo); el panel tiene que mostrar lo que dice la frase en ese momento; no inventes
cifras ni fuentes: solo las que dice la frase. Escribe "title", "stat" y "list" en el idioma del guion.
Devuelve SOLO JSON: {{"scenes": [{{"n": 1, "world": "...", "focus": "...", "overlay": "...", "params": {{}},
"title": "", "stat": null, "source": "", "list": []}}]}}
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
    return {"type": "sim", "world": world, "focus": focus, "overlay": overlay, "params": params,
            "title": _words(scene.get("title"), 5).upper()[:40], "stat": stat, "source": source, "list": items}


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    """shot id → scene, from the LLM in batches of 40 lines (cached by the lines and the channel's worlds)."""

    from .llm import complete_json

    spec = allowed(ctx)
    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    cache = ctx.work_dir / "simulacion.json"
    digest = key(VERSION, lines, spec)
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if saved.get("key") == digest:
            return saved["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    system = SYSTEM.format(worlds=describe(spec))
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
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


RECAP = 0.85          # the summary list only in the last 15 % of the lines


def recap(scenes: dict[str, dict[str, Any]], order: list[str]) -> None:
    """The checklist is the closing summary: earlier lists go (hora1: «lo que hemos visto» at 1:36, over a blurred
    ring, and again over the crossroads)."""

    for n, shot_id in enumerate(order):
        if n < RECAP * len(order) and shot_id in scenes:
            scenes[shot_id]["list"] = []


SOUNDS = {"ambient": "ambiente", "click": "clic", "tick": "tic"}     # assets/sfx/sim/: street hum, relay click, soft tick


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
    found = scenes(ctx, [s for s, _, _ in todo])
    merged: list[list[Any]] = []
    for shot, a, b in todo:
        scene = found[shot.id]
        last = merged[-1] if merged else None
        if last and last[2] == a and last[3] == scene and not scene["title"] and not scene["stat"] and not scene.get("source"):
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
                    "graphic": {**scene, **extra, "at": round(a / fps, 3), "since": round(since, 3), "prev": prev}})
        previous = scene
    every = worlds()
    for group in out:
        g = group["graphic"]
        names = (every.get(g["world"], {}).get("cues") or {}).keys()
        if names:
            run = [o["graphic"] for o in out if o["graphic"]["since"] == g["since"] and o["graphic"]["world"] == g["world"]]
            g["cues"] = {name: next(r["at"] for r in run if r["overlay"] == name) for name in names
                         if any(r["overlay"] == name for r in run)}
    return out


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
            "presente, señalando lo que se ve.")


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
