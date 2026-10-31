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
VERSION = 6


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
- "replay": true SOLO en la frase del momento clave que merece verse otra vez (el frenazo que lo empieza todo, el
  primer coche que se para…): la imagen se congela con «PAUSA», se rebobina y se repite a cámara lenta. Como mucho
  dos en todo el vídeo; si no, false.
Reglas: elige el mundo cuyo TEMA es el de la frase (lee bien qué enseña cada uno; una frase sobre atascos en
general no va al mundo de un carril que se cierra ni al de un cruce); si ningún mundo enseña la frase, sigue en el
mundo de la frase anterior; mantén el mismo mundo, foco y parámetros en frases seguidas de la misma
idea (la cámara no salta sin motivo); el panel tiene que mostrar lo que dice la frase en ese momento; no inventes
cifras ni fuentes: solo las que dice la frase. Escribe "title", "stat" y "list" en el idioma del guion.
Devuelve SOLO JSON: {{"scenes": [{{"n": 1, "world": "...", "focus": "...", "overlay": "...", "params": {{}},
"title": "", "stat": null, "source": "", "list": [], "rules": [], "replay": false}}]}}
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
    return {"type": "sim", "world": world, "focus": focus, "overlay": overlay, "params": params,
            "title": _words(scene.get("title"), 5).upper()[:40], "stat": stat, "source": source, "list": items,
            "rules": rules, "replay": scene.get("replay") is True}


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
    digest = key(VERSION, lines, spec, str(ctx.section("visual").get("guide") or ""), director_scenes(ctx))
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
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


REPLAYS = 2
MIN_WORLD = 12.0      # seconds: a world stays at least this long (hora1 jumped ring → merge → crossroads in 10 s)
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
    found = steady(scenes(ctx, [s for s, _, _ in todo]), [(s.id, a, b) for s, a, b in todo], fps,
                   float(ctx.section("visual").get("min_world_seconds", MIN_WORLD)))
    merged: list[list[Any]] = []
    for shot, a, b in todo:
        scene = found[shot.id]
        last = merged[-1] if merged else None
        if last and last[2] == a and last[3] == scene and not scene["title"] and not scene["stat"] and not scene.get("source") \
                and not scene.get("replay"):
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
    sims = [g for g in timeline.get("groups", []) if (g.get("graphic") or {}).get("type") == "sim"]
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
