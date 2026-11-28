"""The catalogue of a video game's missions, from its wiki: name, chapter, who gives it and what happens in it.

With it the planner knows which mission a sentence talks about — also when the script tells it in its own words
(«cuando Jason rescata a Donnie…» is «Gone Fishing») — and searches that mission's gameplay
(«GTA 6 Gone Fishing mission walkthrough no commentary»), where a search made of the sentence finds any GTA video.

    python main.py --catalogo-juego gta6        # downloads it again (the wiki is still being written)

Per channel (canales/<canal>.yaml):

    juego:
      catalogo: gta6

Saved in datos/juegos/<juego>.json, outside git: the wiki's text is CC BY-NC-SA (non-commercial), so it is only read
by the program to recognise the missions, never shown in a video, a title or a description, and never published in
this (public) repository. A channel whose catalogue is missing downloads it the first time; if that fails, the video
goes on without it (said in the log).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

FOLDER = Path("datos") / "juegos"
GAMES = {
    "gta6": {"game": "GTA 6", "api": "https://gta.wiki/api.php", "page": "Missions_in_GTA_VI",
             "source": "https://gta.wiki/wiki/Missions_in_GTA_VI"},
}


def _api(url: str, params: dict[str, Any]) -> dict[str, Any]:
    import requests

    answer = requests.get(url, params={**params, "format": "json"}, timeout=60,
                          headers={"User-Agent": "edit-vid3 (catalogo de misiones)"})
    answer.raise_for_status()
    return answer.json()


def _plain(text: str) -> str:
    """Wiki markup → plain text: [[a|b]] → b, [[a]] → a, '''x''' → x, templates and refs out."""

    text = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", text, flags=re.S)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = text.replace("'''", "").replace("''", "")
    return " ".join(text.split())


def parse(wikitext: str) -> list[dict[str, Any]]:
    """The missions of a «Missions in …» page: each table row's mission link, with the section (chapter) and the
    sub-section (who gives it) above it, and the {{Quote|…}} that follows as its description."""

    missions: list[dict[str, Any]] = []
    chapter = giver = ""
    lines = wikitext.splitlines()
    for n, line in enumerate(lines):
        if found := re.match(r"^(={2,})\s*(.*?)\s*\1\s*$", line):
            if len(found.group(1)) == 2:                         # == Chapter ==
                chapter, giver = _plain(found.group(2)), ""
            else:                                                # === who gives them === (or a deeper heading)
                giver = _plain(found.group(2))
            continue
        found = re.match(r"^\|\s*\[\[([^\]|]+)(?:\|([^\]]*))?\]\]\s*$", line)
        if not found or found.group(1).startswith(("File:", "Image:")) or not chapter:
            continue
        description = ""
        rest = "\n".join(lines[n + 1:n + 8])
        if quote := re.match(r"\s*\|\s*\{\{Quote\|(.*?)\}\}\s*(?:\n\||\n\|-|\n\|\}|$)", rest, flags=re.S):
            description = _plain(quote.group(1))
        name = re.sub(r"\s*\([^)]*\)$", "", _plain(found.group(2) or found.group(1)))   # «Gone Fishing (GTA VI)»
        missions.append({"name": name, "chapter": chapter, "giver": giver,
                         "story": not chapter.lower().startswith(("side", "other", "random")),
                         "description": description})
    return missions


def path(root: Path, key: str) -> Path:
    return root / FOLDER / f"{key}.json"


def fetch(root: Path, key: str) -> Path:
    """Downloads the catalogue of `key` (a GAMES key) and saves it. Raises ValueError for an unknown game or a page
    with no missions (never saves an empty catalogue over a good one)."""

    if key not in GAMES:
        raise ValueError(f"No conozco el juego «{key}» (hay: {', '.join(GAMES)})")
    game = GAMES[key]
    page = _api(game["api"], {"action": "parse", "page": game["page"], "prop": "wikitext|revid"}).get("parse") or {}
    missions = parse(str((page.get("wikitext") or {}).get("*") or ""))
    if not missions:
        raise ValueError(f"La página {game['source']} no tiene ninguna misión que yo sepa leer")
    try:
        rights = (_api(game["api"], {"action": "query", "meta": "siteinfo", "siprop": "rightsinfo"})
                  .get("query") or {}).get("rightsinfo") or {}
    except Exception:
        rights = {}
    data = {"game": game["game"], "source": game["source"], "revid": page.get("revid"),
            "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"), "licence": rights.get("text") or "",
            "licenceUrl": rights.get("url") or "", "missions": missions}
    target = path(root, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    from .fileio import atomic_write_text

    atomic_write_text(target, json.dumps(data, ensure_ascii=False, indent=1))
    story = sum(1 for m in missions if m["story"])
    print(f"Catálogo de {game['game']}: {story} misiones de historia y {len(missions) - story} secundarias "
          f"(revisión {page.get('revid')}) → {target.relative_to(root)}")
    return target


def load(root: Path, key: str) -> dict[str, Any]:
    return json.loads(path(root, key).read_text("utf-8"))


def planner_note(root: Path, cfg: dict[str, Any]) -> str:
    """What the shots' planner reads for a channel with `juego.catalogo`: every mission and how to search it. Empty
    when the channel has none, or the catalogue cannot be had (said in the log: the video goes on without it)."""

    key = str((cfg or {}).get("catalogo") or "").strip()
    if not key:
        return ""
    try:
        if not path(root, key).is_file():
            fetch(root, key)
        data = load(root, key)
        missions = [m for m in data.get("missions") or [] if isinstance(m, dict) and m.get("name")]
    except Exception as error:
        print(f"   Aviso: sin catálogo de misiones «{key}» ({type(error).__name__}: {str(error)[:120]}): "
              f"python main.py --catalogo-juego {key}")
        return ""
    if not missions:
        return ""
    game = str(data.get("game") or key)
    rows = "\n".join(f"- {m['name']} | {m.get('chapter', '')} | {m.get('giver', '')} | {m.get('description', '')}"
                     for m in missions)
    return (f"MISIONES DE {game.upper()} (nombre | capítulo | quién la da | qué pasa). Si un plano habla de lo que pasa "
            f"en una misión —la nombre o la cuente con otras palabras—, su PRIMERA búsqueda es esa misión: "
            f"'{game} <nombre exacto> mission walkthrough no commentary' (p. ej. '{game} {missions[0]['name']} "
            f"mission walkthrough no commentary'); las siguientes, el momento concreto dentro de ella "
            f"('{game} <nombre> <lo que pasa>'). Nunca escribas en pantalla estas descripciones: solo sirven "
            f"para reconocer la misión.\n{rows}")
