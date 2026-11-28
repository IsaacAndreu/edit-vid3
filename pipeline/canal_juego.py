"""A channel about a video game gets the settings it needs on its own.

config.yaml blocks every source whose title says «gta», «gameplay», «video game»… (content.title_blocklist), and the
judge rejects video-game footage unless told otherwise: right for a channel about megaprojects, fatal for one about
GTA VI (19-11: gtaviprueba, 137 of 164 shots without a picture — the search found nothing it was allowed to use).
A channel created from the studio only says what it is about (ideas.about, its name, its lab searches), so when that
names a video game and the channel has not set its own lists, this adjusts the merged config:

- content.title_blocklist without the video-game terms (gameplay, walkthrough, «video game»…) and without any term
  its own topic names (a Minecraft channel keeps Minecraft);
- content.official_channels with Rockstar Games for GTA / Red Dead;
- judge.note telling the judge that footage of the game is what this channel shows;
- juego.catalogo: gta6 when it is about GTA 6 (its missions from the wiki: pipeline/catalogo_juego.py).

A channel that writes its own content.title_blocklist or judge.note keeps exactly what it wrote (leonida-echt).
"""

from __future__ import annotations

import re
from typing import Any

GAME_WORDS = ("videojuego", "videojuegos", "video game", "video games", "videogame", "videogames", "gaming", "gamer",
              "gameplay", "gta", "grand theft auto", "rockstar", "minecraft", "fortnite", "roblox", "red dead", "sims",
              "call of duty", "zelda", "pokemon", "pokémon", "nintendo", "playstation", "xbox", "elden ring",
              "cyberpunk", "videospiel", "videogioco", "jeu vidéo", "jogo")
# what the global blocklist has against video games in general: never right for a channel about one
GAME_TERMS = {"gta", "gameplay", "walkthrough", "let's play", "lets play", "playthrough", "red dead", "videojuego",
              "video game", "speedrun", "simulator"}
ROCKSTAR = ("gta", "grand theft auto", "red dead", "rockstar")
GTA6 = ("gta 6", "gta vi", "gta6", "grand theft auto vi", "grand theft auto 6", "leonida")


def _has(term: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def topic(config: dict[str, Any]) -> str:
    ideas = config.get("ideas") or {}
    lab = config.get("lab") or {}
    parts = [str(config.get("canal") or ""), str(ideas.get("about") or ""),
             *[str(n) for n in (ideas.get("niches") or [])], *[str(q) for q in (lab.get("queries") or [])]]
    return " ".join(parts).casefold().replace("-", " ").replace("_", " ")


def is_game_channel(config: dict[str, Any]) -> bool:
    text = topic(config)
    return any(_has(word, text) for word in GAME_WORDS)


def adjust(config: dict[str, Any], own: dict[str, Any]) -> dict[str, Any]:
    """`config`: the merged config of a video; `own`: what the channel's profile, series and the video itself wrote
    (their own lists win). Returns the config, adjusted when the channel is about a video game."""

    if not is_game_channel(config):
        return config
    text = topic(config)
    own_content = own.get("content") or {}
    own_judge = own.get("judge") or {}
    content = dict(config.get("content") or {})
    if "title_blocklist" not in own_content:
        content["title_blocklist"] = [t for t in (content.get("title_blocklist") or [])
                                      if str(t).casefold() not in GAME_TERMS and not _has(str(t).casefold(), text)]
    if "official_channels" not in own_content and any(_has(w, text) for w in ROCKSTAR):
        content["official_channels"] = list(dict.fromkeys([*(content.get("official_channels") or []), "Rockstar Games"]))
    judge = dict(config.get("judge") or {})
    if not own_judge.get("note"):
        about = str((config.get("ideas") or {}).get("about") or config.get("canal") or "a video game").strip()
        judge["note"] = (f"This channel is about a video game ({about[:120]}). Any footage of the game (official "
                         "trailers, gameplay, screenshots, from any channel) is ACCEPTABLE for any line about the game, "
                         "its characters, map, vehicles or release. For lines about a real place or a real case, prefer "
                         "real footage of that place. Reject only what is off-topic, a presenter or streamer's face "
                         "talking to camera, or burned-in subtitles.")
    out = {**config, "content": content, "judge": judge}
    if "juego" not in own and any(_has(w, text) for w in GTA6):
        out["juego"] = {**(config.get("juego") or {}), "catalogo": "gta6"}
    return out
