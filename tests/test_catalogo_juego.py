"""The game catalogue (pipeline/catalogo_juego.py): every mission of a game, from its wiki, so the planner knows which
mission a sentence talks about even when the script does not name it, and searches that mission's gameplay."""

from __future__ import annotations

import json

import pytest

from pipeline import catalogo_juego

# A made-up page in the wiki's shape (the real text stays out of the repository: its licence is non-commercial)
WIKITEXT = """{{Released|game=VI}}
The following is a list of '''[[missions]]'''.
==Prologue==
{| class="wikitable"
|-
|[[File:A.png|thumb]]
|[[Wake Up Call]]
|{{Quote|Ana talks to a counselor in jail.}}
|-
|}
==Chapter 1: Sunny Days==
===[[Carl Smith]]===
{| class="wikitable"
|-
|[[File:B.png|thumb]]
|[[Boat Trouble (GAME)|Boat Trouble]]
|{{Quote|When a run goes bad, Joe rescues Dan from the [[Fishers]] in the swamp.}}
|-
|[[File:C.png|thumb]]
|[[Rent Day (mission)]]
|{{Quote|Joe collects rent for '''Bob''' and takes product instead.
It goes wrong.}}
|-
|}
===[[Joe Doe]]===
{| class="wikitable"
|-
|[[Broken Link]]
|-
|}
==Side Missions==
===[[Strangers in GAME]]===
{| class="wikitable"
|-
|[[File:D.png|thumb]]
|[[Steal the Gold Car]]
|{{Quote|A stranger wants a car.}}
|}
"""


def test_the_missions_with_their_chapter_giver_and_what_happens():
    missions = catalogo_juego.parse(WIKITEXT)
    names = [m["name"] for m in missions]
    assert names == ["Wake Up Call", "Boat Trouble", "Rent Day", "Broken Link", "Steal the Gold Car"]
    boat = missions[1]
    assert boat["chapter"] == "Chapter 1: Sunny Days" and boat["giver"] == "Carl Smith" and boat["story"] is True
    assert boat["description"] == "When a run goes bad, Joe rescues Dan from the Fishers in the swamp."
    assert missions[2]["description"] == "Joe collects rent for Bob and takes product instead. It goes wrong."
    assert missions[0]["giver"] == "" and missions[3]["description"] == ""          # missing parts: empty, kept
    assert missions[4]["story"] is False and missions[4]["giver"] == "Strangers in GAME"


def test_fetch_saves_it_outside_git_with_its_source_and_licence(tmp_path, monkeypatch):
    answers = {"parse": {"parse": {"title": "Missions", "revid": 77, "wikitext": {"*": WIKITEXT}}},
               "siteinfo": {"query": {"rightsinfo": {"text": "CC BY-NC-SA 3.0", "url": "https://x/licence"}}}}
    monkeypatch.setattr(catalogo_juego, "_api", lambda url, params: answers["parse" if params["action"] == "parse"
                                                                            else "siteinfo"])
    saved = catalogo_juego.fetch(tmp_path, "gta6")
    data = json.loads(saved.read_text())
    assert saved == tmp_path / "datos" / "juegos" / "gta6.json"
    assert data["game"] == "GTA 6" and data["revid"] == 77 and data["licence"] == "CC BY-NC-SA 3.0"
    assert len(data["missions"]) == 5 and data["source"].startswith("https://gta.wiki/")
    assert catalogo_juego.load(tmp_path, "gta6")["missions"][1]["name"] == "Boat Trouble"


def test_a_page_with_no_missions_is_an_error_not_an_empty_catalogue(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogo_juego, "_api", lambda url, params: {"parse": {"wikitext": {"*": "nothing here"}}}
                        if params["action"] == "parse" else {})
    with pytest.raises(ValueError):
        catalogo_juego.fetch(tmp_path, "gta6")
    assert not (tmp_path / "datos" / "juegos" / "gta6.json").exists()
    with pytest.raises(ValueError):
        catalogo_juego.fetch(tmp_path, "juego-que-no-existe")


def test_what_the_planner_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogo_juego, "_api", lambda url, params: {"parse": {"revid": 1, "wikitext": {"*": WIKITEXT}}}
                        if params["action"] == "parse" else {})
    catalogo_juego.fetch(tmp_path, "gta6")
    note = catalogo_juego.planner_note(tmp_path, {"catalogo": "gta6"})
    assert "Boat Trouble" in note and "Carl Smith" in note and "rescues Dan" in note
    assert "'GTA 6 Boat Trouble mission walkthrough no commentary'" in note or "mission walkthrough" in note
    assert catalogo_juego.planner_note(tmp_path, {}) == ""                         # off: nothing
    (tmp_path / "datos" / "juegos" / "gta6.json").write_text("{roto")              # broken: nothing, never a crash
    assert catalogo_juego.planner_note(tmp_path, {"catalogo": "gta6"}) == ""


def test_the_shots_planner_reads_the_catalogue_only_where_asked(tmp_path, monkeypatch):
    from pipeline import planner
    from pipeline.context import RunContext

    monkeypatch.setattr(catalogo_juego, "_api", lambda url, params: {"parse": {"revid": 1, "wikitext": {"*": WIKITEXT}}}
                        if params["action"] == "parse" else {})
    planner._CATALOGUE_NOTES.clear()
    (tmp_path / "config.yaml").write_text("planner: {shots_note: 'nota del canal'}\n")
    plain = RunContext.create("v1", root=tmp_path)
    assert "Boat Trouble" not in planner.label_system(plain) and "nota del canal" in planner.label_system(plain)
    game = RunContext.create("v2", root=tmp_path, config={"planner": {"shots_note": "nota del canal"},
                                                          "juego": {"catalogo": "gta6"}})
    text = planner.label_system(game)
    assert "nota del canal" in text and "Boat Trouble" in text and "rescues Dan" in text
    assert (tmp_path / "datos" / "juegos" / "gta6.json").is_file()      # downloaded the first time it was needed


def test_a_gta6_channel_made_from_the_studio_gets_the_catalogue_on_its_own():
    from pipeline import canal_juego

    made = canal_juego.adjust({"canal": "gta6-es", "ideas": {"about": "Misiones y secretos de GTA VI"}}, {})
    assert made["juego"]["catalogo"] == "gta6"
    gta5 = canal_juego.adjust({"canal": "gta5", "ideas": {"about": "GTA 5 online"}}, {})
    assert "juego" not in gta5                                              # another game: no
    own = canal_juego.adjust({"canal": "x", "ideas": {"about": "GTA 6"}, "juego": {}}, {"juego": {}})
    assert own["juego"] == {}                                               # the channel said its own: kept
