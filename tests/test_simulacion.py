"""Simulation videos (pipeline/simulacion.py): every scene keeps to the vocabulary the component draws, figures only
when the narrator says them, and the shots become groups that keep one continuous simulation per world."""

from __future__ import annotations

from types import SimpleNamespace

from pipeline import simulacion, stickman
from pipeline.context import RunContext


def test_a_scene_keeps_to_the_vocabulary_and_never_invents_a_figure():
    scene = simulacion.clean({"world": "volcan", "focus": "top", "overlay": "explosion", "title": "por qué pasa esto ahora mismo aquí",
                              "stat": {"label": "espera media", "value": "40 %"}, "list": ["uno", "dos"]},
                             "Con semáforo esperas mucho más.", None)
    assert scene["world"] == "cruces" and scene["focus"] == "both" and scene["overlay"] == "none"
    assert scene["title"] == "POR QUÉ PASA ESTO AHORA" and scene["stat"] is None          # 40 is not in the line
    assert scene["list"] == ["UNO", "DOS"]
    said = simulacion.clean({"world": "cruces", "focus": "left", "overlay": "queue", "stat": {"label": "puntos de choque", "value": "32"}},
                            "En un cruce hay 32 puntos de choque.", None)
    assert said["stat"] == {"label": "PUNTOS DE CHOQUE", "value": "32"} and said["focus"] == "left"
    ring = simulacion.clean({"world": "anillo", "focus": "left"}, "x", None)
    assert ring["focus"] == "ring"                                                         # a focus of the other world
    assert simulacion.clean({}, "x", {"world": "anillo"})["world"] == "anillo"            # no answer: the world goes on


def test_a_simulation_video_is_drawn_in_code(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    assert simulacion.active(ctx) and stickman.drawn(ctx) and not stickman.active(ctx)


def _shot(n, a, b, text="frase"):
    return SimpleNamespace(id=f"s{n:03d}", type="broll", from_=a, durationInFrames=b - a, text=text)


def test_shots_become_groups_with_one_clock_per_world(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion", "min_world_seconds": 0}})
    shots = [_shot(n, (n - 1) * 90, n * 90, f"frase {n}") for n in range(1, 7)]
    plan = {1: {"world": "cruces", "focus": "both", "overlay": "labels"},
            2: {"world": "cruces", "focus": "both", "overlay": "labels"},           # the same scene: one group with s001
            3: {"world": "cruces", "focus": "left", "overlay": "queue"},
            4: {"world": "anillo", "focus": "ring", "overlay": "speed"},
            5: {"world": "anillo", "focus": "chart", "overlay": "chart"},
            6: {"world": "cruces", "focus": "right", "overlay": "yield"}}
    calls = []

    def fake(ctx, **kwargs):         # answers line by line, as the LLM does: [n] frase k
        calls.append(kwargs["user"])
        lines = kwargs["user"].splitlines()
        return {"scenes": [{"n": n, **plan[int(line.split()[-1])]} for n, line in enumerate(lines, 1)]}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    chapter = SimpleNamespace(from_=180, durationInFrames=30)          # a card on top: that stretch is not simulated
    groups = simulacion.groups(ctx, shots, 30, [chapter])
    assert [g["id"] for g in groups] == ["sim-s001", "sim-s004", "sim-s005", "sim-s006"]
    first, ring, chart, back = groups
    assert first["durationInFrames"] == 180 and first["graphic"]["since"] == 0
    assert ring["graphic"]["since"] == 9 and ring["graphic"]["prev"] == "ring"            # a new world: its clock starts
    assert chart["graphic"]["since"] == 9 and chart["graphic"]["prev"] == "ring"          # same world: the camera moves
    assert back["graphic"]["since"] == 15 and back["graphic"]["prev"] == "right"          # back to the junctions: anew
    assert back["graphic"]["at"] == 15
    simulacion.groups(ctx, shots, 30, [chapter])
    assert len(calls) == 1                                                                  # cached by the lines


def test_the_groups_are_valid_timeline_groups(tmp_path, monkeypatch):
    from pipeline.schemas import TimelineGroup

    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **k: {"scenes": [{"n": 1, "world": "anillo", "overlay": "jam"}]})
    for group in simulacion.groups(ctx, [_shot(1, 0, 60)], 30, []):
        assert TimelineGroup.model_validate(group).graphic["type"] == "sim"


def test_the_ring_gets_the_voices_cues_for_the_brake_and_the_jam(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    plan = ["speed", "brake", "none", "jam"]
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **k: {"scenes": [
        {"n": n, "world": "anillo", "focus": "ring", "overlay": o} for n, o in enumerate(plan, 1)]})
    groups = simulacion.groups(ctx, [_shot(n, (n - 1) * 60, n * 60, f"frase {n}") for n in range(1, 5)], 30, [])
    assert {g["graphic"]["cues"]["brake"] for g in groups} == {2.0}
    assert {g["graphic"]["cues"]["jam"] for g in groups} == {6.0}


def test_the_simulation_sounds_are_published_from_assets(tmp_path):
    folder = tmp_path / "assets" / "sfx" / "sim"
    folder.mkdir(parents=True)
    for name in ("ambiente.mp3", "clic.wav"):
        (folder / name).write_bytes(b"x")
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    published = simulacion.sounds(ctx, lambda path: f"audio/{path.name}")
    assert published == {"ambient": "audio/ambiente.mp3", "click": "audio/clic.wav"}       # no tick file: no tick


def test_paths_is_in_the_junctions_vocabulary():
    assert simulacion.clean({"world": "cruces", "overlay": "paths"}, "x", None)["overlay"] == "paths"


def test_every_world_in_the_manifest_is_complete_and_drawn():
    import re
    from pathlib import Path

    registry = Path(simulacion.MANIFEST).with_name("registry.ts").read_text()
    for name, w in simulacion.worlds().items():
        assert w["describe"] and w["focus"] and w["overlay"], name
        for p in (w.get("params") or {}).values():
            assert "default" in p and ("options" in p or p["min"] <= p["default"] <= p["max"])
        assert re.search(rf"\b{name}\b", registry), f"{name} is in worlds.json but not in registry.ts"


def test_parameters_stay_within_their_limits_and_go_on_with_the_world():
    scene = simulacion.clean({"world": "anillo", "params": {"cars": 99}}, "x", None)
    assert scene["params"] == {"cars": 30, "driver": "normal"}
    assert simulacion.clean({"world": "anillo", "params": {"driver": "suave"}}, "x", None)["params"]["driver"] == "suave"
    assert simulacion.clean({"world": "contagio", "params": {"mode": "bulo", "quarantine": "1"}}, "x", None)["params"]["mode"] == "bulo"
    assert simulacion.clean({"world": "contagio", "params": {"mode": "zombi"}}, "x", None)["params"]["mode"] == "virus"
    nothing = simulacion.clean({}, "x", scene)
    assert nothing["world"] == "anillo" and nothing["params"] == {"cars": 30, "driver": "normal"}             # no answer: the same experiment


def test_a_source_is_shown_only_when_the_line_names_it():
    named = simulacion.clean({"source": "Sugiyama et al., 2008"}, "Sugiyama lo comprobó en 2008 con 22 coches.", None)
    assert named["source"] == "Sugiyama et al., 2008"
    assert simulacion.clean({"source": "Universidad de Harvard"}, "Un estudio lo comprobó.", None)["source"] == ""


def test_a_channel_uses_only_its_worlds_and_the_llm_reads_them(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion", "worlds": ["contagio", "nada"]}})
    assert list(simulacion.allowed(ctx)) == ["contagio"]
    text = simulacion.describe(simulacion.allowed(ctx))
    assert '"contagio"' in text and '"cruces"' not in text and "vaccinated" in text
    assert "contagio" in simulacion.writing(ctx)


def test_a_new_experiment_restarts_the_clock_and_the_look_comes_with_every_shot(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion", "theme": "night"},
                                                         "align": {"language": "pt"}, "brand": {"accent": "#19fe5b"}})
    plan = [{"world": "anillo", "params": {"cars": 22}}, {"world": "anillo", "params": {"cars": 22}, "overlay": "speed"},
            {"world": "anillo", "params": {"cars": 28}, "overlay": "jam"}]
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **k: {"scenes": [{"n": n, **p} for n, p in enumerate(plan, 1)]})
    groups = simulacion.groups(ctx, [_shot(n, (n - 1) * 60, n * 60, f"frase {n}") for n in range(1, 4)], 30, [])
    assert [g["graphic"]["since"] for g in groups] == [0, 0, 4]                           # 28 cars: a new run
    assert groups[2]["graphic"]["cues"] == {"jam": 4.0}
    assert {(g["graphic"]["lang"], g["graphic"]["accent"], g["graphic"]["theme"]) for g in groups} == {("pt", "#19fe5b", "night")}


def test_thumbnail_moments_one_per_experiment_longest_first():
    def group(start, frames, world, since):
        return {"from": start, "durationInFrames": frames, "graphic": {"type": "sim", "world": world, "since": since}}

    groups = [group(0, 150, "anillo", 0), group(150, 300, "anillo", 0), group(450, 100, "cruces", 15),
              group(550, 90, "cruces", 15), {"from": 640, "durationInFrames": 30, "graphic": {"type": "chart"}}]
    assert simulacion.moments(groups, 30, 2) == [12.5, 20.58]        # late in the last shot of each run
    assert len(simulacion.moments(groups, 30, 4)) == 4               # then other shots fill the count


def test_niche_profiles_use_known_worlds():
    import yaml
    from pathlib import Path

    known = set(simulacion.worlds())
    for path in Path("canales").glob("*.yaml"):
        visual = (yaml.safe_load(path.read_text("utf-8")) or {}).get("visual") or {}
        if visual.get("style") == "simulacion":
            assert set(visual.get("worlds") or []) <= known, path
            assert visual.get("theme", "day") in ("day", "night", "sepia", "dark"), path


def test_depth_off_by_default_and_files():
    from types import SimpleNamespace

    from pipeline import depth

    ctx = SimpleNamespace(section=lambda name: {})
    timeline = SimpleNamespace(shots=[])
    assert depth.add(ctx, timeline) is timeline
    assert depth.files({"src": "a.jpg"}) == set()
    assert depth.files({"src": "a.jpg", "cutout": "depth/x.png"}) == {"depth/x.png", "depth/x-plate.jpg"}


def test_no_sim_track_without_simulation_sounds():
    from types import SimpleNamespace

    from pipeline.render import sim_track

    timeline = {"groups": [{"from": 0, "durationInFrames": 30, "graphic": {"type": "chart"}},
                           {"from": 30, "durationInFrames": 30, "graphic": {"type": "sim"}}],
                "durationInFrames": 60, "fps": 30}
    assert sim_track(SimpleNamespace(), timeline) is None          # no Remotion call when there is nothing to sound


def test_the_recap_list_only_at_the_end():
    scenes = {f"s{n}": {"list": ["UNO", "DOS"]} for n in range(20)}
    simulacion.recap(scenes, [f"s{n}" for n in range(20)])
    assert [n for n in range(20) if scenes[f"s{n}"]["list"]] == [17, 18, 19]


def test_a_question_does_not_stop_the_simulation(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    shots = [_shot(1, 0, 90), _shot(2, 90, 180)]
    monkeypatch.setattr(simulacion, "scenes", lambda ctx, todo: {s.id: simulacion.clean({}, s.text, None) for s in todo})
    question = SimpleNamespace(kind="question", from_=0, durationInFrames=90)
    card = SimpleNamespace(kind="graphic", from_=90, durationInFrames=90)
    assert [g["from"] for g in simulacion.groups(ctx, shots, 30, [question])] == [0]          # one group over both
    assert [g["from"] for g in simulacion.groups(ctx, shots, 30, [question, card])] == [0]
    assert simulacion.groups(ctx, shots, 30, [question, card])[0]["durationInFrames"] == 90


def test_a_simulation_video_has_no_chapter_cards_and_no_planner_cards(tmp_path):
    from pipeline import capitulos, planner

    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    (ctx.materials_dir).mkdir(parents=True, exist_ok=True)
    (ctx.materials_dir / "guion.txt").write_text("\n\n".join(f"Párrafo {n}." for n in range(8)), "utf-8")
    assert capitulos.ensure(ctx) is False                       # never asks for chapters
    shot = {"id": "s001", "type": "stat", "stat": {"value": "22", "label": "coches"}, "chapterTitle": "CAPÍTULO",
            "text": "22 coches", "broll": {"q": "x"}}
    assert planner.drawn_shot(shot) == {"id": "s001", "type": "broll", "text": "22 coches", "broll": {"q": "x"}}


def test_a_world_stays_at_least_twelve_seconds():
    scene = lambda world, **k: {"world": world, "focus": "f-" + world, "overlay": "x", "params": {}, "title": "", **k}  # noqa: E731
    found = {"a": scene("anillo"), "b": scene("autovia", title="CREMALLERA"), "c": scene("anillo"), "d": scene("cruces"),
             "e": scene("cruces")}
    spans = [("a", 0, 450), ("b", 450, 600), ("c", 600, 900), ("d", 900, 1200), ("e", 1200, 1500)]
    out = simulacion.steady(found, spans, 30)
    assert [out[k]["world"] for k in "abcde"] == ["anillo", "anillo", "anillo", "cruces", "cruces"]
    assert out["b"]["title"] == "CREMALLERA" and out["b"]["overlay"] == "none" and out["b"]["focus"] == "f-anillo"
    assert found["b"]["world"] == "autovia"                                    # the scenes given are not changed
    first = simulacion.steady({"a": scene("autovia"), "b": scene("anillo")}, [("a", 0, 90), ("b", 90, 900)], 30)
    assert first["a"]["world"] == "anillo"                                     # a short opening joins the next world


def test_marks_and_figures_on_the_word_the_voice_says_them():
    words = [SimpleNamespace(text=t, start=i * 0.5) for i, t in enumerate(
        "Mira este coche: frena. Diez coches atrás hay 22 parados y la onda va hacia atrás".split())]
    group = {"from": 0, "durationInFrames": 300, "graphic": {"type": "sim", "world": "anillo",
                                                           "stat": {"label": "PARADOS", "value": "22"}}}
    simulacion.sync([group], words, lambda s: round(s * 30), 30)
    g = group["graphic"]
    assert g["statAt"] == 4.0
    assert [(m["kind"], m["at"], m["text"]) for m in g["marks"]] == [("car", 0.5, "ESTE COCHE"), ("jam", 5.5, "LA ONDA")]


def test_flags_for_the_zoom_between_worlds_and_one_legend(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion", "min_world_seconds": 0}})
    shots = [_shot(n, (n - 1) * 90, n * 90, f"frase {n}") for n in range(1, 4)]
    worlds = {1: "anillo", 2: "anillo", 3: "cruces"}
    monkeypatch.setattr(simulacion, "scenes", lambda ctx, todo: {
        s.id: simulacion.clean({"world": worlds[int(s.id[1:])], "title": s.id}, s.text, None) for s in todo})
    g = [x["graphic"] for x in simulacion.groups(ctx, shots, 30, [])]
    assert [(x["enter"], x["exit"]) for x in g] == [(True, False), (False, True), (True, True)]
    assert [x.get("legend", "") for x in g] == ["right", "", ""]


def test_the_check_after_the_render(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    sim = lambda a, n, world, **k: {"from": a, "durationInFrames": n, "graphic": {"type": "sim", "world": world, **k}}  # noqa: E731
    timeline = {"fps": 30, "durationInFrames": 2400, "groups": [
        sim(0, 900, "anillo", stat={"value": "22"}, list=["UNO"]),
        sim(900, 150, "autovia", replay=True, title="X"),
        sim(1050, 900, "anillo", marks=[{"at": 1.0}, {"at": 1.4}])]}
    found = simulacion.qa(ctx, timeline)
    assert any("autovia" in f and "5 s" in f for f in found)
    assert any("cifra y el resumen" in f for f in found) and any("pausa" in f for f in found)
    assert any("dos flechas" in f for f in found)
    assert (ctx.out_dir / "qa" / "simulacion.md").is_file()


def test_one_panel_at_a_time():
    both = simulacion.clean({"world": "anillo", "focus": "ring", "overlay": "jam", "stat": {"label": "coches", "value": "22"}},
                            "Pusieron 22 coches en una pista.", None)
    assert both["stat"] and both["overlay"] == "none"
    mark = simulacion.clean({"world": "anillo", "focus": "ring", "overlay": "brake", "stat": {"label": "coches", "value": "22"}},
                            "Pusieron 22 coches en una pista.", None)
    assert mark["overlay"] == "brake"                                 # a mark on the road is not a panel


def test_one_general_simulation_channel_per_language_and_the_niches_put_away():
    from pathlib import Path

    from pipeline.web import channel_kinds

    root = Path(__file__).resolve().parent.parent
    kinds = channel_kinds(root)
    langs = {c: RunContext.create("x", root=root, channel=c).section("align").get("language")
             for c in ("el-porque-simulado", "simulated-why", "porque-simulado-pt", "simuliertes-warum")}
    assert langs == {"el-porque-simulado": "es", "simulated-why": "en", "porque-simulado-pt": "pt", "simuliertes-warum": "de"}
    assert all(kinds[c] == "simulacion" for c in langs)
    assert all(kinds[c] == "oculto" for c in ("hora-punta", "cola-de-al-lado", "simule-el-mundo"))
    assert "colas" in RunContext.create("x", root=root, channel="simuliertes-warum").section("visual")["worlds"]


def test_rules_stay_and_one_is_switched_off_and_the_dial_turns(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion", "min_world_seconds": 0}})
    shots = [_shot(n, (n - 1) * 90, n * 90, f"frase {n}") for n in range(1, 5)]
    answers = {1: {"world": "anillo", "rules": [{"text": "acelera"}, {"text": "frena si hace falta"}], "title": "a"},
               2: {"world": "anillo", "title": "b"},
               3: {"world": "anillo", "title": "c", "params": {"driver": "calma"},
                   "rules": [{"text": "acelera"}, {"text": "frena si hace falta"}, {"text": "despistes", "off": True}]},
               4: {"world": "anillo", "title": "d", "params": {"driver": "calma", "cars": 28}}}
    monkeypatch.setattr(simulacion, "scenes", lambda ctx, todo: {
        s.id: simulacion.clean(answers[int(s.id[1:])], s.text, None) for s in todo})
    g = [x["graphic"] for x in simulacion.groups(ctx, shots, 30, [])]
    assert [len(x["rules"]) for x in g] == [2, 2, 3, 3]
    assert g[1]["rulesFrom"] == 2 and g[2]["rulesFrom"] == 2 and g[2]["rulesOff"] == [2] and g[3]["rulesOff"] == []
    assert g[3]["dial"]["from"] == 22 and g[3]["dial"]["to"] == 28 and g[3]["dial"]["label"] == "COCHES EN LA PISTA"
    assert "dial" not in g[2]


def test_the_directors_scene_list_goes_to_the_llm(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion", "guide": "Una idea por escena."}})
    ctx.materials_dir.mkdir(parents=True, exist_ok=True)
    (ctx.materials_dir / "escenas.txt").write_text("Escena 1 · el protagonista amarillo en la cola", "utf-8")
    seen = {}

    def fake(ctx, **kwargs):
        seen.update(kwargs)
        return {"scenes": []}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    simulacion.scenes(ctx, [_shot(1, 0, 90, "Vas al súper.")])
    assert "GUÍA DEL CANAL" in seen["system"] and "Una idea por escena" in seen["system"]
    assert "protagonista amarillo en la cola" in seen["system"]
