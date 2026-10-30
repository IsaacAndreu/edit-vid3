"""Simulation videos: the whole video is a simulation drawn in code, no footage (canales/<canal>.yaml →
visual: {style: simulacion}).

Like the «simulation explainers» (a city seen from above, cars that really drive, live counters and charts):
nothing is searched or downloaded — the footage stages leave empty results, as for stickman videos — and in the
edit (timeline.py) every line of the script gets a scene the LLM picks from a fixed vocabulary: the world being
simulated (`WORLDS`, remotion/lab: junction.ts, traffic.ts), where the camera looks, which panel shows, plus a
section title, a big figure or a recap list. The simulation runs on its own and continuously while one world stays
on screen (its clock starts when that world comes in), so the voice only moves the camera and brings the panels.
Scenes cached in work/<slug>/simulacion.json.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .context import RunContext
from .sourcing.common import key

# world → its focuses and overlays (what remotion/components/graphics/SimScene.tsx knows how to draw)
WORLDS: dict[str, dict[str, tuple[str, ...]]] = {
    "cruces": {"focus": ("both", "left", "right"),
               "overlay": ("none", "labels", "demand", "queue", "yield", "results", "conflicts", "paths")},
    "anillo": {"focus": ("ring", "chart"),
               "overlay": ("none", "speed", "brake", "jam", "chart")},
}
VERSION = 2
SYSTEM = f"""
Eres el realizador de un canal que explica cómo funciona el mundo con simulaciones vistas desde arriba (tráfico,
ciudades). Te paso las frases del guion, numeradas, una por plano. Para CADA plano elige qué se ve, SOLO con este
vocabulario:
- "world": "cruces" (un cruce con semáforos a la izquierda y una rotonda a la derecha, con los mismos coches) o
  "anillo" (22 coches en un círculo de 230 m: un conductor frena un poco y se forma un atasco sin motivo).
- "focus": en "cruces": "both" (pantalla partida), "left" (se amplía el semáforo), "right" (se amplía la rotonda);
  en "anillo": "ring" (el círculo) o "chart" (el círculo a un lado y la gráfica espacio-tiempo al otro).
- "overlay" (el panel que aparece): en "cruces": "labels" (títulos), "demand" (el mismo tráfico a los dos), "queue"
  (coches esperando en rojo y qué dirección tiene verde), "yield" (los que ceden el paso en la rotonda), "results"
  (espera media y coches que han pasado en cada uno), "conflicts" (32 puntos de choque frente a 8), "paths" (flechas
  de las trayectorias: dónde se cruzan dos coches en el semáforo y cómo se incorporan y salen en la rotonda: para
  frases sobre cruzar, incorporarse o ceder), "none";
  en "anillo": "speed" (velocidad media), "brake" (señala al conductor que frena), "jam" (coches parados ahora),
  "chart" (gráfica espacio-tiempo), "none".
- "title": título de sección de 2-5 palabras cuando empieza una idea nueva, si no "".
- "stat": {{"label": "2-5 palabras", "value": "cifra o 1-3 palabras"}} SOLO si la frase da una cifra concreta, o null.
- "list": 2-4 frases muy cortas SOLO para el resumen final, o [].
Reglas: elige el mundo que ilustra la frase; mantén el mismo mundo y foco en frases seguidas de la misma idea (la
cámara no salta sin motivo); el panel tiene que mostrar lo que dice la frase en ese momento; no inventes cifras: en
"stat" solo las que dice la frase. Devuelve SOLO JSON:
{{"scenes": [{{"n": 1, "world": "...", "focus": "...", "overlay": "...", "title": "", "stat": null, "list": []}}]}}
""".strip()


def active(ctx: RunContext) -> bool:
    return str(ctx.section("visual").get("style") or "").lower() in ("simulacion", "simulación", "simulation")


def _words(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split()[:limit])


def clean(scene: dict[str, Any], line: str, before: dict[str, Any] | None) -> dict[str, Any]:
    """A scene the component can draw: only the vocabulary; a figure only when the line says it."""

    world = str(scene.get("world") or (before or {}).get("world") or "cruces").lower()
    world = world if world in WORLDS else "cruces"
    focus = str(scene.get("focus") or "").lower()
    focus = focus if focus in WORLDS[world]["focus"] else WORLDS[world]["focus"][0]
    overlay = str(scene.get("overlay") or "none").lower()
    overlay = overlay if overlay in WORLDS[world]["overlay"] else "none"
    stat = scene.get("stat") if isinstance(scene.get("stat"), dict) else None
    if stat:
        value = _words(stat.get("value"), 3)
        digits = re.findall(r"\d+(?:[.,]\d+)?", value)
        said = set(re.findall(r"\d+(?:[.,]\d+)?", line))
        # a figure must be one the narrator says (or a word for it): never one the LLM made up
        stat = {"label": _words(stat.get("label"), 5).upper()[:40], "value": value.upper()[:18]} \
            if value and (not digits or set(digits) <= said) else None
    items = [_words(x, 9).upper() for x in (scene.get("list") or []) if str(x).strip()][:4]
    return {"type": "sim", "world": world, "focus": focus, "overlay": overlay,
            "title": _words(scene.get("title"), 5).upper()[:40], "stat": stat, "list": items}


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    """shot id → scene, from the LLM in batches of 40 lines (cached by the lines themselves)."""

    from .llm import complete_json

    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    cache = ctx.work_dir / "simulacion.json"
    digest = key(VERSION, lines)
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if saved.get("key") == digest:
            return saved["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    out: dict[str, dict[str, Any]] = {}
    before: dict[str, Any] | None = None
    for start in range(0, len(lines), 40):
        batch = lines[start:start + 40]
        listing = "\n".join(f"[{n}] {text}" for n, (_, text) in enumerate(batch, 1))
        try:
            result = complete_json(ctx, stage="simulacion", section="planner", system=SYSTEM, user=listing,
                                   max_tokens=220 * len(batch))
            found = {int(s.get("n", 0)): s for s in result.get("scenes", []) if isinstance(s, dict)}
        except Exception as error:      # the simulation alone rather than no video
            print(f"   Escenas de simulación no disponibles ({str(error)[:100]}): la simulación sin paneles")
            found = {}
        for n, (shot_id, text) in enumerate(batch, 1):
            before = out[shot_id] = clean(found.get(n) or {}, text, before)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


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


def groups(ctx: RunContext, shots: list[Any], fps: int, taken: list[Any]) -> list[dict[str, Any]]:
    """The simulation on every shot nothing else covers (graphics, chapter cards stay on top). Shots in a row with the
    same scene become one group (a panel does not blink between two shots of one sentence); each group knows when its
    world came on screen (`since`: the simulation's clock) and the focus it comes from (the camera moves from there)."""

    def covered(a: int, b: int) -> bool:
        return any(g.from_ < b and a < g.from_ + g.durationInFrames for g in taken)

    todo = [(s, s.from_, s.from_ + s.durationInFrames) for s in shots
            if s.type != "endscreen" and not covered(s.from_, s.from_ + s.durationInFrames)]
    found = scenes(ctx, [s for s, _, _ in todo])
    merged: list[list[Any]] = []
    for shot, a, b in todo:
        scene = found[shot.id]
        last = merged[-1] if merged else None
        if last and last[2] == a and last[3] == scene and not scene["title"] and not scene["stat"]:
            last[2] = b
        else:
            merged.append([shot.id, a, b, scene])
    out = []
    since = 0.0
    previous: dict[str, Any] | None = None
    for shot_id, a, b, scene in merged:
        if previous is None or previous["world"] != scene["world"] or out and out[-1]["from"] + out[-1]["durationInFrames"] < a - fps:
            since = a / fps                      # the world comes (back) on screen: its simulation starts
        prev = previous["focus"] if previous and previous["world"] == scene["world"] else scene["focus"]
        out.append({"id": f"sim-{shot_id}", "kind": "graphic", "from": a, "durationInFrames": b - a,
                    "graphic": {**scene, "at": round(a / fps, 3), "since": round(since, 3), "prev": prev}})
        previous = scene
    # the ring's events on the voice: the brake when a line first points at it, the cars standing still when a line
    # first speaks of the jam (SimScene paces the simulation's clock to land them there)
    for group in out:
        g = group["graphic"]
        if g["world"] == "anillo":
            run = [o["graphic"] for o in out if o["graphic"]["since"] == g["since"] and o["graphic"]["world"] == "anillo"]
            g["cues"] = {name: next(r["at"] for r in run if r["overlay"] == name) for name in ("brake", "jam")
                         if any(r["overlay"] == name for r in run)}
    return out
