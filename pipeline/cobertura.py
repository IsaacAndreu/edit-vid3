"""Covering a key event by function (planner.cobertura, off; segunda tanda de puntería, point 1).

The competition's editors tell one event — Messi's goal at the Villamarín — with ten sources, each doing a job: the
action, another angle, the crowd's reaction, the radio commentary, the rival coach's press conference, the aftermath.
We searched «something like this sentence» per shot and got five equivalent takes of the same play. Here, after the
ideas pass, one more model call picks the KEY events of the script (the ones it tells in detail, three to six) and,
for each, the functions that make sense and one search per function in the language that footage exists in. Every
shot of those events gets its function (Shot.coverage):

- the search: the function's query goes first in the shot's queries (one search per function and event, shared by its
  shots: the sourcing groups shots by idea and the first query is the anchor);
- the judge knows what it is judging («this must be the crowd's reaction, not the play»: judge.shot_brief);
- the cut: two shots of the same function in a row are reordered when another function of the event is left
  (`balance`), and a reaction, a testimony or a proof may hold its whole idea as one shot (`hold`, point 3, up to the
  channel's cap and `planner.cobertura_hold_seconds`).

What is left over of an event (more angles, more crowd) feeds the ambient ideas of that passage through the fill-in's
event pool, before any borrowing.
"""

from __future__ import annotations

import re
from typing import Any

ROLES = ("accion", "angulo", "reaccion", "comentario", "testimonio", "despues", "prueba")
HOLD_ROLES = ("reaccion", "testimonio", "prueba", "comentario")

SYSTEM = """
Eres el montador jefe de un canal de YouTube. Te paso las IDEAS de un guion (cada una con sus planos y lo que dice la
voz). Elige los SUCESOS CLAVE: los que el guion cuenta con detalle y merecen verse desde varias fuentes (pocos: de tres
a seis; ninguno si el guion no cuenta sucesos concretos).

Para cada suceso, como haría un montador, decide qué FUNCIONES tiene sentido buscar (no todas existen siempre):
- "accion": la jugada, el momento mismo (la retransmisión);
- "angulo": otro ángulo o la repetición del mismo momento (desde la grada, detrás de la portería, cámara lenta);
- "reaccion": la reacción de la grada, el banquillo, un aficionado, el rival;
- "comentario": la narración original de radio o televisión de ese momento;
- "testimonio": rueda de prensa o entrevista de alguien sobre eso;
- "despues": lo que vino después (la celebración, la salida, la portada del día siguiente);
- "prueba": en vídeos de teoría o de juegos, la pantalla, la escena o el documento que prueba lo que se afirma.
Para cada función escribe UNA búsqueda de YouTube corta, en el IDIOMA en que existe ese material (la narración de un
gol en la radio española, en español; una rueda de prensa en inglés, en inglés), con el suceso y la función
(«Messi gol Betis Villamarín ovación afición», «Messi goal Betis reaction crowd»).

Después asigna a cada PLANO de esos sucesos la función que debe enseñar, siguiendo lo que dice la voz en él: la
acción cuando se cuenta la jugada, la reacción cuando se habla de la grada, el testimonio cuando se cita a alguien.
Nunca dos planos seguidos con la misma función si queda otra del suceso. Marca "sound": true en el plano donde el
guion deja sitio a una voz ajena (la narración del gol, un cántico, la frase del entrenador), y solo ahí.

Devuelve SOLO JSON:
{"events": [{"id": "k1", "name": "gol de Messi al Betis, Villamarín 2023", "ideas": ["i004", "i005"],
             "functions": [{"role": "accion", "query": "..."}, {"role": "reaccion", "query": "..."}]}],
 "shots": [{"id": "s012", "event": "k1", "role": "accion", "sound": false}]}
""".strip()


def _line(idea_id: str, members: list[dict[str, Any]]) -> str:
    idea = members[0].get("idea") or {}
    head = f"[{idea_id}] {idea.get('kind', '')} · {idea.get('summary', '')}"
    if idea.get("era"):
        head += f" · {idea['era']}"
    return head + "\n" + "\n".join(f"  {s['id']}: {s.get('text', '')}" for s in members)


def assign(shots: list[dict[str, Any]], answer: dict[str, Any], max_events: int = 6) -> dict[str, int]:
    """Set `coverage` on the shots the answer names, checked: known events and roles only, a query per function,
    at most `max_events` events. Returns {event id: shots covered}."""

    by_id = {s["id"]: s for s in shots}
    events: dict[str, dict[str, Any]] = {}
    for raw in (answer.get("events") or [])[:max_events]:
        event_id = str(raw.get("id") or "")
        if not re.fullmatch(r"k\d{1,2}", event_id):
            continue
        queries = {str(f.get("role")): " ".join(str(f.get("query") or "").split())[:120]
                   for f in raw.get("functions") or [] if str(f.get("role")) in ROLES}
        if queries:
            events[event_id] = {"name": " ".join(str(raw.get("name") or "").split())[:160], "queries": queries}
    counts: dict[str, int] = {}
    for raw in answer.get("shots") or []:
        shot = by_id.get(str(raw.get("id") or ""))
        event = events.get(str(raw.get("event") or ""))
        role = str(raw.get("role") or "")
        if shot is None or event is None or role not in event["queries"] or not shot.get("broll"):
            continue
        shot["coverage"] = {"event": str(raw["event"]), "name": event["name"], "role": role,
                            "query": event["queries"][role] or None, "sound": bool(raw.get("sound"))}
        counts[str(raw["event"])] = counts.get(str(raw["event"]), 0) + 1
    return counts


def balance(shots: list[dict[str, Any]]) -> int:
    """Never two shots of the same function of an event in a row when another of its functions is left: the next
    shot of that event with a different function swaps roles with it. Returns the swaps made."""

    swaps = 0
    covered = [s for s in shots if s.get("coverage")]
    for i in range(1, len(covered)):
        a, b = covered[i - 1]["coverage"], covered[i]["coverage"]
        if a["event"] != b["event"] or a["role"] != b["role"]:
            continue
        later = next((c for c in covered[i + 1:] if c["coverage"]["event"] == b["event"]
                      and c["coverage"]["role"] != b["role"]), None)
        if later is None:
            continue
        mine, theirs = dict(b), dict(later["coverage"])
        covered[i]["coverage"] = {**mine, "role": theirs["role"], "query": theirs["query"]}
        later["coverage"] = {**theirs, "role": mine["role"], "query": mine["query"]}
        swaps += 1
    return swaps


def lead_with_function_query(shots: list[dict[str, Any]]) -> None:
    """The function's search first in each covered shot's queries: one search per function and event."""

    for shot in shots:
        cover, broll = shot.get("coverage"), shot.get("broll")
        if not cover or not broll or not cover.get("query"):
            continue
        queries = [q for q in broll.get("queries") or [] if q != cover["query"]]
        broll["queries"] = [cover["query"], *queries][: max(1, len(broll.get("queries") or []))]


def hold(shots: list[dict[str, Any]], max_seconds: float) -> int:
    """Point 3: consecutive shots of one idea and one held function (a reaction, a testimony, a proof, the original
    commentary) become one shot, up to `max_seconds` — a reaction of 5-6 s instead of two or three cuts. In place;
    returns the shots merged away."""

    merged = 0
    i = 0
    while i < len(shots) - 1:
        a, b = shots[i], shots[i + 1]
        ca, cb = a.get("coverage") or {}, b.get("coverage") or {}
        same = (ca and cb and ca.get("role") in HOLD_ROLES and ca.get("role") == cb.get("role")
                and ca.get("event") == cb.get("event") and (a.get("idea") or {}).get("id") == (b.get("idea") or {}).get("id")
                and a.get("type") == b.get("type") == "broll" and a.get("chapter") == b.get("chapter"))
        if same and float(b["end"]) - float(a["start"]) <= max_seconds + 1e-6:
            a["end"], a["endWord"] = b["end"], b["endWord"]
            a["text"] = f"{a['text']} {b['text']}".strip()
            del shots[i + 1]
            merged += 1
            continue
        i += 1
    return merged


def apply(ctx: Any, shots: list[dict[str, Any]], header: str, ask: Any = None) -> dict[str, Any]:
    """planner.cobertura: the key events, their functions and searches, set on the shots (dicts, in order)."""

    from . import tope

    groups: dict[str, list[dict[str, Any]]] = {}
    for shot in shots:
        idea = shot.get("idea") or {}
        if idea.get("id") and idea.get("kind") != "rotulo":
            groups.setdefault(idea["id"], []).append(shot)
    if not groups:
        return {"events": 0, "shots": 0, "swaps": 0, "held": 0}
    text = "\n".join(_line(idea_id, members) for idea_id, members in groups.items())
    cfg = ctx.section("planner")
    if ask is not None:
        answer = ask(text)
    else:
        from .llm import complete_json

        try:
            answer = complete_json(ctx, stage="planner", section="planner", max_tokens=6000, system=SYSTEM,
                                   user=f"{header}\n\nIDEAS:\n{text}")
        except Exception as error:                  # the video goes on as before, without functions
            print(f"   Cobertura: sin respuesta del modelo ({str(error)[:120]})")
            return {"events": 0, "shots": 0, "swaps": 0, "held": 0}
    counts = assign(shots, answer, int(cfg.get("cobertura_max_events", 6)))
    swaps = balance(shots)
    lead_with_function_query(shots)
    held = hold(shots, min(tope.seconds(ctx), float(cfg.get("cobertura_hold_seconds", 6.0))))
    return {"events": len(counts), "shots": sum(counts.values()), "swaps": swaps, "held": held}
