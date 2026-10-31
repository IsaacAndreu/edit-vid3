"""A calendar of topics a simulation channel can actually show: ideas built from its worlds (remotion/sim/worlds.json),
what works in its niche (the radar's outliers, if the channel has competitors) and what it already made (no repeats),
one a day on the board (Tablero de ideas), each with its hook and the worlds and scenes it would use.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .context import RunContext

SYSTEM = """
Eres el editor de un canal de YouTube que explica cosas cotidianas y del mundo con simulaciones vistas desde arriba
(vídeos de ~10 min, un experimento que se ve). SOLO puede enseñar lo que hacen estos mundos:
{worlds}
Propón {count} vídeos NUEVOS que se puedan enseñar con ellos (cada idea, sobre todo con un mundo y sus escenas; nada
que necesite otra cosa), que la gente busque o se pregunte en su día a día (atascos, colas, apagones, multitudes,
bulos, incendios, inundaciones…), con un gancho cotidiano y un giro. Variados entre sí, sin repetir los ya hechos.
Cada idea con su PLAN: 6-10 bloques del vídeo, cada uno con la escena (el "scene" de un mundo) que lo enseña; un
vídeo bueno cambia de escena con cada idea y no pasa más de 3 bloques seguidos en el mismo mundo. Solo ideas que se
puedan enseñar ENTERAS con estos mundos y sus escenas (el mundo comodín explica, como mucho en 1-2 bloques).
"interest": cuánta gente lo busca o se lo pregunta (alta | media | baja).
En {language}. Devuelve SOLO JSON: {{"ideas": [{{"title": "título de YouTube, máx. 70 caracteres",
"hook": "la primera frase del vídeo", "worlds": ["mundo"], "scenes": "las escenas que usaría, en una frase",
"plan": [{{"idea": "de qué va el bloque, 3-8 palabras", "world": "…", "scene": "…"}}], "interest": "alta",
"why": "por qué funcionaría, en una frase", "dial": "solo en la serie «¿Y si…?»: el parámetro que se gira"}}]}}
""".strip()


WHAT_IF = """
Además, TODAS las ideas son de la serie «¿Y si…?»: una pregunta («¿y si todos los coches fueran autónomos?», «¿y si
hubiera una caja más?»), UN solo mundo y UN parámetro suyo que se gira (el dial). En "dial" el nombre del parámetro del
mundo que se gira y en "scenes" de qué valor a qué valor y qué pasa. El título empieza por «¿Y si».
""".strip()


def propose(root: Path, channel: str, count: int = 10, serie: str = "") -> list[dict[str, Any]]:
    from . import simulacion
    from .llm import complete_json
    from .repeticion import recent_titles

    ctx = RunContext.create("_temas", root=root, channel=channel)
    if not simulacion.active(ctx):
        raise ValueError("Ese canal no es de simulación")
    spec = simulacion.allowed(ctx)
    hits = []
    try:
        from .autopilot import candidates

        hits = [c["title"] for c in candidates(root, channel, limit=15) if c.get("title")]
    except Exception:
        pass
    made = recent_titles(root, channel)
    user = ("LO QUE FUNCIONA EN EL NICHO:\n" + "\n".join(f"- {t}" for t in hits) + "\n\n" if hits else "") \
        + ("YA HECHOS (no repitas):\n" + "\n".join(f"- {t}" for t in made) if made else "Aún no hay vídeos hechos.")
    system = SYSTEM.format(worlds=simulacion.describe(spec), count=count, language=ctx.language)
    if serie == "y-si":
        system += "\n" + WHAT_IF
    answer = complete_json(ctx, stage="temas", section="planner", max_tokens=6000, use_cache=False, user=user, system=system)
    out = []
    for item in answer.get("ideas") or []:
        worlds = [w for w in (item.get("worlds") or []) if w in spec]
        if not str(item.get("title") or "").strip() or not worlds:
            continue                       # an idea no world of the channel can show is no use
        if serie == "y-si":
            worlds = worlds[:1]            # the series: one world, one dial
            dial = str(item.get("dial") or "")
            if dial not in (spec[worlds[0]].get("params") or {}):
                continue                   # a dial the world does not have cannot be turned
        plan = [b for b in (item.get("plan") or []) if isinstance(b, dict)]
        good = [b for b in plan if covered(spec, b)]
        coverage = len(good) / len(plan) if plan else 0.0
        if len(plan) < 5 or coverage < 0.8:
            continue                       # it could not be shown whole: not on the board
        out.append({"title": str(item["title"]).strip()[:100], "hook": str(item.get("hook") or "").strip()[:300],
                    "worlds": worlds, "scenes": str(item.get("scenes") or "").strip()[:300], "why": str(item.get("why") or "").strip()[:200],
                    "coverage": round(coverage * 100), "interest": str(item.get("interest") or "media").lower(),
                    "variety": len({(b.get("world"), b.get("scene")) for b in good}),
                    "escenas": "\n".join(f"{str(b.get('idea') or '').strip()[:80]}: {b.get('world')} {b.get('scene') or ''}".strip() for b in good),
                    **({"serie": serie, "dial": str(item.get("dial"))} if serie else {})})
    rank = {"alta": 0, "media": 1, "baja": 2}
    out.sort(key=lambda i: (rank.get(i["interest"], 1), -i["coverage"], -i["variety"]))
    return out[:count]


def covered(spec: dict[str, Any], block: dict[str, Any]) -> bool:
    """A block of the plan the channel can show: a world it has and, if that world has scenes, one of them."""

    world = str(block.get("world") or "")
    if world not in spec:
        return False
    options = [str(o) for o in ((spec[world].get("params") or {}).get("scene") or {}).get("options") or []]
    return not options or str(block.get("scene") or "") in options


def calendar(root: Path, channel: str, count: int = 10, start: date | None = None, serie: str = "") -> list[dict[str, Any]]:
    """The ideas onto the board, one a day from tomorrow (or `start`); `serie`: y-si for the «¿Y si…?» series."""

    from .agenda import add_idea

    day = start or date.today() + timedelta(days=1)
    added = []
    for n, idea in enumerate(propose(root, channel, count, serie)):
        note = (f"Gancho: {idea['hook']}\nMundos: {', '.join(idea['worlds'])} · {idea['scenes']}\nPor qué: {idea['why']}\n"
                f"Se enseña con escenas: {idea['coverage']} % · interés {idea['interest']}")
        if idea.get("serie"):
            note += f"\nSerie: {idea['serie']} (pon `serie: {idea['serie']}` en el config.yaml del vídeo) · dial: {idea['dial']}"
        added.append(add_idea(root, idea["title"], channel, note, (day + timedelta(days=n)).isoformat(),
                              extra={"escenas": idea["escenas"], "hook": idea["hook"]}))
    return added
