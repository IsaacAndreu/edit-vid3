"""Montage recipes per channel (objetivo-videos-referencia.md): `montaje.receta: persona | suceso | teoria`.

The owner's five reference videos make the same editing decisions within each kind of channel. A recipe turns those
decisions into settings that already exist, as one layer between config.yaml and the channel's profile: whatever the
channel, its series or the video set by hand still wins. No channel has a recipe until the owner gives it one (after
watching a test video whole), so nothing changes on its own.

- persona (A: Gymnast Icons, Rebeca Andrade): clips always full screen — the framed card is for photos and vertical
  material only —; almost no text (5 %); without the right clip, a photo of the person and of that time before any
  other clip or a borrowed one.
- suceso (B: Messi at the Villamarín): persona, plus coverage of each key event by function (action, angle,
  reaction, commentary, testimony, aftermath) held 5-6 s, and the original sound coming back, subtitled.
- teoria (C: Niko Bellic in GTA 6, COLETHEMAN's ten mistakes): argument cards on the brand background (up to 40 % of
  the video), the footage as proof (the scene where it is said, a circle on the detail), clips full screen.
"""

from __future__ import annotations

from typing import Any

_FULL_SCREEN = {"timeline": {"card_share": 0.0, "narrow_layout": "archive"}}

RECIPES: dict[str, dict[str, Any]] = {
    "persona": {
        "timeline": {**_FULL_SCREEN["timeline"], "max_text_share": 0.05},
        "fallback": {"literal_ambient": True, "ambient_photo_first": True},
    },
    "suceso": {
        "timeline": {**_FULL_SCREEN["timeline"], "max_text_share": 0.05},
        "fallback": {"literal_ambient": True, "ambient_photo_first": True},
        "planner": {"cobertura": True, "cobertura_hold_seconds": 6.0},
        "quotes": {"sound_passages": True, "passages": 3},
    },
    "teoria": {
        "timeline": {**_FULL_SCREEN["timeline"], "proof_circles": True},
        "graphics": {"argument": True, "max_card_share": 0.40},
        "indice": {"transcripcion": True},
    },
}

# What each recipe aims at, measured on the references (python -m pipeline.medir_video compares against these)
TARGETS: dict[str, dict[str, float]] = {
    "persona": {"cut_seconds": 3.1, "first_image": 0.0, "text_share": 0.0, "card_share": 0.25},
    "suceso": {"cut_seconds": 4.0, "first_image": 0.0, "text_share": 0.0, "card_share": 0.0},
    "teoria": {"cut_seconds": 4.0, "first_image": 0.0, "text_share": 0.05, "card_share": 0.38},
}


def preset(config: dict[str, Any]) -> dict[str, Any]:
    """The settings of the recipe `config` names ({} without one); an unknown name fails before anything runs."""

    from .config import ConfigError

    name = str(((config.get("montaje") or {}).get("receta")) or "").strip().lower()
    if not name:
        return {}
    if name not in RECIPES:
        raise ConfigError(f"montaje.receta «{name}» no existe (hay: {', '.join(RECIPES)})")
    return RECIPES[name]
