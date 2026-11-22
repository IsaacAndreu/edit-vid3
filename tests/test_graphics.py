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


def test_the_video_game_graphics_carry_only_what_the_script_says():
    from pipeline.graphics import game_graphic

    text = "Si robas un coche de policía te caen tres estrellas. Lucia te escribe: te espero en el puerto. Vas a Vice Beach, a 2 km."
    assert game_graphic("wanted", {"title": "robas un coche de policía", "stars": 3}, text) == {
        "type": "wanted", "title": "robas un coche de policía", "stars": 3}
    assert game_graphic("wanted", {"title": "robas un coche de policía", "stars": 5}, text)["stars"] is None   # 5 not said
    assert game_graphic("wanted", {"title": "atracas un banco"}, text) is None
    assert game_graphic("phone", {"from": "Lucia", "text": "te espero en el puerto", "kind": "llamada"}, text) == {
        "type": "phone", "from": "Lucia", "text": "te espero en el puerto", "kind": "sms"}                 # no call said
    assert game_graphic("phone", {"from": "Jason", "text": "te espero en el puerto"}, text) is None
    assert game_graphic("gps", {"place": "Vice Beach", "note": "la misión del atraco", "distance": "2 km"}, text) == {
        "type": "gps", "place": "Vice Beach", "note": None, "distance": "2 km"}


def test_only_a_channel_about_a_video_game_gets_the_game_graphics(tmp_path, monkeypatch):
    from pipeline import graphics
    from pipeline.context import RunContext

    asked = {}
    monkeypatch.setattr(graphics, "complete_json", lambda ctx, **kw: asked.update(kw) or {"graphics": []})
    sents = [{"n": i, "start": i * 5.0, "end": i * 5.0 + 4.5, "text": "Frase."} for i in range(40)]
    (tmp_path / "config.yaml").write_text("graphics:\n  types: [map, chart]\n  extra_types: []\n")
    graphics.plan(RunContext.create("v", root=tmp_path), sents, 200.0)
    assert "Tipos permitidos en este canal: map, chart." in asked["system"]
    (tmp_path / "config.yaml").write_text("graphics:\n  types: [map, chart]\n  extra_types: []\nideas:\n  about: GTA 6\n")
    graphics.plan(RunContext.create("v", root=tmp_path), sents, 200.0)
    assert "Tipos permitidos en este canal: map, chart, wanted, phone, gps, ficha, prueba, afirmacion, lista." in asked["system"]


def test_argument_cards_take_only_what_the_script_says():
    """Segunda tanda, point 4: a character card, evidence rows with ✓/✗, a numbered claim with its verdict, a list."""

    from pipeline.graphics import argument_graphic

    text = ("Jimmy, el hijo de Michael en GTA 5, vuelve. Mentira 1: que Trevor habla en la radio de GTA 6. Falso. "
            "En los créditos de GTA 6 aparece Josephine Phoenix como Valentina. Dentro de la taquilla hay una pistola, "
            "la foto de Lucia y billetes de Vice City.")
    assert argument_graphic("ficha", {"name": "Jimmy", "origin": "GTA 5", "line": "el hijo de Michael"}, text) == \
        {"type": "ficha", "name": "Jimmy", "origin": "GTA 5", "line": "el hijo de Michael"}
    assert argument_graphic("ficha", {"name": "Franklin"}, text) is None                       # never said
    claim = argument_graphic("afirmacion", {"label": "Mentira 1", "claim": "Trevor habla en la radio de GTA 6",
                                            "verdict": "Falso", "ok": False}, text)
    assert claim and claim["ok"] is False
    rows = argument_graphic("prueba", {"title": "créditos de GTA 6", "rows": [
        {"source": "los créditos de GTA 6", "fact": "Josephine Phoenix", "match": "Valentina", "ok": True},
        {"source": "el tráiler 3", "fact": "Niko Bellic", "match": "Niko", "ok": True}]}, text)
    assert rows and len(rows["rows"]) == 1                                                     # the invented row goes
    items = argument_graphic("lista", {"title": "dentro de la taquilla",
                                       "items": ["una pistola", "la foto de Lucia", "billetes de Vice City"]}, text)
    assert items and len(items["items"]) == 3
    assert argument_graphic("lista", {"title": "dentro de la taquilla", "items": ["una pistola"]}, text) is None


def test_argument_cards_only_where_asked_and_never_past_their_share():
    import inspect

    from pipeline import graphics

    source = inspect.getsource(graphics.plan)
    assert 'cfg.get("argument", False)' in source and 'cfg.get("max_card_share", 0.35)' in source


def test_the_circle_goes_around_the_line_the_narration_names():
    """Segunda tanda, point 4: the easy case of a circle over the proof — text found by OCR."""

    from pipeline.timeline import circle_box

    words = [([[100, 100], [500, 100], [500, 140], [100, 140]], "PRODUCED BY ROCKSTAR NORTH"),
             ([[700, 600], [1200, 600], [1200, 650], [700, 650]], "Josephine Phoenix ... Valentina")]
    box = circle_box(words, "en los créditos aparece Josephine Phoenix como Valentina", 1920, 1080)
    assert box is not None and 30 < box[0] < 37 and 52 < box[1] < 56 and 63 < box[2] < 67
    assert circle_box(words, "nada que ver aquí", 1920, 1080) is None
