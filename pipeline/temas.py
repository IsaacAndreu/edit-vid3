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
En {language}. Devuelve SOLO JSON: {{"ideas": [{{"title": "título de YouTube, máx. 70 caracteres",
"hook": "la primera frase del vídeo", "worlds": ["mundo"], "scenes": "las escenas que usaría, en una frase",
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
    answer = complete_json(ctx, stage="temas", section="planner", max_tokens=3500, use_cache=False, user=user, system=system)
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
        out.append({"title": str(item["title"]).strip()[:100], "hook": str(item.get("hook") or "").strip()[:300],
                    "worlds": worlds, "scenes": str(item.get("scenes") or "").strip()[:300], "why": str(item.get("why") or "").strip()[:200],
                    **({"serie": serie, "dial": str(item.get("dial"))} if serie else {})})
    return out[:count]


def calendar(root: Path, channel: str, count: int = 10, start: date | None = None, serie: str = "") -> list[dict[str, Any]]:
    """The ideas onto the board, one a day from tomorrow (or `start`); `serie`: y-si for the «¿Y si…?» series."""

    from .agenda import add_idea

    day = start or date.today() + timedelta(days=1)
    added = []
    for n, idea in enumerate(propose(root, channel, count, serie)):
        note = f"Gancho: {idea['hook']}\nMundos: {', '.join(idea['worlds'])} · {idea['scenes']}\nPor qué: {idea['why']}"
        if idea.get("serie"):
            note += f"\nSerie: {idea['serie']} (pon `serie: {idea['serie']}` en el config.yaml del vídeo) · dial: {idea['dial']}"
        added.append(add_idea(root, idea["title"], channel, note, (day + timedelta(days=n)).isoformat()))
    return added
