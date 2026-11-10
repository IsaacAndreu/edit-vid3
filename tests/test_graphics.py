from pipeline import graphics
from pipeline.context import RunContext

TEXT = "En 2018 ganó bronce en Doha. En 2019 fue oro en Stuttgart con un 15.3. En 2021 quedó cuarto en Tokio."


def test_numbers_must_be_said():
    ok = graphics.clean("timeline", {"title": "Carrera", "events": [
        {"year": "2018", "text": "Bronce en Doha"}, {"year": "2019", "text": "Oro en Stuttgart"},
        {"year": "2021", "text": "Cuarto en Tokio"}, {"year": "2022", "text": "Inventado"}]}, TEXT, None, set())
    assert [e["year"] for e in ok["events"]] == ["2018", "2019", "2021"]            # 2022 is never said
    chart = graphics.clean("chart", {"chart": "bar", "title": "Notas", "data": [
        {"label": "Stuttgart", "value": 15.3}, {"label": "Doha", "value": 14.9}]}, TEXT, None, set())
    assert chart is None                                                             # 14.9 invented, and < 3 points


def test_compare_needs_two_rows_of_said_figures():
    data = {"left": {"name": "A"}, "right": {"name": "B"}, "rows": [
        {"label": "x", "a": 2018, "b": 2019}, {"label": "y", "a": 15.3, "b": 2021}]}
    assert graphics.clean("compare", data, TEXT, None, set())["rows"][1] == {"label": "y", "a": 15.3, "b": 2021.0,
                                                                            "unit": None, "better": "high"}
    data["rows"][1]["b"] = 99
    assert graphics.clean("compare", data, TEXT, None, set()) is None


def test_map_keeps_known_countries_and_geocoded_points(tmp_path, monkeypatch):
    monkeypatch.setattr(graphics, "geocode", lambda ctx, q: (139.7, 35.7) if "Tokyo" in q else None)
    ctx = RunContext.create("x", root=tmp_path, config={})
    out = graphics.clean("map", {"title": "Japón", "countries": ["Japan", "Narnia"], "route": True, "zoom": 3,
                                 "points": [{"name": "Tokio", "query": "Tokyo, Japan", "note": "2021"},
                                            {"name": "Atlantis", "query": "Atlantis"}]}, TEXT, ctx, {"Japan", "France"})
    assert out["countries"] == ["Japan"] and [p["name"] for p in out["points"]] == ["Tokio"]
    assert out["points"][0]["note"] == "2021" and out["route"] is False and out["zoom"] is None


def test_kinetic_must_be_literal_and_short():
    assert graphics.clean("kinetic", {"lines": ["oro en Stuttgart"]}, TEXT, None, set()) == {"type": "kinetic", "lines": ["oro en Stuttgart"]}
    assert graphics.clean("kinetic", {"lines": ["plata en Londres"]}, TEXT, None, set()) is None


def test_portrait_prefers_full_name_and_refuses_ambiguous_surnames(tmp_path, monkeypatch):
    monkeypatch.setattr(graphics, "face_focus", lambda ctx, path: (50.0, 20.0))
    ctx = RunContext.create("x", root=tmp_path, config={})
    people = [{"name": "Carlos Yulo", "image": "people/carlos.png"}, {"name": "Eldrew Yulo", "image": "people/eldrew.png"}]
    assert graphics.portrait(ctx, "Carlos Yulo", people)["src"] == "people/carlos.png"
    assert graphics.portrait(ctx, "Yulo", people) is None
    assert graphics.portrait(ctx, "Eldrew", people)["focus"] == [50.0, 20.0]
