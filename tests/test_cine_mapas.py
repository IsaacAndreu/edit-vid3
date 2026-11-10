"""The drawn films: stickman cinema (pipeline/cine.py), map explainers (pipeline/mapas.py), their sounds
(pipeline/sfx_synth.py) and their dubbing."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from pipeline.context import RunContext

ROOT = Path(__file__).resolve().parent.parent


def _root(tmp_path):
    shutil.copy(ROOT / "config.yaml", tmp_path / "config.yaml")
    shutil.copytree(ROOT / "canales", tmp_path / "canales")
    (tmp_path / "out").mkdir()
    return tmp_path


def _shots(lines, fps=30, seconds=3):
    return [SimpleNamespace(id=f"s{i}", type="narration", from_=i * seconds * fps, durationInFrames=seconds * fps, text=t)
            for i, t in enumerate(lines)]


def _words(lines, seconds=3):
    out = []
    for i, line in enumerate(lines):
        for k, w in enumerate(line.split()):
            out.append(SimpleNamespace(text=w, start=i * seconds + 0.2 + k * 0.3))
    return SimpleNamespace(words=out)


def test_a_rules_thriller_keeps_its_clock_numbers_each_rule_once_and_ends_on_the_next_day(tmp_path, monkeypatch):
    from pipeline import cine

    root = _root(tmp_path)
    ctx = RunContext.create("reglas1", root=root, channel="reglas-de-la-noche")
    assert cine.active(ctx) and cine.mode(ctx) == "reglas"
    lines = ["Imagina que te despiertas a las seis cuarenta y dos.", "Te llega un mensaje de ti mismo.",
             "Regla uno: no abras la puerta.", "Otra vez: no abras la puerta.", "¿Abres la puerta?"]
    scenes = [
        {"n": 1, "set": "bedroom", "shot": "wide", "light": "cold", "hud": {"day": "1", "clock": "6:42 AM"}, "keys": ["despiertas"]},
        {"n": 2, "set": "living", "shot": "pov-phone", "phone": {"from": "Yo", "messages": ["No vayas a trabajar."]}},
        {"n": 3, "set": "door", "shot": "medium", "rule": {"n": 1, "text": "no abras la puerta"}, "actors": [{"who": "hero", "pose": "kick"}]},
        {"n": 4, "set": "door", "shot": "close", "rule": {"n": 1, "text": "no abras la puerta"}, "hud": {"clock": "11:58 PM"}},
        {"n": 5, "set": "door", "shot": "wide", "choice": {"question": "¿Abres?", "a": "Abrir", "b": "Quedarte"}},
    ]
    monkeypatch.setattr("pipeline.llm.complete_json", lambda *a, **k: {"scenes": scenes})
    out = cine.groups(ctx, _shots(lines), 30, [], _words(lines))
    g = [x["graphic"] for x in out]
    assert [x["hud"]["clock"] for x in g[:5]] == ["6:42 AM", "6:42 AM", "6:42 AM", "11:58 PM", "11:58 PM"]
    assert g[1]["hud"]["day"] == "DÍA 1"
    assert g[2]["rule"] == {"n": 1, "text": "NO ABRAS LA PUERTA", "word": "REGLA"} and "rule" not in g[3]   # once
    assert g[2]["actors"][0]["pose"] == "stand"                       # out of the vocabulary: the default
    assert g[1]["shot"] == "pov-phone" and g[1]["phone"]["messages"] == ["No vayas a trabajar."]
    assert g[0]["words"][0] == {"t": "Imagina", "f": 6, "key": False}
    assert any(w["key"] for w in g[0]["words"] if w["t"] == "despiertas")
    assert g[4]["choice"]["comment"] == "COMENTA ABAJO"
    assert out[-1]["id"] == "cine-end" and out[-1]["graphic"]["end"]["follow"] == "SIGUE PARA EL DÍA 2"
    assert out[-1]["from"] == out[-2]["from"] + out[-2]["durationInFrames"]


def test_a_what_if_film_has_no_clock_and_no_captions_unless_asked(tmp_path, monkeypatch):
    from pipeline import cine

    root = _root(tmp_path)
    ctx = RunContext.create("ysi1", root=root, channel="y-si-animado")
    lines = ["¿Y si tus reflejos fueran diez veces más rápidos?"]
    monkeypatch.setattr("pipeline.llm.complete_json", lambda *a, **k: {"scenes": [
        {"n": 1, "set": "lab", "shot": "close", "hud": {"day": "1", "clock": "9:00"}, "counter": {"label": "reflejos", "value": "10x"}}]})
    g = cine.groups(ctx, _shots(lines), 30, [], _words(lines))[0]["graphic"]
    assert "hud" not in g and "words" not in g and g["counter"] == {"label": "REFLEJOS", "value": "10x"}
    assert g["hero"] == {"mark": "cap", "color": "#ffcc00"}
    assert "¿Y SI" in cine.writing(ctx)


def test_a_broken_answer_still_gives_a_shot_per_line(tmp_path, monkeypatch):
    from pipeline import cine

    root = _root(tmp_path)
    ctx = RunContext.create("ysi2", root=root, channel="disciplina-animada")

    def fail(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr("pipeline.llm.complete_json", fail)
    out = cine.groups(ctx, _shots(["Una.", "Dos."]), 30, [], _words(["Una.", "Dos."]))
    assert len(out) == 2 and all(x["graphic"]["actors"][0]["who"] == "hero" for x in out)


def test_a_map_line_keys_each_element_to_its_word_and_flies_from_the_last_camera(tmp_path, monkeypatch):
    from pipeline import mapas

    root = _root(tmp_path)
    ctx = RunContext.create("mapa1", root=root, channel="mapas-explicados")
    assert mapas.active(ctx)
    lines = ["Desde esta isla puedes ver el mañana.", "Rusia y Estados Unidos están a cuatro kilómetros."]
    monkeypatch.setattr("pipeline.llm.complete_json", lambda *a, **k: {"scenes": [
        {"n": 1, "center": {"lat": 65.78, "lon": -169.06}, "zoom": 12, "circle": {"lat": 65.78, "lon": -169.06, "word": "mañana", "at": "isla"}},
        {"n": 2, "center": {"lat": 60, "lon": -170}, "zoom": 3, "tags": [{"name": "Rusia", "sub": "", "lat": 65.78, "lon": -169.06, "at": "Rusia"}],
         "line": {"points": [[65.77, -169.03], [65.75, -168.95]], "count": "3,8 km", "dashed": True, "at": "kilómetros"},
         "highlight": [{"name": "Russia", "label": "Rusia"}], "zoom_bad": 99}]})
    monkeypatch.setattr(mapas, "satellite_layers", lambda ctx, lat, lon, zoom: [{"z": 13, "lat": lat, "lon": lon, "src": "x.jpg"}])
    out = mapas.groups(ctx, _shots(lines), 30, [], _words(lines))
    a, b = out[0]["graphic"], out[1]["graphic"]
    assert a["prev"] == {"lat": 65.78, "lon": -169.06, "zoom": 12.0}            # the first line starts where it is
    assert b["prev"] == {"lat": 65.78, "lon": -169.06, "zoom": 12.0}            # then flies from there
    assert a["circle"]["at"] == round((0.2 + 2 * 0.3) * 30)                    # «isla» is the third word
    assert b["tags"][0]["at"] == 6 and b["tags"][0]["name"] == "RUSIA"
    assert b["line"]["at"] == round((0.2 + 7 * 0.3) * 30) and b["line"]["count"] == "3,8 KM"
    assert b["highlight"] == [{"name": "Russia", "label": "RUSIA"}]
    assert a["sat"] and b["sat"] and "Sentinel-2" in a["credit"]                # b pulls out from the satellite
    assert mapas.moments(out, 30, 1)


def test_the_land_is_cut_out_over_a_drawn_sea(tmp_path):
    from PIL import Image

    from pipeline.mapas import land_over_sea

    img = Image.new("RGB", (200, 120), (10, 40, 120))                     # sea: bluer than red
    for x in range(60, 140):
        for y in range(30, 90):
            img.putpixel((x, y), (150, 120, 80))                          # land: redder than blue
    img.save(tmp_path / "raw.jpg")
    land_over_sea(tmp_path / "raw.jpg", tmp_path / "out.jpg")
    out = np.asarray(Image.open(tmp_path / "out.jpg")).astype(int)
    assert abs(out[60, 100] - [150, 120, 80]).max() < 20                    # the land stays
    corner = out[2, 2]
    assert corner[2] < 70 and corner[0] < 30                                # the sea is the drawn navy


def test_every_sound_is_made_finite_and_short(tmp_path):
    from pipeline import sfx_synth

    for name, make in sfx_synth.SOUNDS.items():
        x = make()
        assert len(x) > 100 and np.isfinite(x).all() and np.abs(x).max() <= 1.0, name
        assert len(x) / sfx_synth.SR < 2.0, name
    path = sfx_synth.path(tmp_path, "whoosh-up")
    assert path.is_file() and path.stat().st_size > 1000


def test_a_whoosh_rises_like_the_reference(tmp_path):
    from pipeline import sfx_synth

    x = sfx_synth.SOUNDS["whoosh-up"]()
    n = 2048
    f = np.fft.rfftfreq(n, 1 / sfx_synth.SR)

    def centre(seg):
        s = np.abs(np.fft.rfft(seg * np.hanning(n)))
        return (s * f).sum() / s.sum()

    assert centre(x[2000:2000 + n]) < 3000 < centre(x[-4000 - n:-4000])


def test_the_cues_follow_the_events():
    from pipeline import sfx_synth

    cine = sfx_synth.cine_cues({"type": "cine", "rule": {"n": 1, "text": "X", "at": 12}, "shot": "peephole"}, 30, False)
    assert ("slap", 12, 0.55) in cine and any(c[0] == "heartbeat" for c in cine) and cine[0][0] == "swipe"
    mapa = sfx_synth.mapa_cues({"type": "mapa", "lat": 60, "lon": -170, "zoom": 3, "prev": {"lat": 65, "lon": -169, "zoom": 12},
                                "tags": [{"at": 9}], "stamp": {"at": 20}, "props": [{"at": 4, "flip": {"top": "LUNES"}}]}, 30)
    names = [c[0] for c in mapa]
    assert names[0] == "whoosh-up" and "stamp" in names and "flip" in names and ("paper", 9, 0.45) in mapa


def test_a_dub_translates_only_what_is_on_screen():
    from pipeline import dub

    g = {"type": "cine", "set": "door", "shot": "wide", "rule": {"n": 1, "text": "NO ABRAS LA PUERTA", "word": "REGLA"},
         "phone": {"from": "Yo", "messages": ["No vayas."]}, "actors": [{"label": "TÚ", "pose": "stand", "who": "hero"}]}
    texts = {}
    dub._graphic_strings(g, "g", texts)
    assert set(texts) == {"g.rule.text", "g.rule.word", "g.phone.from", "g.phone.messages.0", "g.actors.0.label"}
    done = dub._set_graphic_strings(g, "g", {k: "DE" for k in texts})
    assert done["rule"]["text"] == "DE" and done["set"] == "door" and done["phone"]["messages"] == ["DE"] and g["phone"]["messages"] == ["No vayas."]
    m = {"type": "mapa", "highlight": [{"name": "Russia", "label": "RUSIA"}], "tags": [{"name": "RUSIA", "sub": "", "lat": 1, "lon": 2}]}
    texts = {}
    dub._graphic_strings(m, "m", texts)
    assert set(texts) == {"m.highlight.0.label", "m.tags.0.name"}                # never «Russia» (the map's key)


def test_drawn_films_dub_with_a_native_voice(tmp_path):
    import json

    from pipeline import doblaje

    root = _root(tmp_path)
    (root / "out" / "_voces.json").write_text(json.dumps({"y-si-animado": {"voice_id": "es", "name": "ES"},
                                                          "was-waere-wenn": {"voice_id": "de", "name": "DE"}}), "utf-8")
    cfg = doblaje.settings(RunContext.create("x", root=root, channel="y-si-animado"))
    assert cfg["enabled"] and cfg["languages"] == ["de"] and cfg["voices"]["de"]["voice_id"] == "de"
    (root / "out" / "_voces.json").write_text(json.dumps({"y-si-animado": {"voice_id": "es", "name": "ES"}}), "utf-8")
    assert not doblaje.settings(RunContext.create("x", root=root, channel="y-si-animado"))["enabled"]   # never Spanish reading German


def test_shorts_are_told_apart_from_long_videos(tmp_path):
    from pipeline.web import is_short

    root = _root(tmp_path)
    folder = root / "materiales" / "el-porque-simulado" / "atasco-short2"
    folder.mkdir(parents=True)
    assert is_short(root, folder, "el-porque-simulado")                       # made from a long video
    plain = root / "materiales" / "el-porque-simulado" / "atasco"
    plain.mkdir()
    assert not is_short(root, plain, "el-porque-simulado")
    assert is_short(root, plain, "reglas-de-la-noche")                         # a vertical channel
    (plain / "config.yaml").write_text("serie: short\n", "utf-8")
    assert is_short(root, plain, "el-porque-simulado")


def test_the_new_scenes_are_offered_to_the_planner():
    import json

    worlds = json.loads((ROOT / "remotion" / "sim" / "worlds.json").read_text("utf-8"))
    kitchen = worlds["restaurante"]["params"]
    assert {"cocina", "comparar", "sentar", "mesas", "noche", "herbie"} <= set(kitchen["scene"]["options"])
    assert kitchen["regla"]["options"] == ["juntos", "centro"] and "plancha2" in kitchen["arreglo"]["options"]
    town = worlds["contagio"]["params"]
    assert {"oficina", "oficinas", "snow", "super"} <= set(town["scene"]["options"]) and "ventana" in town["que"]["options"]
    assert "oficina" in worlds["contagio"]["describe"] and "Lloyd-Smith" in worlds["contagio"]["describe"]
