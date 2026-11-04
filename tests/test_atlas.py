"""Atlas deep dives: the LLM's scenes cleaned, every element at its word, chapters, cues, drawn and dubbed."""

from pathlib import Path
from types import SimpleNamespace

from pipeline import atlas, dub, stickman
from pipeline.context import RunContext


def test_clean_keeps_only_the_vocabulary_and_falls_back_to_the_globe():
    scene = atlas.clean({"view": "chart", "camera": {"lat": -90, "lon": 0, "zoom": 9},
                         "routes": [{"from": [-31.9, 115.8], "to": [-34.6, -58.4], "label": "6.500 km", "style": "main", "at": "cuerda"},
                                    {"from": "x", "to": [1, 2]}],
                         "rings": [{"lat": -54.8, "lon": -68.3, "km": 99999, "label": "Ushuaia"}],
                         "card": {"kind": "quote", "title": "Tratado", "lines": ["cita"], "at": "dice"},
                         "chart": {"kind": "bars", "bars": [{"label": "Defecto", "value": 60}, {"label": "787", "value": "330"}]}}, None)
    assert scene["camera"] == {"lat": -90.0, "lon": 0.0, "zoom": 1.8}          # the whole globe unless a place is named
    assert len(scene["routes"]) == 1 and scene["rings"][0]["km"] == 6000 and scene["rings"][0]["label"] == "USHUAIA"
    assert scene["view"] == "chart" and scene["chart"]["bars"][1]["value"] == 330
    one = atlas.clean({"view": "chart", "chart": {"kind": "bars", "title": "SUEÑO", "bars": [{"label": "1 h más", "value": 19, "unit": "min"}]}}, None)
    assert one["view"] == "globe" and one["counter"]["value"] == 19 and one["counter"]["unit"] == "min"   # one bar: a counter
    bad = atlas.clean({"view": "icon", "icon": {"name": "unicornio"}}, scene)
    assert bad["view"] == "globe" and bad["camera"] == scene["camera"]          # no valid icon: the globe, same camera


def _shot(i, start, dur, text, kind="broll", title=None, number=None):
    return SimpleNamespace(id=f"s{i}", type=kind, from_=start, durationInFrames=dur, text=text,
                           chapterTitle=title, chapterNumber=number)


def test_groups_time_elements_to_their_words_and_carry_the_chapters(monkeypatch, tmp_path: Path):
    ctx = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "brand": {"name": "Atlas"}})
    shots = [_shot(0, 0, 90, "Estira una cuerda de Perth a Buenos Aires."),
             _shot(1, 90, 60, "", "chapter", "Nadie a quien *volar*", 1),
             _shot(2, 150, 90, "Casi nadie vive en el sur.")]
    monkeypatch.setattr(atlas, "scenes", lambda c, s: {
        "s0": atlas.clean({"camera": {"lat": -90, "lon": 0, "zoom": 1.5},
                           "points": [{"name": "Perth", "lat": -31.9, "lon": 115.8, "at": "Perth"}]}, None),
        "s2": atlas.clean({"camera": {"lat": -40, "lon": 20, "zoom": 1}}, None)})
    words = SimpleNamespace(words=[SimpleNamespace(start=1.5, text="Perth"), SimpleNamespace(start=0.2, text="Estira")])
    out = atlas.groups(ctx, shots, 30, [], words)
    assert [g["graphic"]["view"] for g in out] == ["globe", "title", "globe"]
    assert out[0]["graphic"]["points"][0]["at"] == 45                  # the frame of «Perth»
    assert out[1]["graphic"]["title"] == {"number": "I", "text": "Nadie a quien *volar*"}   # (if a chapter shot ever comes)
    assert out[2]["graphic"]["chapter"] == 1 and out[2]["graphic"]["chapters"] == ["Nadie a quien *volar*"]
    assert out[2]["graphic"]["prev"] == out[0]["graphic"]["camera"]    # the globe turns from the last globe shot
    assert out[0]["graphic"]["brand"] == "Atlas"


def test_atlas_is_drawn_and_its_texts_are_dubbed(tmp_path: Path):
    ctx = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}})
    assert atlas.active(ctx) and stickman.drawn(ctx) and stickman.film(ctx)
    assert "atlas" in dub.DRAWN_TEXTS and "card" in dub.DRAWN_TEXTS["atlas"]
    cues = atlas.cues({"prev": {"lat": 0, "lon": 0, "zoom": 1}, "camera": {"lat": -90, "lon": 0, "zoom": 2},
                       "stamp": {"at": 10}, "routes": [{"at": 5}]}, 30)
    assert {c[0] for c in cues} >= {"whoosh-down", "stamp", "marker"}


def test_writing_guide_per_language(tmp_path: Path):
    es = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "align": {"language": "es"}})
    en = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "align": {"language": "en"}})
    assert "cinco razones" in atlas.writing(es) and "five reasons" in atlas.writing(en)


def test_description_cites_the_checked_facts(tmp_path: Path):
    import json

    from pipeline import publish

    ctx = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "align": {"language": "en"}})
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    (ctx.work_dir / "factcheck.json").write_text(json.dumps({"claims": [
        {"claim": "The A350 is certified for 370-minute ETOPS", "verdict": "ok", "source": "https://example.org/a350"},
        {"claim": "Unsure thing", "verdict": "unverified", "source": "https://example.org/x"},
        {"claim": "Duplicate", "verdict": "ok", "source": "https://example.org/a350"}]}))
    text = publish.fact_sources(ctx, 1000)
    assert text == "Sources\nThe A350 is certified for 370-minute ETOPS: https://example.org/a350"
    assert publish.compact_credits([], 1000).strip().count("\n") == 0        # no third-party sources: the heading alone


def test_the_camera_fits_what_is_drawn_and_a_line_in_the_same_place_keeps_it():
    scene = atlas.clean({"camera": {"lat": -45, "lon": 100, "zoom": 2},
                         "routes": [{"from": [-31.9, 115.8], "to": [-34.6, -58.4], "at": "cuerda"}]}, None)
    fitted = atlas.fit_camera(scene)
    assert fitted["camera"]["lat"] < -70 and fitted["camera"]["zoom"] <= 1.3          # looks down at the pole, pulled out
    nxt = atlas.carry(atlas.clean({"camera": dict(fitted["camera"])}, fitted), fitted)
    assert nxt["routes"] and nxt["routes"][0]["kept"]
    moved = atlas.carry(atlas.clean({"camera": {"lat": 50, "lon": 0, "zoom": 2}}, fitted), fitted)
    assert not moved["routes"]


def test_autopilot_asks_an_atlas_channel_for_a_question_in_five_reasons(monkeypatch, tmp_path: Path):
    from pipeline import autopilot, llm

    (tmp_path / "canales").mkdir()
    (tmp_path / "config.yaml").write_text("align: {language: es}\n")
    (tmp_path / "canales" / "atlas-es.yaml").write_text("visual: {style: atlas}\nideas: {about: mapas}\n")
    seen = {}

    def fake(ctx, **kw):
        seen.update(kw)
        return {"title": "¿Por qué nadie vive aquí?"}

    monkeypatch.setattr(llm, "complete_json", fake)
    import pipeline.porque as porque
    import pipeline.repeticion as repeticion
    monkeypatch.setattr(porque, "lessons", lambda root, ch: [])
    monkeypatch.setattr(repeticion, "recent_titles", lambda root, ch: [])
    idea = autopilot.idea_from(tmp_path, "atlas-es", {"title": "Why planes avoid Antarctica", "channel": "X", "views": 1, "ratio": 50})
    assert idea["title"] and "cinco razones" in seen["system"] and "PREGUNTA" in seen["system"]


def test_the_real_night_and_the_new_cards():
    from datetime import datetime, timezone

    lat, lon = atlas.subsolar(datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc))
    assert abs(lat - 23.44) < 0.1 and abs(lon) < 1                    # solstice noon: over the tropic, at Greenwich
    scene = atlas.clean({"camera": {"lat": 47, "lon": 6, "zoom": 2.6},
                         "night": {"date": "2026-06-21", "from": "21:20", "to": "22:25", "tz": "Europe/Madrid", "at": "noche"},
                         "meridians": {"step": 15},
                         "highlight": [{"name": "Spain", "label": "UTC+1", "group": 1}],
                         "card": {"kind": "choice", "title": "Vives en Vigo y quieres comer con el sol en lo más alto. ¿A qué hora te sientas?",
                                  "lines": ["A las 13:00", "A las 14:40"], "source": "2"}}, None)
    assert scene["night"]["clock"] == ["21:20", "22:25"] and scene["night"]["from"][1] > scene["night"]["to"][1]   # the sun moves west
    assert scene["meridians"]["step"] == 15 and scene["highlight"][0]["group"] == 1
    assert scene["card"]["title"].endswith("¿A qué hora te sientas?")


def test_lines_in_the_same_place_pile_up_and_a_bare_figure_becomes_a_tag():
    a = atlas.clean({"camera": {"lat": 45, "lon": 0, "zoom": 2},
                     "points": [{"name": "Vigo", "lat": 42.2, "lon": -8.7, "at": "Vigo"}]}, None)
    b = atlas.carry(atlas.clean({"camera": {"lat": 45.5, "lon": 0.5, "zoom": 2},
                                 "points": [{"name": "Madrid", "lat": 40.4, "lon": -3.7, "at": "Madrid"}]}, a), a)
    assert [p["name"] for p in b["points"]] == ["VIGO", "MADRID"] and b["points"][0]["kept"] and b["camera"] == a["camera"]
    c = atlas.auto_tag(atlas.carry(atlas.clean({"camera": a["camera"]}, b), b), "En Vigo, a las 14:42.", b)
    assert c["tags"] == [{"text": "14:42", "lat": 42.2, "lon": -8.7, "at": "14:42"}]       # by Vigo, the place it names
    assert atlas.auto_tag(c, "Nada que contar.", b) == c
    close = atlas.clean({"camera": {"lat": 42, "lon": -4, "zoom": 3}, "points": [{"name": "Vigo", "lat": 42.2, "lon": -8.7}]}, None)
    again = atlas.carry(atlas.clean({"camera": close["camera"]}, close), close)
    assert again["camera"]["zoom"] == 2.6 and again["points"]          # the same close view, its dot kept
    far = atlas.carry(atlas.clean({"camera": {"lat": -40, "lon": 140, "zoom": 1.5}}, b), b)
    assert far["points"] == []


def test_the_new_views_and_elements():
    sat = atlas.clean({"view": "sat", "sat": {"lat": 51.95, "lon": 4.12, "zoom": 20, "label": "Puerto de Róterdam"}}, None)
    assert sat["view"] == "sat" and sat["sat"]["zoom"] == 13 and sat["camera"]["lat"] == 51.95
    flat = atlas.clean({"view": "flat", "flat": {"from": [-31.9, 115.8], "to": [-34.6, -58.4], "straight": "lo que sugiere"}}, None)
    assert flat["view"] == "flat" and flat["flat"]["straight"] == "LO QUE SUGIERE"
    size = atlas.clean({"view": "size", "size": {"country": "Greenland", "to": [2, 20], "compare": "Algeria"}}, None)
    assert size["view"] == "size" and size["size"]["to"] == [2.0, 20.0]
    assert atlas.clean({"view": "size", "size": {"country": "Greenland"}}, None)["view"] == "globe"     # nowhere to drag it
    scene = atlas.clean({"routes": [{"from": [40.4, -3.7], "to": [40.7, -74], "mover": "plane"},
                                    {"from": [51.5, 0], "to": [35.7, 139.7], "style": "many"}],
                         "counter": {"value": "5770", "unit": "km"},
                         "night": {"date": "2026-12-21", "from": "18:30", "tz": "Europe/Madrid"}}, None)
    assert [r["mover"] for r in scene["routes"]] == ["plane", "dot"] and scene["counter"]["value"] == 5770
    assert scene["night"]["lights"] is True


def test_two_satellite_dives_when_the_llm_chose_none():
    scenes = {f"s{i}": atlas.clean({"camera": {"lat": 40, "lon": 0, "zoom": 1.5}}, None) for i in range(30)}
    for i in (5, 7, 16, 25):
        scenes[f"s{i}"] = atlas.clean({"camera": {"lat": 42, "lon": -8, "zoom": 2},
                                        "points": [{"name": f"Sitio {i}", "lat": 42.2, "lon": -8.7, "at": "Vigo"}]}, None)
    atlas.ensure_satellites(scenes, 2)
    dives = [k for k, g in scenes.items() if g["view"] == "sat"]
    assert len(dives) == 2 and "s7" not in dives                       # never two within 8 lines
    assert scenes[dives[0]]["sat"]["zoom"] == 11 and scenes[dives[0]]["sat"]["label"].startswith("SITIO")


def test_a_named_country_gets_its_flag():
    assert atlas.flag_codes()["Spain"] == "es" and atlas.flag_codes()["Poland"] == "pl"
    scene = atlas.clean({"countries": [{"name": "Spain", "label": "España", "at": "España"}, {"name": "Atlantis"}]}, None)
    assert scene["countries"] == [{"name": "Spain", "label": "ESPAÑA", "at": "España"}]        # unknown names dropped


def test_the_night_stays_and_its_sun_never_jumps_back():
    night = {"date": "2026-06-21", "from": "21:20", "to": "22:25", "tz": "Europe/Madrid"}
    a = atlas.clean({"camera": {"lat": 47, "lon": 6, "zoom": 1.8}, "night": night}, None)
    b = atlas.carry(atlas.clean({"camera": {"lat": 45, "lon": 0, "zoom": 1.4}}, a), a)          # moved a bit, no night given
    assert b["night"]["kept"] and b["night"]["from"] == a["night"]["to"] == b["night"]["to"]
    c = atlas.carry(atlas.clean({"camera": {"lat": 45, "lon": 0, "zoom": 1.4}, "night": night}, b), b)   # the same night again
    assert c["night"]["from"] == a["night"]["to"]
    off = atlas.carry(atlas.clean({"camera": {"lat": 45, "lon": 0, "zoom": 1.4}, "night": {"off": True}}, c), c)
    assert off["night"] is None
    far = atlas.carry(atlas.clean({"camera": {"lat": -30, "lon": 140, "zoom": 1.4}}, c), c)
    assert far["night"] is None                                                                     # another part of the world
