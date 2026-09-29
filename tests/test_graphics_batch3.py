from pipeline import graphics, planner, timeline
from pipeline.config import PROJECT_ROOT
from pipeline.context import RunContext

TEXT = ("En París ganó Yulo con 15,000, plata para Dolgopyat con 14,966 y bronce para Jarman. "
        "China ganó 8 oros en 2012, 1 en 2016 y 4 en 2021; Japón 1 en 2012, 3 en 2016 y 2 en 2021. "
        "Yulo tiene 2 oros olímpicos, 3 títulos mundiales y 24 años. "
        "Sotomayor saltó 2,45 metros en 1993.")


def test_podium_needs_the_winner():
    data = {"title": "Final de suelo", "places": [
        {"place": 1, "name": "Yulo", "note": "15,000"}, {"place": 2, "name": "Dolgopyat", "note": "14,966"},
        {"place": 3, "name": "Jarman", "note": "14,5"}]}
    out = graphics.clean("podium", data, TEXT, None, set())
    assert [p["name"] for p in out["places"]] == ["Yulo", "Dolgopyat", "Jarman"]
    assert out["places"][2]["note"] is None                                   # 14,5 was never said
    assert graphics.clean("podium", {"places": data["places"][1:]}, TEXT, None, set()) is None


def test_race_keeps_said_values_and_needs_three_steps():
    steps = [{"label": "2012", "values": {"China": 8, "Japón": 1}}, {"label": "2016", "values": {"China": 1, "Japón": 3}},
             {"label": "2021", "values": {"China": 4, "Japón": 2, "Rusia": 7}}]
    out = graphics.clean("race", {"title": "Oros", "steps": steps}, TEXT, None, set())
    assert [s["values"] for s in out["steps"]][-1] == {"China": 4, "Japón": 2}      # Rusia never said
    assert graphics.clean("race", {"title": "Oros", "steps": steps[:2]}, TEXT, None, set()) is None


def test_player_card_stats_are_said():
    data = {"name": "Carlos Yulo", "position": "suelo", "headline": {"label": "Oros", "value": "2"},
            "stats": [{"label": "Oros", "value": "2"}, {"label": "Mundiales", "value": "3"},
                      {"label": "Edad", "value": "24"}, {"label": "Altura", "value": "1,50"}]}
    out = graphics.clean("card", data, TEXT, None, set())
    assert [s["value"] for s in out["stats"]] == ["2", "3", "24"] and out["headline"] == {"label": "Oros", "value": "2"}
    assert out["position"] is None                                            # "suelo" is never said


def test_scale_adds_known_references():
    out = graphics.clean("scale", {"title": "El salto", "axis": "height", "unit": "m",
                                   "items": [{"name": "Sotomayor", "value": "2,45"}], "references": ["persona", "ovni"]},
                         TEXT, None, set())
    assert out["items"] == [{"name": "Sotomayor", "value": 2.45},
                            {"name": "Persona media", "value": 1.75, "reference": True}]
    assert graphics.clean("scale", {"axis": "height", "items": [{"name": "X", "value": 3.1}]}, TEXT, None, set()) is None


def test_rivalry_and_records_formats():
    for fmt, word in (("rivalidad", "RIVALIDAD"), ("records", "RÉCORDS")):
        assert word in planner.outline_system(RunContext.create("_t", root=PROJECT_ROOT, config={"format": fmt}))
    podium = {"type": "podium", "places": [{"place": 1}, {"place": 2}, {"place": 3}]}
    assert timeline.graphic_cues(podium, 150)[-1] == ("impact", timeline.PODIUM_RISE[1] + 8)
    assert timeline.graphic_cues({"type": "card", "stats": [{}] * 2}, 150)[0] == ("impact", timeline.CARD_LANDS)
