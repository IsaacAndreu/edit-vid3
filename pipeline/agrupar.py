"""Ideas instead of 3-second pieces (planner.ideas, off by default; bloque 1 of prompts/motor-punteria-prompt.md).

The planner cuts the narration every ~3 s and each piece used to be searched, scored and judged on its own: half
of them are half sentences («en París. Pero detrás», «con veintisiete años,») with nothing to search for, they stay
empty, and the empty ones got covered with whatever clip was at hand. Here, after the planner has described every
shot, one more pass of the language model groups the consecutive shots that say the same thing into an IDEA (one or
two sentences, 4-12 s) and labels it:

- literal: that very thing must be seen («una abeja en el podio», «Biles se sale del tapiz dos veces»);
- ambiente: no image of its own («dejó el instituto», «mide un metro cuarenta y dos»): footage of who or what it is
  about, of that time or event, is fine;
- rotulo: a chapter title or the goodbye read aloud («SECRETO 4: …», «suscríbete»): nothing is searched.

For each idea it also writes who must and who must not be on screen, the time or event, one short line for the
screen and the facts that can be labelled (place, year, age, score). The cut itself does not change: the shots stay
as they are, each one carries its idea (Shot.idea), and the later stages search, judge and cut by idea.

The answer is checked, never trusted: ideas are made of consecutive shots, never cross a chapter start, never last
more than MAX_SECONDS; whatever the model leaves out becomes an idea of its own, labelled by simple rules.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

MAX_SECONDS = 14.0                 # an idea longer than this is split (the model is asked for 4-12 s)
BATCH = 40                         # shots per call

SYSTEM = """
Eres el montador jefe de un canal de YouTube de documentales. Recibes los planos ya cortados de un vídeo (unos 3 s
cada uno, con lo que la voz dice en cada uno y lo que se pensó enseñar). Tu trabajo es agruparlos en IDEAS y decir,
para cada idea, qué tiene que verse.

Por qué: hasta ahora cada trozo de 3 s se buscaba solo, y muchos trozos son media frase sin nada que buscar. Un
montador piensa por ideas: «aquí cuento su caída en Río», «aquí su infancia», y para cada idea elige un material y
lo corta en varios planos seguidos. Si la idea no tiene imagen propia, enseña a la persona de la que se habla en ese
momento de su vida; si la tiene, enseña exactamente eso o nada.

Una IDEA son planos SEGUIDOS que cuentan lo mismo: normalmente una frase o dos, de 4 a 12 segundos. Un título de
capítulo o un cambio claro de tema empiezan idea nueva.

Etiqueta de cada idea:
- "literal": lo que se cuenta se grabó y TIENE que verse eso: una competición concreta, una caída, un gol, una
  boda, un juicio, una rueda de prensa, una escena del juego, un lugar nombrado. Si no está, mejor otra cosa sobria
  que un clip de otra cosa.
  Ej.: «en plena ceremonia de medallas bajó del podio de un salto» (gimnasia); «el jurado le declaró culpable en
  Miami en 1979» (crimen); «la misión del atraco al banco de Vice City» (GTA); «la caída del Muro en noviembre de
  1989» (historia).
- "ambiente": la frase no tiene imagen propia (una decisión, un sentimiento, el colegio, la familia, el dinero, una
  edad, una altura, una lista de títulos): vale material de la persona o el tema del que se habla, de esa época o
  de ese suceso.
  Ej.: «con unos quince años dejó el instituto»; «sus padres nunca dejaron de creer en ella»; «nadie sabía qué
  había pasado aquella noche»; «muchos jugadores cometen este error al empezar».
- "rotulo": la voz lee un título o una fórmula fija: «SECRETO 4: SUS PADRES SON SUS ABUELOS», «ERROR NÚMERO 3»,
  «suscríbete», «déjamelo en los comentarios». No se busca nada; va en pantalla como texto.

Además, para cada idea:
- "mustShow": quién TIENE que salir (nombres tal como los dice el guion), [] si nadie en concreto.
- "mustNotShow": quién NO puede salir aunque se le parezca o salga en los mismos vídeos (la rival de la que no se
  habla, otro gimnasta, otro acusado), [] si nada.
- "era": la época o el suceso concreto («Mundial de Amberes 2013», «infancia en Spring, Texas, años 2000»,
  «juicio de Miami 1979»), null si da igual. Sirve para no poner París 2024 cuando se habla de 2013.
- "screenLine": UNA línea corta para escribir en pantalla (máx. 60 caracteres), con el dato o la palabra clave
  entre asteriscos; si el dato tiene fuente, la fuente delante («Rockstar: *sin mapa* hasta 2026», «*11* medallas
  olímpicas»). Es lo que el espectador lee mientras la voz lo dice: corta, sin repetir la frase entera. null si no
  aporta.
- "facts": lo que se puede rotular sobre la imagen: lugar, año, edad, nota, cifra (como lo dice el guion), [].
- "summary": de qué va la idea en una frase.

Devuelve SOLO JSON:
{"ideas": [{"shots": ["s001", "s002"], "kind": "literal", "summary": "...", "mustShow": ["Simone Biles"],
            "mustNotShow": [], "era": "Juegos de Río 2016", "screenLine": "4 oros en Río", "facts": ["Río 2016"]}]}

Cada plano de la lista va en una idea y solo en una, en orden.
"""

_ROTULO = re.compile(r"^\s*(secreto|cap[ií]tulo|parte|error|n[uú]mero|paso|truco|mito|raz[oó]n)\s*(n[uú]mero\s*)?\d+\b",
                     re.I)
_GOODBYE = re.compile(r"suscr[ií]b|coment(a|arios)|dale (a )?like|campanita|nos vemos en el pr[oó]ximo", re.I)


def guess_kind(shot: dict[str, Any]) -> str:
    """The label of a shot the model left out: simple rules, on the safe side."""

    text = str(shot.get("text") or "")
    if _ROTULO.match(text) or _GOODBYE.search(text):
        return "rotulo"
    broll = shot.get("broll") or {}
    return "literal" if broll.get("moment") else "ambiente"


def _line(shot: dict[str, Any]) -> str:
    broll = shot.get("broll") or {}
    seconds = float(shot.get("end", 0)) - float(shot.get("start", 0))
    chapter = f" [CAPÍTULO: {shot['chapterTitle']}]" if shot.get("chapterTitle") else ""
    return (f"{shot['id']} ({seconds:.1f} s){chapter}: «{shot.get('text', '')}»"
            + (f" — pensado: {broll.get('visualIntent')}" if broll.get("visualIntent") else "")
            + (f" — momento: {broll.get('moment')}" if broll.get("moment") else ""))


def _clean(items: Any, limit: int, size: int) -> list[str]:
    return [str(x).strip()[:size] for x in (items or []) if str(x).strip()][:limit]


def assign(shots: list[dict[str, Any]], answer: dict[str, Any]) -> list[dict[str, Any]]:
    """Ideas over `shots` from the model's answer, checked: consecutive shots, in order, never across a chapter
    start, never over MAX_SECONDS; any shot left out becomes an idea of its own. Returns one dict per idea with
    its shot ids (no `id` yet: numbered over the whole video by `apply`)."""

    order = [s["id"] for s in shots]
    by_id = {s["id"]: s for s in shots}
    proposed: dict[str, dict[str, Any]] = {}            # first shot id → the model's idea
    taken: set[str] = set()
    for raw in (answer or {}).get("ideas") or []:
        ids = [str(i) for i in raw.get("shots") or [] if str(i) in by_id and str(i) not in taken]
        if not ids:
            continue
        positions = sorted(order.index(i) for i in ids)
        run = [order[positions[0]]]
        for pos in positions[1:]:                      # only the consecutive start of what it listed
            if pos != order.index(run[-1]) + 1:
                break
            run.append(order[pos])
        taken.update(run)
        proposed[run[0]] = {**raw, "shots": run}
    ideas: list[dict[str, Any]] = []
    i = 0
    while i < len(order):
        first = order[i]
        idea = proposed.get(first)
        members = list(idea["shots"]) if idea else [first]
        kept: list[str] = []
        seconds = 0.0
        for sid in members:                            # split at chapter starts and past MAX_SECONDS
            shot = by_id[sid]
            length = float(shot.get("end", 0)) - float(shot.get("start", 0))
            if kept and (shot.get("chapterTitle") or seconds + length > MAX_SECONDS):
                break
            kept.append(sid)
            seconds += length
        if idea and str(idea.get("kind")) in ("literal", "ambiente", "rotulo"):
            ideas.append({
                "shots": kept, "kind": str(idea["kind"]),
                "summary": str(idea.get("summary") or "").strip()[:240],
                "mustShow": _clean(idea.get("mustShow"), 4, 80), "mustNotShow": _clean(idea.get("mustNotShow"), 4, 80),
                "era": (str(idea.get("era")).strip()[:160] or None) if idea.get("era") else None,
                "screenLine": (str(idea.get("screenLine")).strip()[:120] or None) if idea.get("screenLine") else None,
                "facts": _clean(idea.get("facts"), 4, 40),
            })
        else:
            ideas.append({"shots": kept, "kind": guess_kind(by_id[first])})
        rest = [m for m in members if m not in kept]
        if rest and idea:                              # the part split off keeps the model's labels
            proposed[rest[0]] = {**idea, "shots": rest}
        i = order.index(kept[-1]) + 1
    return ideas


def apply(ctx: Any, shots: list[dict[str, Any]], header: str, ask: Any = None) -> dict[str, int]:
    """Group `shots` (the planner's dicts, in order) into ideas and set each one's `idea`. Returns counts per kind.
    `ask(batch_text) -> answer` is the model call (complete_json by default)."""

    from .llm import complete_json

    cfg = ctx.section("planner")

    def call(text: str) -> dict[str, Any]:
        if ask is not None:
            return ask(text)
        try:
            return complete_json(ctx, stage="planner", section="planner", max_tokens=4000, system=SYSTEM,
                                 user=f"{header}\n\nPLANOS:\n{text}")
        except Exception as error:                  # the rules below still label every shot
            print(f"   Ideas: sin respuesta del modelo en un tramo ({str(error)[:120]}): reglas simples")
            return {}

    batches = [shots[i:i + BATCH] for i in range(0, len(shots), BATCH)]
    with ThreadPoolExecutor(max_workers=max(1, int(cfg.get("parallel", 4)))) as pool:
        answers = list(pool.map(lambda batch: call("\n".join(_line(s) for s in batch)), batches))
    counts = {"literal": 0, "ambiente": 0, "rotulo": 0}
    number = 0
    by_id = {s["id"]: s for s in shots}
    for batch, answer in zip(batches, answers):
        for idea in assign(batch, answer):
            number += 1
            members = idea.pop("shots")
            idea = {"id": f"i{number:03d}", **{k: v for k, v in idea.items() if v not in (None, [], "")}}
            counts[idea["kind"]] += 1
            for sid in members:
                by_id[sid]["idea"] = idea
    return counts
