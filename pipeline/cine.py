"""«Cine de monigotes»: animated short films with stickmen, drawn in code (canales/<canal>.yaml → visual: {style: cine}).

Three modes (`visual.mode`), the three formats that are working on YouTube with this look:
- `y-si`: «¿Y si…?» films (Ifverse, IFOLOGY): one impossible premise followed to the end with real science, a
  counter on screen (10x, 52 AÑOS, 00:00:05), the twist at the end. 8-16 min, horizontal.
- `disciplina`: short films about discipline, temptation and starting again (Day One Films, Monk Mode Films): few
  lines, slow, backlit silhouettes, «DÍA 1», the hero alone in his room at night. 2-5 min, horizontal.
- `reglas`: the vertical survival thriller in second person: «Imagina que…», a HUD with the day and a clock that
  moves on, 3-4 rules on stickers, a phone, a peephole, the threat shown more than told, a choice at the end and
  «SIGUE PARA EL DÍA 2». 60-90 s, 1080x1920.

Nothing is searched or downloaded (the footage stages leave empty results, like stickman and simulation videos). In
the edit every line of the script gets a shot: the LLM picks it from a fixed vocabulary (set, shot, light, move,
actors, prop, rule, phone, counter, title, choice), knowing the whole story so the HUD clock moves forward, the rules
are numbered and the threat escalates. remotion/components/graphics/CineScene.tsx draws it. The words of each line
come with their frames: the captions go word by word, the key words in the accent colour. Cached in
work/<slug>/cine.json.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .context import RunContext
from .sourcing.common import key
from .stickman import FACES, POSES, PROPS, _num, _pick, _words

MODES = ("y-si", "disciplina", "reglas")
SETS = ("bedroom", "hallway", "door", "living", "street", "city", "above", "rooftop", "office", "gym", "desk", "mirror",
        "void", "space", "lab", "classroom", "nature", "rain", "stairs", "hospital")
SHOTS = ("wide", "medium", "close", "pov-phone", "peephole", "over", "above", "silhouette")
LIGHTS = ("warm", "cold", "dark", "red", "dawn", "day", "neon")
MOVES = ("still", "push", "pull", "pan-left", "pan-right", "shake")
WHO = ("hero", "other", "double", "shadow")
CINE_FACES = (*FACES, "determined", "scared")
MARKS = ("scar", "cap", "hood", "scarf", "none")
VERSION = 1

LANG_WORDS = {   # on-screen words in the video's language
    "es": {"rule": "REGLA", "day": "DÍA", "comment": "COMENTA ABAJO", "follow": "SIGUE PARA EL DÍA {n}"},
    "en": {"rule": "RULE", "day": "DAY", "comment": "COMMENT BELOW", "follow": "FOLLOW FOR DAY {n}"},
    "de": {"rule": "REGEL", "day": "TAG", "comment": "KOMMENTIERE UNTEN", "follow": "FOLGE FÜR TAG {n}"},
    "pt": {"rule": "REGRA", "day": "DIA", "comment": "COMENTE ABAIXO", "follow": "SIGA PARA O DIA {n}"},
    "fr": {"rule": "RÈGLE", "day": "JOUR", "comment": "COMMENTE EN DESSOUS", "follow": "ABONNE-TOI POUR LE JOUR {n}"},
    "it": {"rule": "REGOLA", "day": "GIORNO", "comment": "COMMENTA SOTTO", "follow": "SEGUI PER IL GIORNO {n}"},
}

MODE_GUIDE = {
    "y-si": """
Es un vídeo «¿Y SI…?»: una premisa imposible seguida hasta el final, con ciencia real. Varía mucho los decorados (laboratorio,
espacio, ciudad, calle, su cuarto) según lo que cuenta la frase; el héroe vive la premisa. Cuando la frase da una cifra
que mide la premisa (velocidad, años, segundos, veces), "counter" con ella. Al empezar cada parte nueva, "title" corto
(2-4 palabras). Usa "shadow" para lo que amenaza; "other" para la gente normal. Planos variados: muchos medium y close
para las reacciones, wide para enseñar el mundo, above para el caos de la ciudad.""",
    "disciplina": """
Es un cortometraje de DISCIPLINA y superación: lento, emotivo. El héroe solo, de noche, en su cuarto, su escritorio, el
gimnasio, una calle mojada; la tentación (el móvil, la cama, la pantalla) es "shadow" o "pov-phone"; los momentos de
decisión en "silhouette" a contraluz o "close" de la cara. Luz "dark" o "cold" para la caída, "dawn" o "warm" para la
subida. "title" solo en 2-3 momentos clave («DÍA 1», «365 DÍAS», el tema del vídeo). Movimientos lentos: push y pull.""",
    "reglas": """
Es un thriller VERTICAL en segunda persona («Imagina que…»): el espectador ES el héroe. Pon "hud" en TODAS las escenas:
el día ("day": número) y la hora ("clock": "11:58 PM" o "23:58" según el idioma), que AVANZA a lo largo del vídeo y se
dice en la frase si la voz la dice. Cada regla, la primera vez que se dice, va en "rule" (número y texto corto en
MAYÚSCULAS). POV: el móvil con mensajes ("pov-phone" con "phone"), la mirilla ("peephole": quien está fuera se
acerca), lo que se ve por una puerta, una ventana. La amenaza se enseña ("shadow", "double": alguien igual que tú) más
que se cuenta. Planos de 1,5-3 s, muy variados, close de la cara para las reacciones. La última frase: "choice" con la
pregunta («¿ABRES?») y dos opciones malas (la primera en verde, la segunda en rojo).""",
}

SYSTEM = """
Eres el director de animación de un canal de cortos animados con monigotes (stickmen planos, cabeza grande, contorno
grueso) en decorados oscuros iluminados como una película. Te paso el guion entero, una frase numerada por plano.
Diseña UN plano por frase que se entienda sin sonido y siga la historia (el mismo sitio mientras dure la escena; la
amenaza crece), con este vocabulario y nada más:
- "set": {sets}
- "shot": {shots}  (pov-phone = el móvil en tus manos; peephole = la mirilla; over = por encima del hombro del héroe;
  above = la ciudad desde arriba; silhouette = a contraluz)
- "light": {lights}  · "move": {moves}
- "actors": 0-3: {{"pose": {poses}, "face": {faces}, "x": 0.15-0.85, "facing": "left"|"right",
  "who": {who}, "label": "0-2 palabras o ''", "size": 0.8-1.3}}  (el héroe es "hero"; siempre el mismo)
- "prop": un objeto o null: {{"icon": {props}, "x": 0.1-0.9, "y": 0.2-0.8, "held": true si lo lleva alguien}}
- "phone": solo con pov-phone: {{"from": "quién escribe", "messages": ["mensajes cortos, literales si la voz los lee"],
  "typing": true si alguien está escribiendo}}
- "rule": {{"n": número, "text": "LA REGLA EN 2-5 PALABRAS"}} o null
- "hud": {{"day": número, "clock": "la hora"}} o null
- "counter": {{"label": "1-2 palabras", "value": "la cifra corta: 10x, 52 AÑOS, 00:00:05"}} o null
- "title": "2-4 palabras en MAYÚSCULAS" o ""
- "choice": {{"question": "¿…?", "a": "opción 1", "b": "opción 2"}} o null (solo al final)
- "keys": 1-2 palabras LITERALES de la frase que pesan más (se resaltan en el subtítulo)
{mode}
No repitas el mismo plano y decorado en tres frases seguidas. Los textos en pantalla, en el idioma del guion.
Devuelve SOLO JSON: {{"scenes": [{{"n": 1, "set": "...", "shot": "...", "light": "...", "move": "...", "actors": [...],
"prop": null, "phone": null, "rule": null, "hud": null, "counter": null, "title": "", "choice": null, "keys": []}}]}}
""".strip()


def active(ctx: RunContext) -> bool:
    return str(ctx.section("visual").get("style") or "").lower() == "cine"


def mode(ctx: RunContext) -> str:
    value = str(ctx.section("visual").get("mode") or "y-si").lower()
    return value if value in MODES else "y-si"


def _lang(ctx: RunContext) -> str:
    return str(ctx.section("align").get("language", "es"))[:2]


def writing(ctx: RunContext) -> str:
    """For the script draft (organizar.draft_script): how this format's scripts are written."""

    if not active(ctx):
        return ""
    own = str(ctx.section("visual").get("writing") or "").strip()
    base = {
        "y-si": "ESTE CANAL SON PELÍCULAS ANIMADAS «¿Y SI…?» CON MONIGOTES: una premisa imposible («¿y si tus reflejos "
                "fueran 10 veces más rápidos?») seguida hasta el final a través de UN personaje. Arranca con la premisa en "
                "la primera frase y lo que tendría de increíble; luego la ciencia real que lo hace posible o imposible "
                "(cita estudios o datos ciertos); luego las consecuencias en su vida, cada vez más grandes y raras (el "
                "primer día, el primer problema, cuando el mundo se entera); el giro final que nadie espera; y una "
                "pregunta al espectador. Cada frase, algo que se pueda ENSEÑAR. Frases cortas, en presente.",
        "disciplina": "ESTE CANAL SON CORTOS ANIMADOS SOBRE DISCIPLINA Y SUPERACIÓN CON UN MONIGOTE: 2-5 minutos, pocas "
                      "frases (una cada 3-5 segundos), muy visuales, emotivas, sin sermones. Una historia: el personaje "
                      "atrapado (el móvil, la cama, la comodidad), el momento en que toca fondo, la decisión («día 1»), "
                      "la lucha diaria (recaídas incluidas) y el cambio. Habla de «él» o de «tú». Frases de 4-12 "
                      "palabras. Nada de títulos copiados de otros canales: una historia propia.",
        "reglas": "ESTE CANAL SON THRILLERS VERTICALES DE 60-90 SEGUNDOS EN SEGUNDA PERSONA CON MONIGOTES. Empieza con "
                  "«Imagina que…» y una hora concreta en los 3 primeros segundos; 3-4 REGLAS cortas (imperativas: «No "
                  "abras la puerta»), cada una se cumple o se pone a prueba en pantalla; una amenaza que crece y se ENSEÑA "
                  "(lo que ves por la mirilla, por la ventana, en el móvil); un giro que hace imposible una regla; y un "
                  "final con una elección donde las dos opciones son malas («¿Abres la puerta?»). Una pregunta nueva "
                  "cada ~10 s. La hora avanza y se dice. 20-30 frases cortas. Escribe las horas como se dicen.",
    }[mode(ctx)]
    return base + ("\n" + own if own else "")


def _clean_actor(a: dict[str, Any]) -> dict[str, Any]:
    return {"pose": _pick(a.get("pose"), POSES, "stand"), "face": _pick(a.get("face"), CINE_FACES, "neutral"),
            "x": _num(a.get("x"), 0.12, 0.88, 0.5), "facing": "left" if a.get("facing") == "left" else "right",
            "label": _words(a.get("label"), 2).upper()[:14], "size": _num(a.get("size"), 0.8, 1.3, 1.0),
            "who": _pick(a.get("who"), WHO, "hero")}


def clean(scene: dict[str, Any], line: str, video_mode: str) -> dict[str, Any]:
    """A shot the component can draw: only the vocabulary, positions in range."""

    shot = _pick(scene.get("shot"), SHOTS, "medium")
    out: dict[str, Any] = {"type": "cine", "mode": video_mode, "set": _pick(scene.get("set"), SETS, "bedroom"),
                           "shot": shot, "light": _pick(scene.get("light"), LIGHTS, "dark"),
                           "move": _pick(scene.get("move"), MOVES, "push")}
    actors = [_clean_actor(a) for a in (scene.get("actors") or [])[:3] if isinstance(a, dict)]
    if not actors and shot not in ("pov-phone", "above"):
        actors = [_clean_actor({"pose": "stand", "who": "hero", "face": "neutral"})]
    if actors and shot != "peephole" and not any(a["who"] == "hero" for a in actors):
        pass                       # a shot of someone else (the threat, a crowd): fine
    out["actors"] = actors
    prop = scene.get("prop") if isinstance(scene.get("prop"), dict) else None
    out["prop"] = ({"icon": prop["icon"], "x": _num(prop.get("x"), 0.1, 0.9, 0.7), "y": _num(prop.get("y"), 0.2, 0.8, 0.45),
                    "label": "", "held": bool(prop.get("held"))} if prop and str(prop.get("icon") or "") in PROPS else None)
    phone = scene.get("phone") if isinstance(scene.get("phone"), dict) else None
    if shot == "pov-phone":
        messages = [_words(m, 14) for m in (phone or {}).get("messages") or [] if str(m).strip()][:4]
        out["phone"] = {"from": _words((phone or {}).get("from"), 3)[:24], "messages": messages or [_words(line, 10)],
                        "typing": bool((phone or {}).get("typing"))}
    rule = scene.get("rule") if isinstance(scene.get("rule"), dict) else None
    if rule and str(rule.get("text") or "").strip():
        try:
            n = max(1, min(9, int(rule.get("n") or 1)))
        except (TypeError, ValueError):
            n = 1
        out["rule"] = {"n": n, "text": _words(rule["text"], 6).upper()[:40]}
    hud = scene.get("hud") if isinstance(scene.get("hud"), dict) else None
    if hud:
        out["hud"] = {"day": str(hud.get("day") or "").strip()[:4], "clock": str(hud.get("clock") or "").strip()[:9]}
    counter = scene.get("counter") if isinstance(scene.get("counter"), dict) else None
    if counter and str(counter.get("value") or "").strip():
        out["counter"] = {"label": _words(counter.get("label"), 2).upper()[:16], "value": str(counter["value"]).strip()[:12]}
    title = _words(scene.get("title"), 5).upper()[:32]
    if title:
        out["title"] = title
    choice = scene.get("choice") if isinstance(scene.get("choice"), dict) else None
    if choice and str(choice.get("question") or "").strip():
        out["choice"] = {"question": _words(choice["question"], 6).upper(), "a": _words(choice.get("a"), 4).upper(),
                         "b": _words(choice.get("b"), 4).upper(), "comment": ""}
    spoken = re.findall(r"\w+", line.lower())
    out["keys"] = [k for k in (re.sub(r"[^\w]", "", str(x).lower()) for x in (scene.get("keys") or [])[:2]) if k in spoken]
    return out


def scenes(ctx: RunContext, shots: list[Any]) -> dict[str, dict[str, Any]]:
    """shot id → scene, from the LLM with the whole script in view (cached by the lines themselves)."""

    from .llm import complete_json

    video_mode = mode(ctx)
    lines = [(s.id, " ".join(s.text.split())) for s in shots]
    cache = ctx.work_dir / "cine.json"
    digest = key(VERSION, video_mode, lines)
    try:
        saved = json.loads(cache.read_text("utf-8"))
        if saved.get("key") == digest:
            return saved["scenes"]
    except (OSError, ValueError, KeyError):
        pass
    guide = MODE_GUIDE[video_mode] + ("\n" + str(ctx.section("visual").get("guide") or "").strip()
                                      if ctx.section("visual").get("guide") else "")
    system = SYSTEM.format(sets="|".join(SETS), shots="|".join(SHOTS), lights="|".join(LIGHTS), moves="|".join(MOVES),
                           poses="|".join(POSES), faces="|".join(CINE_FACES), who="|".join(WHO), props="|".join(PROPS),
                           mode=guide)
    out: dict[str, dict[str, Any]] = {}
    story = "\n".join(f"[{n}] {text}" for n, (_, text) in enumerate(lines, 1))
    for start in range(0, len(lines), 40):
        batch = lines[start:start + 40]
        user = (f"EL GUION ENTERO (para la historia):\n{story}\n\n" if len(lines) > 40 else "") + \
            f"DISEÑA LOS PLANOS {start + 1}-{start + len(batch)}:\n" + \
            "\n".join(f"[{start + n}] {text}" for n, (_, text) in enumerate(batch, 1))
        try:
            result = complete_json(ctx, stage="cine", section="planner", system=system, user=user,
                                   max_tokens=420 * len(batch))
            found = {int(s.get("n", 0)): s for s in result.get("scenes", []) if isinstance(s, dict)}
        except Exception as error:      # a plain shot of the hero rather than no video
            print(f"   Planos de cine no disponibles ({str(error)[:100]}): el héroe en su cuarto")
            found = {}
        for n, (shot_id, text) in enumerate(batch, start + 1):
            out[shot_id] = clean(found.get(n) or {}, text, video_mode)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": digest, "scenes": out}, ensure_ascii=False), encoding="utf-8")
    return out


def _clock_words(lang: str) -> dict[str, str]:
    return LANG_WORDS.get(lang, LANG_WORDS["es"])


def groups(ctx: RunContext, shots: list[Any], fps: int, taken: list[Any], words: Any = None) -> list[dict[str, Any]]:
    """A full-screen shot for every line nothing else covers, with the words it says (captions word by word), the HUD
    carried from shot to shot, the rules numbered once, the hero's mark and the end card."""

    def covered(a: int, b: int) -> bool:
        return any(g.from_ < b and a < g.from_ + g.durationInFrames for g in taken)

    todo = [(shot, shot.from_, shot.from_ + shot.durationInFrames) for shot in shots
            if shot.type != "endscreen" and not covered(shot.from_, shot.from_ + shot.durationInFrames)]
    if not todo:
        return []
    found = scenes(ctx, [s for s, _, _ in todo])
    visual = ctx.section("visual")
    video_mode = mode(ctx)
    lang = _lang(ctx)
    say = _clock_words(lang)
    hero = {"mark": _pick(visual.get("mark"), MARKS, "scar"), "color": str(visual.get("mark_color") or "#e5322d")}
    accent = str(visual.get("accent") or ctx.section("brand").get("accent") or "#ffd400")
    captions = str(visual.get("captions") or ("palabra" if video_mode == "reglas" else "no")).lower()
    spoken = [(round(w.start * fps), w.text.strip()) for w in (words.words if words is not None else []) if w.text.strip()]
    hud: dict[str, str] = {}
    rules_seen: set[int] = set()
    out = []
    for n, (shot, a, b) in enumerate(todo):
        g = dict(found[shot.id])
        if video_mode == "reglas":                   # the HUD stays and moves on: a shot without one keeps the last
            new = g.get("hud") or {}
            if new.get("day"):
                hud["day"] = f"{say['day']} {new['day']}" if new["day"].isdigit() else new["day"].upper()
            if new.get("clock"):
                hud["clock"] = new["clock"].upper()
            g["hud"] = dict(hud) if hud else None
        else:
            g.pop("hud", None)
        rule = g.get("rule")
        if rule:
            if rule["n"] in rules_seen:              # a rule said again: no new sticker
                g.pop("rule")
            else:
                rules_seen.add(rule["n"])
                rule["word"] = say["rule"]
        if g.get("choice"):
            g["choice"]["comment"] = say["comment"]
        keys = set(g.pop("keys", []) or [])
        line_words = [(f, t) for f, t in spoken if a <= f < b]
        if captions == "palabra":
            g["words"] = [{"t": t, "f": f - a, "key": re.sub(r"[^\w]", "", t.lower()) in keys} for f, t in line_words]
        elif captions == "clave" and keys:              # only the key words, as they are said
            g["words"] = [{"t": t, "f": f - a, "key": True} for f, t in line_words if re.sub(r"[^\w]", "", t.lower()) in keys]
        g.update({"hero": hero, "accent": accent, "seed": n})
        out.append({"id": f"cine-{shot.id}", "kind": "graphic", "from": a, "durationInFrames": b - a, "graphic": g})
    if video_mode == "reglas" and out and visual.get("end_card", True) is not False:
        last = out[-1]
        hold = round(float(visual.get("end_seconds", 2.0)) * fps)
        day = re.sub(r"\D", "", hud.get("day", "1")) or "1"
        out.append({"id": "cine-end", "kind": "graphic", "from": last["from"] + last["durationInFrames"],
                    "durationInFrames": hold, "graphic": {
                        "type": "cine", "mode": video_mode, "set": "void", "shot": "wide", "light": "dark",
                        "end": {"series": str(visual.get("series_name") or "")[:40], "title": hud.get("day", f"{say['day']} 1"),
                                "sub": hud.get("clock", ""), "follow": say["follow"].format(n=int(day) + 1)}}})
    return out


def moments(groups: list[Any], fps: int, count: int) -> list[float]:
    """Seconds for thumbnails: the close-ups and the shots with a title, a rule or a counter first."""

    scored = []
    for group in groups:
        g = (group.graphic if hasattr(group, "graphic") else group.get("graphic")) or {}
        if g.get("type") != "cine" or g.get("end") or g.get("shot") == "pov-phone":
            continue
        start = group.from_ if hasattr(group, "from_") else group["from"]
        dur = group.durationInFrames if hasattr(group, "durationInFrames") else group["durationInFrames"]
        score = (2 if g.get("shot") == "close" else 1) + (1 if g.get("title") or g.get("counter") or g.get("rule") else 0) \
            + (1 if any(a.get("who") == "shadow" for a in g.get("actors") or []) else 0)
        scored.append((score, (start + dur * 0.6) / fps))
    return [t for _, t in sorted(scored, key=lambda x: -x[0])[:count]]
