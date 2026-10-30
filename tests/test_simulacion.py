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
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
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
    assert scene["params"] == {"cars": 30}
    assert simulacion.clean({"world": "contagio", "params": {"mode": "bulo", "quarantine": "1"}}, "x", None)["params"]["mode"] == "bulo"
    assert simulacion.clean({"world": "contagio", "params": {"mode": "zombi"}}, "x", None)["params"]["mode"] == "virus"
    nothing = simulacion.clean({}, "x", scene)
    assert nothing["world"] == "anillo" and nothing["params"] == {"cars": 30}             # no answer: the same experiment


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
            assert visual.get("theme", "day") in ("day", "night", "sepia"), path
