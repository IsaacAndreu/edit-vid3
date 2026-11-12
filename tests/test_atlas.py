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
    cam = out[0]["graphic"]["camera"]                                   # the globe turns from where the last one ended
    assert out[2]["graphic"]["prev"] == {"lat": cam["lat"], "lon": cam["lon"] + 0.75, "zoom": round(cam["zoom"] + atlas.PUSH, 2)}
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
    assert close["camera"]["zoom"] == 4.4                               # a region: the close map, never a cut globe
    assert again["camera"]["zoom"] == 4.4 and again["points"]          # the same close view, its dot kept
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


def test_close_views_fill_the_screen_or_fall_back_to_the_globe():
    vigo = {"name": "Vigo", "lat": 42.2, "lon": -8.7}
    assert atlas.clean({"camera": {"lat": 42, "lon": -8, "zoom": 3.4}, "points": [vigo]}, None)["camera"]["zoom"] == 4.4
    assert atlas.clean({"camera": {"lat": 42, "lon": -8, "zoom": 9}, "points": [vigo]}, None)["camera"]["zoom"] == 6.0
    assert atlas.clean({"camera": {"lat": 42, "lon": -8, "zoom": 2.4}, "points": [vigo]}, None)["camera"]["zoom"] == 2.4
    far = atlas.fit_camera(atlas.clean({"camera": {"lat": 42, "lon": -8, "zoom": 5},
                                        "points": [vigo, {"name": "Moscú", "lat": 55.7, "lon": 37.6}]}, None))
    assert far["camera"]["zoom"] <= 2.6                                 # a close view that would hide Moscow


def test_a_failed_batch_is_asked_again_in_halves_and_drawings_are_spaced(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from pipeline import llm
    from pipeline.context import RunContext

    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "atlas"}})
    shots = [SimpleNamespace(id=f"s{i}", text=f"Frase {i} sobre Brasil.") for i in range(1, 31)]
    asked = []

    def answer(_ctx, **kw):
        first, last = [int(x) for x in kw["user"].split("FRASES ")[1].split(":")[0].split("-")]
        asked.append((first, last))
        if last - first + 1 > 13:
            raise ValueError("JSON cortado")
        return {"scenes": [{"n": n, "view": "icon", "icon": {"name": "ship"}, "stamp": {"text": "SI"},
                            "points": [{"name": f"P{n}", "lat": -15, "lon": -47}]} for n in range(first, last + 1)]}

    monkeypatch.setattr(llm, "complete_json", answer)
    out = atlas.scenes(ctx, shots)
    assert asked[0] == (1, 25) and (1, 12) in asked and (13, 25) in asked and (26, 30) in asked
    assert all(out[f"s{i}"]["points"] for i in range(1, 31))           # no line left without its scene
    icons = [i for i in range(1, 31) if out[f"s{i}"]["view"] == "icon"]
    assert icons and all(b - a >= atlas.ICON_EVERY for a, b in zip(icons, icons[1:]))
    stamps = [i for i in range(1, 31) if out[f"s{i}"]["stamp"]]
    assert stamps and all(b - a >= atlas.STAMP_EVERY for a, b in zip(stamps, stamps[1:]))


def test_a_close_map_frames_its_places():
    near = atlas.fit_camera(atlas.clean({"camera": {"lat": -23.6, "lon": -46.4, "zoom": 3},
                                         "points": [{"name": "São Paulo", "lat": -23.55, "lon": -46.63},
                                                    {"name": "Santos", "lat": -23.96, "lon": -46.33}]}, None))
    wide = atlas.fit_camera(atlas.clean({"camera": {"lat": -15, "lon": -45, "zoom": 3.5},
                                         "points": [{"name": "Brasília", "lat": -15.8, "lon": -47.9},
                                                    {"name": "Salvador", "lat": -12.97, "lon": -38.5},
                                                    {"name": "Rio", "lat": -22.9, "lon": -43.2}]}, None))
    assert near["camera"]["zoom"] == atlas.MAX_CLOSE and atlas.REGION_ZOOM < wide["camera"]["zoom"] < atlas.MAX_CLOSE
    assert abs(wide["camera"]["lat"] + 17) < 1.5                       # centred on what it draws


def test_quiet_lines_are_filled_before_the_render_and_a_moment_keeps_one_camera(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from pipeline import llm
    from pipeline.context import RunContext

    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "atlas"}})
    shots = [SimpleNamespace(id=f"s{i}", text=f"Frase {i}.", seconds=3.0) for i in range(1, 9)]
    calls = []

    def answer(_ctx, **kw):
        calls.append(kw["system"])
        if "MOMENTOS" in kw["system"]:
            return {"starts": [1, 5]}
        if "RELLENAS" in kw["system"]:
            return {"scenes": [{"n": n, "points": [{"name": f"Extra {n}", "lat": -15 - n, "lon": -48}]} for n in range(2, 9)]}
        cams = {1: {"lat": -15, "lon": -50, "zoom": 1.6}, 2: {"lat": -14, "lon": -52, "zoom": 1.6}, 5: {"lat": 40, "lon": -3, "zoom": 1.6}}
        return {"scenes": [{"n": 1, "camera": cams[1], "points": [{"name": "Brasília", "lat": -15.8, "lon": -47.9}]}]
                + [{"n": n, "camera": cams[2]} for n in (2, 3, 4)]
                + [{"n": 5, "camera": cams[5], "points": [{"name": "Madrid", "lat": 40.4, "lon": -3.7}]}]
                + [{"n": n, "camera": cams[5]} for n in (6, 7, 8)]}

    monkeypatch.setattr(llm, "complete_json", answer)
    out = atlas.scenes(ctx, shots)
    first = [out[f"s{i}"]["camera"] for i in range(1, 5)]
    assert all(c == first[0] for c in first)                                   # one moment, one camera
    assert out["s5"]["camera"] != first[0]                                     # the next moment moves
    assert any("AHORA SOLO RELLENAS" in c for c in calls)                      # the quiet lines were sent to be filled
    assert [p["name"] for p in out["s3"]["points"] if not p.get("kept")] == ["EXTRA 3"]


def test_sentences_join_the_planner_shots_and_segments_last_as_long_as_the_idea():
    from types import SimpleNamespace

    shot = lambda i, a, d, text, kind="broll": SimpleNamespace(id=f"s{i}", from_=a, durationInFrames=d, text=text, type=kind)   # noqa: E731
    todo = [(s, s.from_, s.from_ + s.durationInFrames) for s in
            [shot(0, 0, 90, "Brasil tem uma costa"), shot(1, 90, 90, "de oito mil quilômetros."), shot(2, 180, 60, "Veja."),
             shot(3, 240, 30, "O gráfico.")]]
    lines = atlas.sentences(todo)
    assert [x["text"] for x in lines] == ["Brasil tem uma costa de oito mil quilômetros.", "Veja.", "O gráfico."]
    base = atlas.clean({"camera": {"lat": -15, "lon": -50, "zoom": 1.5}}, None)
    chart = atlas.clean({"view": "chart", "chart": {"kind": "bars", "bars": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]}}, None)
    for x, sc in zip(lines, [{**base, "moment": 0}, {**base, "moment": 0}, {**chart, "moment": 1}]):
        x["scene"] = sc
    segs = atlas._segments(lines + [{"id": "s9", "from": 270, "to": 300, "text": "Fim.", "scene": {**base, "moment": 2}}], 30)
    assert [len(s["lines"]) for s in segs] == [2, 2]          # same moment joined; a 1-s chart takes the next line (MIN_VIEW)


def test_places_the_script_names_are_drawn_by_themselves():
    seen: set[str] = set()
    scene = atlas.auto_places(atlas.clean({"camera": {"lat": -15, "lon": -50, "zoom": 1.5}}, None),
                              "O Brasil tem mais gente em São Paulo do que em Portugal.", seen)
    assert {h["name"] for h in scene["highlight"]} == {"Brazil", "Portugal"}
    assert [c["name"] for c in scene["countries"]] == ["Brazil", "Portugal"] and "Brazil" in seen
    assert [p["name"] for p in scene["points"]] == ["SÃO PAULO"]
    again = atlas.auto_places(atlas.clean({"camera": {"lat": -15, "lon": -50, "zoom": 1.5}}, None), "O Brasil de novo.", seen)
    assert not again["countries"]                                              # the flag card only the first time

def test_a_bar_chart_only_with_the_figures_the_script_says():
    def chart(bars):
        return {"view": "chart", "chart": {"kind": "bars", "title": "População", "unit": "%",
                                           "bars": [{"label": a, "value": v, "unit": "%"} for a, v in bars]}}

    whole = atlas.check_chart(atlas.clean(chart([("Sudeste", 41.8), ("Resto", 55.2)]), None), "O Sudeste tem 41,8% da população.")
    assert [b["value"] for b in whole["chart"]["bars"]] == [41.8, 58.2]           # a whole adds up to 100
    made_up = atlas.check_chart(atlas.clean(chart([("2010", 55.8), ("2022", 54.8), ("2030", 60)]), None),
                                "Em 2010 eram 55,8%; em 2022, 54,8%.")
    assert [b["value"] for b in made_up["chart"]["bars"]] == [55.8, 54.8]         # 60 was never said
    one = atlas.check_chart(atlas.clean(chart([("Sudeste", 41.8), ("Norte", 9)]), None), "O Sudeste tem 41,8%.")
    assert one["view"] == "globe" and one["chart"] is None and one["counter"]["value"] == 41.8
    words = atlas.check_chart(atlas.clean(chart([("A", 3), ("B", 5)]), None), "três contra cinco")
    assert len(words["chart"]["bars"]) == 2                                      # figures in words: not checked


def test_one_dot_per_place_and_no_bare_numbers():
    scene = atlas.clean({"camera": {"lat": -77, "lon": 166, "zoom": 1.5},
                         "points": [{"name": "McMurdo", "lat": -77.8, "lon": 166.7}, {"name": "Base McMurdo", "lat": -77.85, "lon": 166.67}],
                         "tags": [{"text": "3"}, {"text": "257"}]}, None)
    assert [p["name"] for p in scene["points"]] == ["BASE MCMURDO"] and [t["text"] for t in scene["tags"]] == ["257"]
    later = atlas.carry(atlas.clean({"camera": {"lat": -77, "lon": 166, "zoom": 1.5},
                                     "points": [{"name": "Estreito de McMurdo", "lat": -77.9, "lon": 166.5}]}, scene), scene)
    assert [p["name"] for p in later["points"]] == ["ESTREITO DE MCMURDO"]          # not two names on one dot
    polar = atlas.drift({"lat": -78, "lon": 166, "zoom": 1.5}, 2)
    assert 10 < atlas._angle((polar["lat"], polar["lon"]), (-78, 166)) <= atlas.DRIFT_MAX + 1e-6   # moves near a pole too


def test_no_dive_where_the_satellite_has_no_picture():
    mcmurdo = atlas.clean({"view": "sat", "sat": {"lat": -77.85, "lon": 166.67, "zoom": 11, "label": "McMurdo"}}, None)
    assert mcmurdo["view"] == "globe" and mcmurdo["points"][-1]["name"] == "MCMURDO"
    scenes = {f"s{i}": atlas.clean({"camera": {"lat": -60, "lon": 170, "zoom": 1.5}}, None) for i in range(30)}
    scenes["s5"] = atlas.clean({"camera": {"lat": -70, "lon": 170, "zoom": 2},
                                "points": [{"name": "Vostok", "lat": -78.46, "lon": 106.84}]}, None)
    scenes["s15"] = atlas.clean({"camera": {"lat": -36, "lon": 174, "zoom": 2},
                                 "points": [{"name": "Auckland", "lat": -36.85, "lon": 174.76}]}, None)
    atlas.ensure_satellites(scenes, 2)
    assert scenes["s15"]["view"] == "sat" and scenes["s5"]["view"] == "globe"


def test_a_trip_keeps_the_road_travelled_so_far():
    from pipeline.atlas import Journey

    def scene(lat, lon, *routes):
        return {"view": "globe", "camera": {"lat": lat, "lon": lon, "zoom": 2.0},
                "routes": [{"from": list(a), "to": list(b), "label": "x", "dashed": False, "style": "main", "at": ""} for a, b in routes]}

    trip = Journey()
    sao_paulo, bogota, panama, mexico = (-23.5, -46.6), (4.7, -74.1), (9.0, -79.5), (19.4, -99.1)
    first = trip.add(scene(-10, -60, (sao_paulo, bogota)))
    assert len(first["routes"]) == 1                                  # one leg is not a trip yet
    assert trip.add(scene(5, -70))["routes"] == []                    # a view in between: nothing to keep yet
    second = trip.add(scene(7, -77, (bogota, panama)))
    assert [r["to"] for r in second["routes"]] == [list(bogota), list(panama)]
    assert second["routes"][0]["trail"] and second["routes"][0]["label"] == "" and not second["routes"][1].get("trail")
    later = trip.add(scene(15, -90, (panama, mexico)))
    assert [r["to"] for r in later["routes"]] == [list(bogota), list(panama), list(mexico)]
    assert len(trip.add(scene(12, -85))["routes"]) == 3               # a close look on the way: the road stays
    assert trip.add(scene(40, 120))["routes"] == []                   # the other side of the world: not drawn there
    other = trip.add(scene(48, 2, ((48.8, 2.3), (51.5, -0.1))))       # an unrelated route: on its own
    assert len(other["routes"]) == 1


def test_atlas1pt_review_fixes():
    from pipeline.atlas import auto_places, clean, split_far

    # Salvador (Bahia) is a city, not El Salvador's flag
    scene = auto_places(clean({"view": "globe", "camera": {"lat": -13, "lon": -40, "zoom": 2}}, None),
                        "primeiro Salvador, depois o Rio de Janeiro", set())
    assert not scene.get("countries") and not scene.get("highlight")
    # a region of a country is not the whole country tinted; a real country label stays
    out = clean({"view": "globe", "camera": {"lat": -5, "lon": -60, "zoom": 2},
                 "highlight": [{"name": "Brazil", "label": "REGIÃO NORTE"}, {"name": "United States of America", "label": "EUA"}]}, None)
    assert [h["name"] for h in out["highlight"]] == ["United States of America"]
    # bars of 0 and a counter of 0 are the model's blanks
    out = clean({"view": "chart", "camera": {"lat": 0, "lon": 0, "zoom": 1}, "counter": {"value": 0, "label": "X"},
                 "chart": {"kind": "bars", "title": "CRESCIMENTO", "bars": [{"label": "Centro-Oeste", "value": 0}, {"label": "Média", "value": 0}]}}, None)
    assert out["view"] == "globe" and out["chart"] is None and out["counter"] is None
    # a ring named like the dot it circles: one name
    out = clean({"view": "globe", "camera": {"lat": -15, "lon": -47, "zoom": 5},
                 "points": [{"name": "Cerrado", "lat": -15, "lon": -47}], "rings": [{"lat": -15, "lon": -47, "km": 500, "label": "CERRADO"}]}, None)
    assert out["rings"][0]["label"] == ""
    # the coast band, with its label as a tag on the coast
    out = clean({"view": "globe", "camera": {"lat": -15, "lon": -45, "zoom": 2},
                 "band": {"country": "Brazil", "km": 150, "label": "150 km", "lat": -23.9, "lon": -46.3, "at": "linha"}}, None)
    assert out["band"] == {"country": "Brazil", "km": 150.0, "at": "linha"} and out["tags"][0]["text"] == "150 km"
    assert clean({"view": "globe", "camera": {"lat": 0, "lon": 0, "zoom": 1}, "band": {"country": "Atlantis", "km": 1}}, None)["band"] is None
    # one moment from the Tietê to the Mississippi is cut where it jumps across the world
    tiete = {"view": "globe", "points": [{"name": "TIETÊ", "lat": -23.5, "lon": -45.9}]}
    santos = {"view": "globe", "points": [{"name": "SANTOS", "lat": -23.9, "lon": -46.3}]}
    miss = {"view": "globe", "points": [{"name": "MISSISSIPPI", "lat": 32, "lon": -91}]}
    assert split_far([tiete, santos, {"view": "globe"}, miss], [1]) == [1, 4]


def test_darien_review_fixes():
    from pipeline.atlas import REGION_ZOOM, clean, moment_camera

    # Yaviza and Turbo, 100 km apart, asked on the whole globe: the moment goes close
    yaviza = clean({"view": "globe", "camera": {"lat": 8, "lon": -77, "zoom": 1.5},
                    "points": [{"name": "Yaviza", "lat": 8.16, "lon": -77.69}, {"name": "Turbo", "lat": 8.09, "lon": -76.73}]}, None)
    tag = clean({"view": "globe", "camera": {"lat": 8, "lon": -77, "zoom": 1.5},
                 "tags": [{"text": "1.845 m", "lat": 7.9, "lon": -77.5}]}, yaviza)
    assert moment_camera([yaviza, tag])["zoom"] >= REGION_ZOOM
    # far apart: still the globe
    far = clean({"view": "globe", "camera": {"lat": 0, "lon": -60, "zoom": 1.5},
                 "points": [{"name": "Acre", "lat": -9, "lon": -70}, {"name": "Bogotá", "lat": 4.7, "lon": -74}]}, None)
    assert moment_camera([far])["zoom"] < REGION_ZOOM
    # a country's label on top of a dot with its name: one name
    out = clean({"view": "globe", "camera": {"lat": 4, "lon": -73, "zoom": 2},
                 "points": [{"name": "Colômbia", "lat": 4.5, "lon": -73}], "highlight": [{"name": "Colombia", "label": "COLÔMBIA"}]}, None)
    assert out["highlight"][0]["label"] == ""


def test_a_stretch_still_quiet_gets_the_lines_key_words():
    from pipeline.atlas import fill_quiet

    globe = lambda: {"view": "globe", "camera": {"lat": 0, "lon": 0, "zoom": 1}}   # noqa: E731
    cleaned = [globe() for _ in range(6)]
    built = [dict(x) for x in cleaned]
    lines = [(f"s{i}", t) for i, t in enumerate([
        "Não é uma ponte quebrada.", "Não é um trecho em obras.", "A estrada simplesmente acaba, no meio do mapa",
        "e recomeça do outro lado.", "A Rodovia Pan-Americana é uma das maiores do planeta.", "Ok."])]
    assert fill_quiet(cleaned, built, lines, [3.0] * 6) == 3                     # 18 s quiet: one every ~5 s
    notes = [c["card"]["title"] for c in cleaned if c.get("card")]
    assert notes[0] == "Não é uma ponte quebrada" and all(len(n.split()) >= 2 for n in notes)
    short = [globe(), globe()]
    assert fill_quiet(short, [dict(x) for x in short], lines[:2], [2.0, 2.0]) == 0   # 4 s: not quiet enough


def test_a_trip_is_one_solid_road_and_is_not_left_lying_about():
    from pipeline.atlas import TRIP_LINES, Journey, drift

    def scene(lat, lon, *routes):
        return {"view": "globe", "camera": {"lat": lat, "lon": lon, "zoom": 2.0},
                "routes": [{"from": list(a), "to": list(b), "label": "", "dashed": True, "style": "main", "at": ""} for a, b in routes]}

    trip = Journey()
    trip.add(scene(-10, -60, ((-10, -68), (-12, -77))))
    second = trip.add(scene(-5, -78, ((-11, -76.5), (-1, -78))))          # starts 1° off the first one's end
    assert second["routes"][1]["from"] == [-12, -77] and not second["routes"][1]["dashed"]
    assert not second["routes"][0]["dashed"]
    for _ in range(TRIP_LINES):
        assert len(trip.add(scene(-5, -78))["routes"]) == 2
    assert trip.add(scene(-5, -78))["routes"] == []                       # the story moved on
    assert drift({"lat": 0, "lon": 0, "zoom": 1.0}, 1)["zoom"] == 1.0     # the whole globe never shrinks


def test_a_tint_stays_while_its_country_is_in_view():
    from pipeline.atlas import TINT_LINES, keep_tint

    state = {"list": [], "left": 0}
    globe = lambda lat, lon, **kw: {"view": "globe", "camera": {"lat": lat, "lon": lon, "zoom": 1.5}, **kw}   # noqa: E731
    keep_tint(globe(-70, 0, highlight=[{"name": "Antarctica", "label": "ANTÁRTIDA", "group": 0}]), state)
    after = keep_tint(globe(-60, 20), state)
    assert after["highlight"] == [{"name": "Antarctica", "label": "", "group": 0}]
    assert keep_tint(globe(40, -100), state).get("highlight") is None          # the other side of the world
    for _ in range(TINT_LINES):
        keep_tint(globe(-60, 20), state)
    assert keep_tint(globe(-60, 20), state).get("highlight") is None            # not for ever
    assert keep_tint({"view": "chart", "camera": {"lat": 0, "lon": 0, "zoom": 1}}, state)["view"] == "chart"


def test_no_view_held_too_long_and_no_close_map_on_the_ice():
    from pipeline.atlas import HOLD_MAX, REGION_ZOOM, off_the_ice, reframe_holds

    def globe(zoom=1.8, **kw):
        return {"view": "globe", "camera": {"lat": -40, "lon": 170, "zoom": zoom}, **kw}

    built = [globe(tags=[{"text": "ETOPS", "lat": -60, "lon": 160, "at": ""}]) for _ in range(12)]
    assert reframe_holds(built, [4.0] * 12) >= 2
    cams = [(b["camera"]["lat"], b["camera"]["lon"], b["camera"]["zoom"]) for b in built]
    assert len(set(cams)) >= 2 and all(1.0 <= z <= 2.6 for _, _, z in cams)
    # changes only after HOLD_MAX seconds of the same framing
    first_change = next(i for i, c in enumerate(cams) if c != cams[0])
    assert first_change * 4.0 >= HOLD_MAX
    close = [globe(zoom=6.0) for _ in range(8)]
    reframe_holds(close, [4.0] * 8)
    assert {b["camera"]["zoom"] for b in close} >= {6.0, 5.1}
    assert all(b["camera"]["zoom"] >= REGION_ZOOM for b in close)
    ice = off_the_ice({"view": "globe", "camera": {"lat": -77.8, "lon": 166.7, "zoom": 6.5}})
    assert ice["camera"]["zoom"] < REGION_ZOOM
    assert off_the_ice({"view": "globe", "camera": {"lat": -23, "lon": -46, "zoom": 6.5}})["camera"]["zoom"] == 6.5


def test_tags_pointing_at_nothing_become_a_note():
    from pipeline import atlas as A

    cam = {"lat": -50, "lon": -60, "zoom": 2.0}
    loose = A.pin_tags({"view": "globe", "camera": cam, "points": [], "routes": [], "rings": [], "highlight": [],
                        "tags": [{"text": "ETOPS", "lat": -55, "lon": -70, "at": "ETOPS"},
                                 {"text": "SEM POUSO", "lat": -57, "lon": -68, "at": ""}]})
    assert loose["tags"] == [] and loose["card"]["kind"] == "note" and loose["card"]["title"] == "ETOPS · SEM POUSO"
    pinned = A.pin_tags({"view": "globe", "camera": cam, "points": [{"name": "USHUAIA", "lat": -54.8, "lon": -68.3}],
                         "routes": [], "rings": [], "highlight": [], "tags": [{"text": "40 min", "lat": -55, "lon": -70, "at": ""}]})
    assert len(pinned["tags"]) == 1 and not pinned.get("card")


def test_a_close_map_with_no_name_opens_to_the_globe():
    from pipeline import atlas as A

    route = {"from": [8, -77], "to": [9, -79], "label": "", "trail": True}
    empty = A.no_empty_close({"view": "globe", "camera": {"lat": 8, "lon": -77, "zoom": 6}, "points": [], "routes": [route],
                              "highlight": [], "rings": []})
    assert empty["camera"]["zoom"] == A.EMPTY_CLOSE_ZOOM
    named = A.no_empty_close({"view": "globe", "camera": {"lat": 8, "lon": -77, "zoom": 6}, "routes": [],
                              "points": [{"name": "YAVIZA", "lat": 8.2, "lon": -77.7}], "highlight": []})
    assert named["camera"]["zoom"] == 6


def _scene(raw, text="", dark=False):
    return atlas.check_scene(atlas.clean({"view": "scene", "scene": raw}, None), text)


def test_a_scene_view_becomes_a_scene_of_the_atlas_schema():
    dial = _scene({"type": "dial", "kicker": "a 35.000 pies sin oxígeno", "title": "Lúcido *un minuto o menos*",
                   "max": 60, "from": 0, "to": 60, "fill": "remaining", "readout": "{value} SEG", "at": "minuto"})
    s = dial["scene"]
    assert dial["view"] == "scene" and s["type"] == "atlas-dial" and s["kicker"] == "A 35.000 PIES SIN OXÍGENO"
    assert s["dial"]["fill"] == "remaining" and s["dial"]["accent"] == "danger" and s["readout"]["style"] == "mono"
    saved = _scene({"type": "dial", "max": 60, "from": 0, "to": 20, "fill": "elapsed", "readout": "~{value} *minutos ahorrados*"},
                   "Ahorra unos 20 minutos por vuelo.")
    assert saved["scene"]["dial"]["accent"] == "good" and saved["scene"]["readout"]["style"] == "serif"
    bars = _scene({"type": "compare", "unit": "km", "bars": [{"label": "Antártida", "value": 2.5}, {"label": "Tíbet", "value": 4.1}],
                   "ghost": {"bar": 1, "value": 5, "label": "2 × Antártida"}}, "La Antártida, 2,5 km; el Tíbet, 4,1 km.")
    b = bars["scene"]
    assert b["type"] == "atlas-bar-compare" and [x["value"] for x in b["bars"]] == [2.5, 4.1]
    assert b["bars"][-1]["valueAccent"] == "danger" and b["ghost"]["value"] == 5 and b["axis"]["max"] >= 5
    assert b["axis"]["format"] == "{v} KM" and b["bars"][0]["display"] == "2.5 km"


def test_a_scene_with_figures_the_script_never_says_goes_back_to_the_globe():
    made_up = _scene({"type": "compare", "bars": [{"label": "A", "value": 7}, {"label": "B", "value": 9}]}, "En A son 7 y en B, 8.")
    assert made_up["view"] == "globe" and made_up["scene"] is None
    one_bar = _scene({"type": "compare", "bars": [{"label": "A", "value": 7}]})
    assert one_bar["view"] == "globe"                                             # one bar compares nothing
    density = _scene({"type": "density", "boxes": [{"label": "Mar", "percent": 100}, {"label": "Lhasa", "percent": 70}]},
                     "En Lhasa queda el 70% del aire.")
    assert density["scene"]["boxes"][1]["accent"] == "danger"
    unknown = _scene({"type": "pie", "values": [1, 2]})
    assert unknown["view"] == "globe"


def test_scene_times_turn_words_into_seconds_from_the_group():
    s = atlas.clean({"view": "scene", "scene": {"type": "cards", "title": "Cuando *no salen* las cuentas",
                                                  "cards": [{"text": "Una ruta de escape", "at": "ruta"},
                                                            {"text": "Un avión más ligero", "at": "ligero"}]}}, None)["scene"]
    words = [(0, "Hay"), (15, "una"), (30, "ruta"), (60, "o"), (90, "un"), (120, "avión"), (150, "más"), (180, "ligero.")]
    timed = atlas.scene_times(s, words, 210, 30, 5)
    assert [c["at"] for c in timed["cards"]] == [{"t": 1.0}, {"t": 6.0}]
    agenda = atlas.scene_times(atlas.clean({"view": "scene", "scene": {"type": "agenda", "title": "Cinco razones",
                                                                         "tagline": "Cruzar es *lo fácil*"}}, None)["scene"],
                               words, 210, 30, 5)
    assert len(agenda["numerals"]) == 5 and all("t" in n for n in agenda["numerals"]) and "t" in agenda["tagline"]["at"]
    recap = atlas.scene_times(atlas.clean({"view": "scene", "scene": {"type": "recap", "items": ["a", "b", "c", "d", "e", "f"]}}, None)["scene"],
                              words, 210, 30, 5)
    assert len(recap["items"]) == 5                                             # one card per chapter
