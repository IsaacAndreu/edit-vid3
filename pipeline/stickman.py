"""Stickman videos: the whole video drawn in code, no footage (canales/<canal>.yaml → visual: {style: stickman}).

Like the stickman explainers of psychology and money channels: line-drawn figures on paper, one or two red props,
a few words of the line in capitals at the bottom. Nothing is searched or downloaded — the footage stages leave empty
results (`skip`) — and in the edit (timeline.py) every shot gets a scene: the LLM picks it from a fixed vocabulary
(poses, faces, props, places) for each line of the script, and remotion/components/graphics/Stickman.tsx draws and
animates it. Graphics, chapter cards and figures go on top as in any other video. Scenes cached in work/<slug>/stickman.json.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .context import RunContext
from .sourcing.common import key

POSES = ("stand", "walk", "run", "point", "think", "cheer", "sad", "sit", "talk", "shrug", "fall", "hold", "give", "wave",
         "facepalm", "jump")
FACES = ("neutral", "happy", "sad", "angry", "surprised", "worried")
PROPS = ("money", "coin", "phone", "house", "car", "heart", "broken-heart", "clock", "chart-up", "chart-down", "book",
         "gift", "lightbulb", "question", "warning", "trophy", "bomb", "bag", "brain", "lock", "key", "calendar", "fire",
         "star", "speech", "chain", "door", "ladder", "mountain", "target", "box", "pill", "laptop", "bed", "food")
PLACES = ("plain", "room", "street", "office", "stage", "nature", "night", "city")
DANGLING = {"que", "de", "del", "tu", "tus", "su", "sus", "el", "la", "los", "las", "un", "una", "y", "o", "a", "en", "por",
            "para", "con", "sin", "mi", "se", "lo", "le", "al", "es", "más", "muy"}
SKIP = ("sourcing", "analysis", "judge", "ingest", "people", "fallback", "coldopen")
VERSION = 2

SYSTEM = f"""
Eres el animador de un canal de vídeos explicativos con monigotes (stickman) dibujados con líneas sobre papel. Te paso
las frases del guion, numeradas, una por plano. Para CADA plano diseña una escena que se entienda sin sonido, con este
vocabulario y nada más:
- "place": {", ".join(PLACES)}
- "actors": 1-3 monigotes: {{"pose": {"|".join(POSES)}, "face": {"|".join(FACES)}, "x": 0.15-0.85 (posición),
  "facing": "left"|"right", "label": "quién es en 1-2 palabras si importa (TÚ, JEFE, ELLA…) o ''", "size": 0.8-1.3}}
- "prop": un objeto rojo que resume la idea o null: {{"icon": {"|".join(PROPS)}, "x": 0.1-0.9, "y": 0.2-0.8,
  "label": "0-2 palabras o ''", "held": true si lo sostiene el monigote más cercano}}
- "bubble": un bocadillo de 1-4 palabras que dice alguien o ''
- "caption": 2-7 palabras LITERALES de la frase, las que más pesan, o '' (no en todos los planos)
Varía MUCHO: no repitas la misma pose, el mismo objeto ni el mismo lugar en planos seguidos; usa al menos 4 lugares
distintos en el vídeo y cambia de lugar cuando cambia la idea; pon 2 monigotes (alguien con quien hablar, el jefe, la
pareja, un amigo) en al menos un tercio de los planos; prefiere acciones (dar, señalar, caminar, caerse, celebrar) a
estar de pie. Una idea visual por plano, simple. El "caption" es una idea completa (no termina en «que», «de», «tu»…).
Devuelve SOLO JSON: {{"scenes": [{{"n": 1, "place": "...", "actors": [...], "prop": {{...}} | null, "bubble": "", "caption": ""}}]}}
""".strip()


def active(ctx: RunContext) -> bool:
    return str(ctx.section("visual").get("style") or "").lower() == "stickman"


def drawn(ctx: RunContext) -> bool:
    """The whole video is drawn in code (stickman or simulation): no footage to search, download or measure."""

    from . import simulacion

    return active(ctx) or simulacion.active(ctx)


def skip(ctx: RunContext, stage: str) -> None:
    """A footage stage of a stickman video: its empty but valid result, without searching or downloading anything."""

    from .schemas import ShotsFile

    print("   Vídeo dibujado en código: sin metraje que buscar")
    if stage in ("sourcing", "analysis"):
        from .schemas import ShotCandidates, ShotScores
        from .sourcing import needs_footage

        folder = ctx.work_dir / ("candidates" if stage == "sourcing" else "scores")
        folder.mkdir(parents=True, exist_ok=True)
        for shot in ShotsFile.model_validate(ctx.read_json("shots.json")).shots:
            if needs_footage(shot):
                data = (ShotCandidates(shotId=shot.id, specHash="stickman", queries={}, candidates=[]) if stage == "sourcing"
                        else ShotScores(shotId=shot.id, inputsHash="stickman", needed=min(5.0, max(0.1, shot.duration)),
                                        prompts=[], options=[]))
                (folder / f"{shot.id}.json").write_text(data.model_dump_json(by_alias=True, exclude_none=True), encoding="utf-8")
        (folder / "_summary.json").write_text(json.dumps({"stickman": True}), encoding="utf-8")
    elif stage == "judge":
        ctx.write_json("selection.json", {"slug": ctx.slug, "selections": [], "stats": {}})
    elif stage == "ingest":
        (ctx.work_dir / "media").mkdir(parents=True, exist_ok=True)
        (ctx.work_dir / "media" / "_ingest.json").write_text(json.dumps({"slug": ctx.slug, "media": []}), encoding="utf-8")
    elif stage == "people":
        ctx.write_json("people.json", {"slug": ctx.slug, "people": []})
    elif stage == "fallback":
        ctx.write_json("fallback.json", {"slug": ctx.slug, "items": []})
    elif stage == "coldopen":
        ctx.write_json("coldopen.json", {"slug": ctx.slug})


def _pick(value: Any, allowed: tuple[str, ...], default: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in allowed else default


def _num(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return round(min(hi, max(lo, float(value))), 3)
    except (TypeError, ValueError):
        return default


def _words(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split()[:limit])


def clean(scene: dict[str, Any], line: str) -> dict[str, Any]:
    """A scene the component can draw: only the vocabulary, positions in range, captions said in the line."""

    actors = []
    for a in (scene.get("actors") or [])[:3]:
        if isinstance(a, dict):
            actors.append({"pose": _pick(a.get("pose"), POSES, "stand"), "face": _pick(a.get("face"), FACES, "neutral"),
                           "x": _num(a.get("x"), 0.12, 0.88, 0.5), "facing": "left" if a.get("facing") == "left" else "right",
                           "label": _words(a.get("label"), 2).upper()[:14], "size": _num(a.get("size"), 0.8, 1.3, 1.0)})
    if not actors:
        actors = [{"pose": "talk", "face": "neutral", "x": 0.5, "facing": "right", "label": "", "size": 1.0}]
    prop = scene.get("prop") if isinstance(scene.get("prop"), dict) else None
    if prop and str(prop.get("icon") or "") in PROPS:
        prop = {"icon": prop["icon"], "x": _num(prop.get("x"), 0.1, 0.9, 0.7), "y": _num(prop.get("y"), 0.2, 0.8, 0.45),
                "label": _words(prop.get("label"), 2).upper()[:16], "held": bool(prop.get("held"))}
    else:
        prop = None
    spoken = set(re.findall(r"\w+", line.lower()))
    caption = _words(scene.get("caption"), 7)
    words = re.findall(r"\w+", caption.lower())
    if caption and (not set(words) <= spoken or len(words) < 2 or words[-1] in DANGLING):
        caption = ""                     # only the line's own words, and a whole idea («ZAPATILLAS QUE» is not one)
    return {"type": "stickman", "place": _pick(scene.get("place"), PLACES, "plain"), "actors": actors, "prop": prop,
            "bubble": _words(scene.get("bubble"), 4), "caption": caption.upper()}


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    """shot id → scene, from the LLM in batches of 40 lines (cached by the lines themselves)."""

    from .llm import complete_json

    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    cache = ctx.work_dir / "stickman.json"
    digest = key(VERSION, lines)
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if saved.get("key") == digest:
            return saved["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(lines), 40):
        batch = lines[start:start + 40]
        listing = "\n".join(f"[{n}] {text}" for n, (_, text) in enumerate(batch, 1))
        try:
            result = complete_json(ctx, stage="stickman", section="planner", system=SYSTEM, user=listing,
                                   max_tokens=350 * len(batch))
            found = {int(s.get("n", 0)): s for s in result.get("scenes", []) if isinstance(s, dict)}
        except Exception as error:      # a plain talking figure rather than no video
            print(f"   Escenas de monigotes no disponibles ({str(error)[:100]}): figura hablando")
            found = {}
        for n, (shot_id, text) in enumerate(batch, 1):
            out[shot_id] = clean(found.get(n) or {}, text)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


def groups(ctx: RunContext, shots: list[Any], fps: int, taken: list[Any]) -> list[dict[str, Any]]:
    """A full-screen stickman scene for every shot nothing else covers (graphics, cards and figures stay on top)."""

    def covered(a: int, b: int) -> bool:
        return any(g.from_ < b and a < g.from_ + g.durationInFrames for g in taken)

    todo = []
    for shot in shots:
        a, b = shot.from_, shot.from_ + shot.durationInFrames
        if shot.type != "endscreen" and not covered(a, b):
            todo.append((shot, a, b))
    found = scenes(ctx, [s for s, _, _ in todo])
    palette = "paper" if str(ctx.section("visual").get("palette") or "color") == "paper" else "color"
    return [{"id": f"stickman-{shot.id}", "kind": "graphic", "from": a, "durationInFrames": b - a,
             "graphic": {**found[shot.id], "seed": n, "palette": palette}} for n, (shot, a, b) in enumerate(todo)]
