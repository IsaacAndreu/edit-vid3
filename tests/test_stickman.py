"""Stickman videos (pipeline/stickman.py): no footage stage searches anything, and every scene uses only the
vocabulary the component draws, with captions taken from the line itself."""

from __future__ import annotations

from pipeline import stickman
from pipeline.context import RunContext


def test_a_scene_keeps_to_the_vocabulary_and_the_lines_words():
    scene = stickman.clean({"place": "volcano", "actors": [{"pose": "dance", "face": "happy", "x": 3, "label": "el jefe malo"},
                                                           {"pose": "point", "facing": "left"}],
                            "prop": {"icon": "money", "x": 0.7, "label": "ahorros"}, "caption": "tu dinero se escapa"},
                           "Mira cómo tu dinero se escapa cada mes.")
    assert scene["place"] == "plain" and scene["actors"][0]["pose"] == "stand" and scene["actors"][0]["x"] == 0.88
    assert scene["actors"][0]["label"] == "EL JEFE" and scene["actors"][1]["facing"] == "left"
    assert scene["prop"]["icon"] == "money" and scene["caption"] == "TU DINERO SE ESCAPA"
    assert stickman.clean({"caption": "ahorra mil euros"}, "Mira cómo tu dinero se escapa.")["caption"] == ""   # not said
    assert stickman.clean({}, "x")["actors"][0]["pose"] == "talk"                                               # never empty


def test_the_footage_stages_leave_valid_empty_results(tmp_path):
    from pipeline import analysis, coldopen, fallback, ingest, judge, people, sourcing

    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "stickman"}})
    assert stickman.active(ctx)
    ctx.write_json("shots.json", {"slug": "v", "title": "v", "durationSeconds": 3.0, "chapters": [{"title": "c", "startWord": 0, "fromScript": False}],
                                  "shots": [{"id": "s001", "type": "broll", "startWord": 0, "endWord": 2, "start": 0.0, "end": 3.0,
                                             "text": "Una frase.", "chapter": 0,
                                             "broll": {"visualIntent": "una escena", "queriesEn": ["a", "b", "c"], "queriesEs": ["a"],
                                                       "entities": [], "mustContain": [], "avoid": [], "preferredShot": "medium"}}]})
    for stage in stickman.SKIP:
        stickman.skip(ctx, stage)
    for module in (sourcing, analysis, judge, ingest, people, fallback, coldopen):
        assert module.validate(ctx) is not False
