"""Simulation videos: the opening with the climax, «¿tú qué harías?», chapters in the description, each world's
sound, Shorts that loop, the new worlds and the «¿Y si…?» series."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from pipeline import simulacion
from pipeline.context import RunContext
from pipeline.schemas import Timeline


def _timeline(scenes: list[dict], fps: int = 30, seconds: int = 20) -> Timeline:
    """One shot and one sim group per scene, `seconds` each."""

    n = seconds * fps
    shots, groups = [], []
    since = 0.0
    for k, g in enumerate(scenes):
        a = k * n
        if k and (scenes[k - 1]["world"], scenes[k - 1].get("params")) != (g["world"], g.get("params")):
            since = a / fps
        shots.append({"id": f"s{k}", "type": "broll", "from": a, "durationInFrames": n, "text": "x"})
        groups.append({"id": f"sim-s{k}", "kind": "graphic", "from": a, "durationInFrames": n,
                       "graphic": {"type": "sim", "focus": "both", "overlay": "none", "params": {}, "title": "", "stat": None,
                                   "source": "", "list": [], "lang": "es", "at": a / fps, "since": since, "prev": "both", **g}})
    return Timeline.model_validate({"slug": "v", "title": "t", "fps": fps, "width": 1920, "height": 1080,
                                    "durationInFrames": n * len(scenes), "shots": shots, "groups": groups,
                                    "audio": {"voice": "voz.mp3", "speech": [[0, n * len(scenes)]]}})


def test_an_ask_only_on_a_line_that_asks_and_two_at_most(tmp_path, monkeypatch):
    assert simulacion.clean({"world": "colas", "ask": "¿qué cola eliges?"}, "¿Qué cola eliges?", None)["ask"] == "¿QUÉ COLA ELIGES?"
    assert "ask" not in simulacion.clean({"world": "colas", "ask": "qué cola"}, "Eliges una cola.", None)
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **k: {"scenes": [
        {"n": n, "world": "colas", "ask": "¿cuál?"} for n in range(1, 6)]})
    shots = [SimpleNamespace(id=f"s{n}", type="broll", from_=n * 60, durationInFrames=60, text=f"¿Pregunta {n}?") for n in range(5)]
    found = simulacion.scenes(ctx, shots)
    asked = [k for k, v in found.items() if v.get("ask")]
    assert asked == ["s1", "s2"]                                  # never the first line, two at most


def test_the_world_and_the_voice_stop_on_the_question():
    tl = _timeline([{"world": "colas"}, {"world": "colas", "ask": "¿CUÁL?", "cues": {"x": 30.0}}, {"world": "colas", "cues": {"x": 30.0}}])
    out = simulacion.with_asks(tl, 30, 3.0)
    assert out.durationInFrames == tl.durationInFrames + 90
    asked = next(g for g in out.groups if g.id == "sim-s1")
    after = next(g for g in out.groups if g.id == "sim-s2")
    assert asked.durationInFrames == 600 + 90 and asked.graphic["askHold"] == 3.0
    assert after.from_ == 1290 and after.graphic["at"] == 43.0 and after.graphic["since"] == 3.0   # the clock goes on where it stopped
    assert after.graphic["cues"] == {"x": 33.0}
    assert out.audio.voiceGaps == [(1200, 90)]
    assert [s.from_ for s in out.shots] == [0, 600, 1290]


def test_the_opening_shows_the_strongest_moment_first():
    tl = _timeline([{"world": "anillo"}, {"world": "carretera", "replay": True}, {"world": "colas", "list": ["A", "B"], "title": "RESUMEN"}])
    key = simulacion.climax(tl.groups, 30)
    assert key["world"] == "carretera" and 20 <= key["at"] <= 21 and key["overlay"] == "none"
    out = simulacion.with_teaser(tl, 30, 5.0)
    assert out.audio.voiceFrom == 150 and out.durationInFrames == tl.durationInFrames + 150
    teaser = out.groups[0]
    assert teaser.id == "sim-teaser" and teaser.from_ == 0 and teaser.graphic["teaser"] is True
    assert out.shots[0].id == "teaser" and out.shots[1].from_ == 150
    road = next(g for g in out.groups if g.id == "sim-s1")
    assert road.graphic["at"] == 25.0 and road.graphic["since"] == 25.0      # everything five seconds later
    assert teaser.graphic["at"] - teaser.graphic["since"] == key["at"] - key["since"]   # the same moment of that world


def test_chapters_in_the_description_at_each_experiment():
    from pipeline.publish import chapter_lines

    tl = _timeline([{"world": "anillo", "title": "EL CÍRCULO DE SUGIYAMA"}, {"world": "anillo"},
                    {"world": "carretera", "title": "POR QUÉ DURA"}, {"world": "colas"}, {"world": "colas", "title": "LA COLA ÚNICA"},
                    {"world": "inundacion", "list": ["A"], "title": "LO QUE HEMOS VISTO"}])
    assert chapter_lines(tl) == ["0:00 El círculo de sugiyama", "0:40 Por qué dura", "1:00 La cola única", "1:40 Lo que hemos visto"]
    short = _timeline([{"world": "anillo", "title": "A"}, {"world": "colas"}])
    assert chapter_lines(short) == []                             # fewer than 3: none (YouTube's rule)


def test_every_world_sounds_its_place(tmp_path):
    folder = tmp_path / "assets" / "sfx" / "sim"
    folder.mkdir(parents=True)
    for stem in simulacion.SOUNDS.values():
        (folder / f"{stem}.wav").write_bytes(b"x")
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion"}})
    published = simulacion.sounds(ctx, lambda path: path.name)
    assert {"murmur", "rain", "crowd", "kitchen", "beep", "ding", "impact"} <= set(published)
    real = Path(simulacion.MANIFEST).parent.parent.parent / "assets" / "sfx" / "sim"
    for stem in simulacion.SOUNDS.values():                       # the repository has them all
        assert any(real.glob(f"{stem}.*")), stem


def test_a_short_ends_on_its_first_scene(tmp_path, monkeypatch):
    ctx = RunContext.create("v-short1", root=tmp_path, config={"visual": {"style": "simulacion", "min_world_seconds": 0},
                                                                 "shorts": {"of": "v"}})
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **k: {"scenes": [
        {"n": 1, "world": "anillo"}, {"n": 2, "world": "colas", "title": "X"}]})
    shots = [SimpleNamespace(id=f"s{n}", type="broll", from_=n * 300, durationInFrames=300, text=f"frase {n}") for n in range(2)]
    groups = simulacion.groups(ctx, shots, 30, [])
    assert groups[-1]["graphic"]["loopTo"]["world"] == "anillo" and "loopTo" not in groups[0]["graphic"]
    from pipeline.shorts import NEW_SYSTEM

    assert "bucle" in NEW_SYSTEM


def test_the_new_worlds_are_there_and_on_the_channel():
    every = simulacion.worlds()
    for name in ("ascensores", "aparcamiento", "aeropuerto", "metro", "restaurante"):
        assert name in every and every[name]["params"]["scene"]["options"], name
    import yaml

    channel = yaml.safe_load(Path("canales/el-porque-simulado.yaml").read_text("utf-8"))
    assert {"ascensores", "aparcamiento", "aeropuerto", "metro", "restaurante"} <= set(channel["visual"]["worlds"])
    assert "y-si" in channel["series"]


def test_the_what_if_series_reaches_the_scenes_and_the_topics(tmp_path, monkeypatch):
    import shutil

    from pipeline import temas

    (tmp_path / "canales").mkdir()
    shutil.copy("canales/el-porque-simulado.yaml", tmp_path / "canales")
    shutil.copy("config.yaml", tmp_path / "config.yaml")
    ctx = RunContext.create("v", root=tmp_path, channel="el-porque-simulado", series="y-si")
    assert "¿Y SI…?" in simulacion.series_guide(ctx) and "¿Y SI…?" in simulacion.writing(ctx)
    seen = {}

    def fake(ctx, **kwargs):
        seen["system"] = kwargs["system"]
        return {"ideas": [{"title": "¿Y si hubiera una caja más?", "worlds": ["colas"], "dial": "tills", "hook": "h"},
                          {"title": "¿Y si nadie frenara?", "worlds": ["anillo"], "dial": "inventado"}]}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    monkeypatch.setattr("pipeline.repeticion.recent_titles", lambda root, channel: [])
    ideas = temas.propose(tmp_path, "el-porque-simulado", 5, "y-si")
    assert "«¿Y si…?»" in seen["system"]
    assert [i["title"] for i in ideas] == ["¿Y si hubiera una caja más?"] and ideas[0]["dial"] == "tills"   # a real dial only


def test_a_rule_is_never_cut_and_keeps_its_words(tmp_path, monkeypatch):
    rule = simulacion.clean({"world": "red", "rules": [{"text": "Su carga pasa a las vecinas"}]}, "x", None)["rules"][0]
    assert rule["text"] == "SU CARGA PASA A LAS VECINAS"                       # sim3 showed «SU CARGA PASA A LAS»
    assert simulacion._rule("cada línea tiene un límite un poco por encima de su") == "CADA LÍNEA TIENE UN LÍMITE UN POCO"
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": "simulacion", "min_world_seconds": 0}})
    plan = [[{"text": "su carga pasa a las vecinas"}], [], [{"text": "carga a las vecinas"}, {"text": "se desconecta"}]]
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **k: {"scenes": [
        {"n": n, "world": "apagon", "rules": r, "title": f"T{n}"} for n, r in enumerate(plan, 1)]})
    shots = [SimpleNamespace(id=f"s{n}", type="broll", from_=n * 300, durationInFrames=300, text=f"frase {n}") for n in range(3)]
    groups = simulacion.groups(ctx, shots, 30, [])
    first, carried, more = (g["graphic"] for g in groups)
    assert not first.get("rulesMini") and carried["rulesMini"] is True               # explained, then put in a corner
    assert [r["text"] for r in more["rules"]] == ["SU CARGA PASA A LAS VECINAS", "SE DESCONECTA"]   # the same words
    assert not more.get("rulesMini")                                                   # a new rule: shown big


def test_the_same_picture_for_minutes_is_a_warning():
    fps = 30
    sims = [{"from": k * 1800, "durationInFrames": 1800, "graphic": {"type": "sim", "world": "red", "params": {"margin": 0.2}}}
            for k in range(5)]                                                        # 5 minutes of one map (sim3)
    found = simulacion.monotony(sims, fps)
    assert any("min seguidos en el mismo mundo" in w for w in found)
    assert any("la misma escena" in w for w in found)
    varied = [{"from": k * 1800, "durationInFrames": 1800, "graphic": {"type": "sim", "world": "apagon" if k < 2 else "anillo",
                                                                          "params": {"scene": ["cascada", "frecuencia", "x", "y", "z"][k]}}}
              for k in range(5)]
    assert simulacion.monotony(varied, fps) == []


def test_the_grid_world_has_its_scenes_and_follows_the_language():
    w = simulacion.worlds()["apagon"]
    assert set(w["params"]["scene"]["options"]) == {"cascada", "reparto", "combado", "frecuencia", "inercia", "arena", "arranque", "isla"}
    assert w["params"]["pais"]["default"] == "auto" and {"iberia", "alemania", "brasil", "eeuu"} <= set(w["params"]["pais"]["options"])
    assert "apagon" in simulacion.worlds()["red"]["describe"]                            # the old map sends the LLM here
