"""Doblaje de los vídeos de --atlas-guion (pipeline/atlas_doblaje.py), con una IA de mentira."""

import json
from pathlib import Path

import pytest

from pipeline import atlas_doblaje as ad

ROOT = Path(__file__).resolve().parent.parent
BOARD = json.loads((ROOT / "materiales" / "Hudson1549" / "escenas.json").read_text(encoding="utf-8"))["storyboard"]
SCRIPT = (ROOT / "materiales" / "Hudson1549" / "guion.txt").read_text(encoding="utf-8")


def test_collect_finds_anchors_and_screen_texts_but_not_vocabulary():
    anchors, texts = ad.collect(BOARD)
    assert anchors and all("say" in a for a in anchors.values())
    assert "scenes.0.kicker" in texts and "meta.brand.name" not in texts
    assert not any(p.endswith((".type", ".clock", ".region", ".data", ".ref")) for p in texts)


def test_translate_replaces_anchors_and_texts():
    def ask(system, user):
        data = json.loads(user)
        return {"guion": data["guion"].upper(), "anchors": data["anchors"], "texts": {k: v + "!" for k, v in data["texts"].items()}}

    script, board = ad.translate(ask, "alemán", "", SCRIPT, BOARD)
    assert script == SCRIPT.upper().strip()
    assert board["scenes"][0]["kicker"].endswith("!")
    assert board["scenes"][0]["type"] == BOARD["scenes"][0]["type"]
    assert board["scenes"][1]["start"]["say"] == BOARD["scenes"][1]["start"]["say"]


def test_translate_retries_and_fails_when_anchors_are_not_in_the_script():
    calls = []

    def ask(system, user):
        calls.append(user)
        data = json.loads(user)
        return {"guion": "otro texto", "anchors": data["anchors"], "texts": {}}

    with pytest.raises(ValueError):
        ad.translate(ask, "alemán", "", SCRIPT, BOARD)
    assert len(calls) == 2 and "INTENTO ANTERIOR" in calls[1]
