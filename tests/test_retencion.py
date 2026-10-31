"""Where viewers leave (pipeline/retencion.py): YouTube Studio's retention CSV against the video's own timeline."""

from __future__ import annotations

from pipeline import retencion
from pipeline.context import RunContext


def _timeline():
    sim = lambda a, n, world, **k: {"id": f"g{a}", "kind": "graphic", "from": a, "durationInFrames": n,  # noqa: E731
                                    "graphic": {"type": "sim", "world": world, "overlay": "none", "params": {}, **k}}
    return {"fps": 30, "durationInFrames": 30 * 300,
            "shots": [{"id": f"s{i}", "type": "broll", "from": i * 900, "durationInFrames": 900, "text": f"frase {i}"} for i in range(10)],
            "groups": [sim(0, 30 * 150, "anillo"), sim(30 * 150, 30 * 150, "colas", params={"scene": "limite"})]}


def test_the_drops_are_found_with_what_was_said_and_seen(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={})
    ctx.write_json("timeline.json", _timeline())
    # a CSV like YouTube Studio's: position as a fraction, absolute retention in %; a cliff at 2:40 (160 s)
    rows = ["Video position,Absolute audience retention (%)"]
    for k in range(101):
        t = k * 3
        r = 100 - t * 0.12 - (15 if t >= 165 else 0) - max(0, (t - 159)) * 2.5 * (159 < t < 165)
        rows.append(f"{k / 100:.2f},{r:.1f}")
    monkeypatch.setattr(retencion, "advice", lambda ctx, r: ["Adelanta la escena de la caja"])
    result = retencion.analyse(ctx, "\n".join(rows))
    assert result["hook30"] > 95 and result["drops"]
    big = max(result["drops"], key=lambda d: d["loss"])
    assert 145 <= big["at"] <= 165 and "colas · limite" in big["seen"] and "frase" in big["said"]
    report = (ctx.out_dir / "retencion.md").read_text("utf-8")
    assert "Dónde se va la gente" in report and "Adelanta la escena" in report


def test_times_and_fractions_are_read():
    curve = retencion.parse("pos;ret\n0:00;100\n0:30;80\n1:00;70\n1:30;65\n2:00;60\n", 120)
    assert curve[1] == (30.0, 80.0)
    frac = retencion.parse("a,b\n0,1\n0.25,0.8\n0.5,0.7\n0.75,0.6\n1,0.5\n", 200)
    assert frac[1] == (50.0, 80.0)


def test_topic_ideas_only_with_the_channels_worlds_and_one_a_day(tmp_path, monkeypatch):
    import shutil
    from datetime import date
    from pathlib import Path

    from pipeline import agenda, temas

    root = Path(__file__).resolve().parent.parent
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    shutil.copytree(root / "canales", tmp_path / "canales")
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **k: {"ideas": [
        {"title": "Por qué el metro se colapsa", "hook": "Llegas al andén…", "worlds": ["multitud"], "scenes": "pasillo", "why": "x"},
        {"title": "Algo imposible", "worlds": ["volcan"]},
        {"title": "Por qué el wifi va lento", "worlds": ["colas"], "scenes": "limite"}]})
    added = temas.calendar(tmp_path, "el-porque-simulado", 10, start=date(2026, 11, 2))
    assert [a["title"] for a in added] == ["Por qué el metro se colapsa", "Por qué el wifi va lento"]
    assert [a["date"] for a in added] == ["2026-11-02", "2026-11-03"] and "Mundos: multitud" in added[0]["note"]
    assert len(agenda.load(tmp_path)["ideas"]) == 2


def _sim_root(tmp_path):
    import json
    import shutil
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    shutil.copytree(root / "canales", tmp_path / "canales")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "_voces.json").write_text(json.dumps({
        "el-porque-simulado": {"voice_id": "es-voice", "name": "Narrador ES"},
        "simulated-why": {"voice_id": "en-voice", "name": "Narrator EN"}}), "utf-8")
    return tmp_path


def test_a_simulation_dubs_only_where_there_is_a_voice_of_that_language(tmp_path):
    from pipeline import doblaje
    from pipeline.web import create_video

    root = _sim_root(tmp_path)
    opts = {o["lang"]: o["voice"] for o in doblaje.options(root, "el-porque-simulado")}
    assert opts == {"en": "Narrator EN", "pt": None, "de": None}          # never the Spanish voice reading German
    ctx = RunContext.create("x", root=root, channel="el-porque-simulado")
    cfg = doblaje.settings(ctx)
    assert cfg["enabled"] and cfg["languages"] == ["en"] and cfg["voices"]["en"]["voice_id"] == "en-voice"
    script = "Vas al súper con prisa y eliges la cola más corta. " * 10
    create_video(root, {"name": "super1", "channel": "el-porque-simulado", "script": script, "dub": []})
    none = RunContext.create("super1", root=root)
    assert none.config.get("dub_languages") == [] and not doblaje.settings(none)["enabled"]
    create_video(root, {"name": "super2", "channel": "el-porque-simulado", "script": script, "dub": ["en", "de"]})
    chosen = doblaje.settings(RunContext.create("super2", root=root))
    assert chosen["enabled"] and chosen["languages"] == ["en"]                # German ticked but it has no voice


def test_a_dub_is_adapted_to_its_viewers(tmp_path, monkeypatch):
    from pipeline import doblaje

    root = _sim_root(tmp_path)
    folder = root / "materiales" / "el-porque-simulado" / "atasco1"
    folder.mkdir(parents=True)
    (root / "materiales" / "el-porque-simulado" / "config.yaml").write_text("canal: el-porque-simulado\n", "utf-8")
    script = "Vas por la autovía y todo se para. " * 20
    (folder / "guion.txt").write_text(script, "utf-8")
    seen = {}

    def fake(ctx, **k):
        seen.update(k)
        return {"title": "Stau aus dem Nichts", "script": "Du fährst auf der Autobahn und alles steht. " * 20,
                "changes": ["autovía → Autobahn", "añadido el apagón europeo de 2006 (río Ems)"]}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    ctx = RunContext.create("atasco1", root=root)
    assert doblaje.translate(ctx, "de")
    assert "Alemania, Austria y Suiza" in seen["system"] and "Autobahn" in seen["system"] and "Ems" in seen["system"]
    assert "Autobahn" in (folder / "guion-de.txt").read_text("utf-8")
    assert "río Ems" in (folder / "adaptacion-de.md").read_text("utf-8")
