import pytest

from pipeline import graphics, ideas, planner, report
from pipeline.config import PROJECT_ROOT, ConfigError
from pipeline.context import RunContext


def _root(tmp_path, base="canal: a\nbrand: {accent: '#111', canvas: '#000'}\nx: 1\n"):
    (tmp_path / "config.yaml").write_text(base)
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "a.yaml").write_text("brand: {accent: '#aaa'}\nx: 2\n")
    (tmp_path / "canales" / "b.yaml").write_text("brand: {accent: '#bbb'}\nformat: ranking\n")
    return tmp_path


def test_profile_sits_between_base_and_video(tmp_path):
    root = _root(tmp_path)
    ctx = RunContext.create("v", root=root)
    assert ctx.channel == "a" and ctx.config["brand"] == {"accent": "#aaa", "canvas": "#000"} and ctx.config["x"] == 2
    (root / "materiales" / "v").mkdir(parents=True)
    (root / "materiales" / "v" / "config.yaml").write_text("canal: b\nx: 3\n")
    ctx = RunContext.create("v", root=root)
    assert ctx.channel == "b" and ctx.config["brand"]["accent"] == "#bbb" and ctx.config["x"] == 3
    assert ctx.config["format"] == "ranking"
    assert RunContext.create("_ideas", root=root, channel="b").channel == "b"


def test_unknown_profile_is_an_error(tmp_path):
    root = _root(tmp_path)
    with pytest.raises(ConfigError, match="a, b"):
        RunContext.create("v", root=root, channel="zzz")


def test_repo_profiles_load():
    gym = RunContext.create("_t", root=PROJECT_ROOT, channel="gimnasia")
    robots = RunContext.create("_t", root=PROJECT_ROOT, channel="robots")
    assert gym.config["brand"]["accent"] != robots.config["brand"]["accent"]
    assert robots.config["format"] == "ranking" and robots.section("people")["enabled"] is False
    assert robots.section("video")["fps"] == gym.section("video")["fps"]          # the rest comes from config.yaml
    assert ideas.ideas_dir(robots).name == "robots"


def test_ranking_outline_hint():
    assert "RANKING" in planner.outline_system(RunContext.create("_t", root=PROJECT_ROOT, channel="robots"))
    assert "RANKING" not in planner.outline_system(RunContext.create("_t", root=PROJECT_ROOT, channel="gimnasia"))


SENTS = [{"n": i, "start": i * 6.0, "end": i * 6.0 + 5.5, "text": t} for i, t in enumerate([
    "Estas son las ciudades con más robots.",
    "En el número tres está Shenzhen.",
    "Allí trabajan 900 robots en fábricas.",
    "Número dos: Pekín, la capital.",
    "Y en el puesto uno, Shanghái.",
    "Tiene 1200 robots.",
])]


def test_ranking_cards_and_maps(tmp_path, monkeypatch):
    items = [{"rank": 3, "sentence": 1, "name": "Shenzhen", "place": "Shenzhen, China", "country": "China",
              "stats": [{"label": "Robots", "value": "900"}, {"label": "Fábricas", "value": "77"}]},
             {"rank": 5, "sentence": 3, "name": "Pekín"},                       # "cinco" is never said there
             {"rank": 1, "sentence": 4, "name": "Shanghái", "subtitle": "China", "place": None}]
    monkeypatch.setattr(graphics, "complete_json", lambda *a, **k: {"total": 3, "items": items})
    monkeypatch.setattr(graphics, "geocode", lambda ctx, q: (114.1, 22.5))
    monkeypatch.setattr(graphics, "country_names", lambda root: {"China"})
    ctx = RunContext.create("x", root=tmp_path, config={"format": "ranking"})
    out = graphics.ranking(ctx, SENTS)
    # «Número dos: Pekín» opens a position in the script itself: it gets its card although the LLM called it 5
    assert [(o["graphic"]["type"], o["graphic"].get("rank")) for o in out] == [("rank", 3), ("map", None), ("rank", 2),
                                                                              ("rank", 1)]
    assert out[2]["graphic"]["name"] == "Pekín, la capital"
    assert out[0]["graphic"]["stats"] == [{"label": "Robots", "value": "900"}] and out[0]["graphic"]["total"] == 3
    assert out[1]["start"] == out[0]["end"] and out[1]["graphic"]["countries"] == ["China"]
    assert out[1]["graphic"]["zoom"] == 0


def test_report_without_protagonist():
    text = report.text({"person": "", "protagonist": 0.0, "stock": 0.02, "weak": [], "wrong": [], "problems": []})
    assert "en pantalla" not in text and text.startswith("✅")


def test_every_countdown_position_of_the_script_gets_its_card(tmp_path, monkeypatch):
    texts = ["Esta es la cuenta atrás de los récords.", "Número diez.", "El relevo de Seúl.", "Corrieron cuatro.",
             "Número nueve.", "La reina del heptatlón.", "Siete pruebas.", "Antes del número uno, hablemos de otros.",
             "Número uno.", "El más antiguo de todos.", "Múnich."]
    sents = [{"n": i, "start": i * 10.0, "end": i * 10.0 + 9, "text": t} for i, t in enumerate(texts)]
    assert [(n, r, name) for n, r, name in graphics.countdown_marks(sents)] == [
        (1, 10, "El relevo de Seúl"), (4, 9, "La reina del heptatlón"), (8, 1, "El más antiguo de todos")]
    # the LLM only found one: the script's marks still give every card, numbered out of 10
    monkeypatch.setattr(graphics, "complete_json", lambda *a, **k: {"total": None, "items": [
        {"rank": 9, "sentence": 5, "name": "Joyner-Kersee", "stats": [{"label": "Puntos", "value": "7"}]}]})
    monkeypatch.setattr(graphics, "country_names", lambda root: set())
    ctx = RunContext.create("x", root=tmp_path, config={"format": "records"})
    out = graphics.ranking(ctx, sents)
    assert [(o["graphic"]["rank"], o["graphic"]["total"], o["graphic"]["name"]) for o in out] == [
        (10, 10, "El relevo de Seúl"), (9, 10, "Joyner-Kersee"), (1, 10, "El más antiguo de todos")]
    assert out[0]["start"] == 10.0 and out[2]["start"] == 80.0


def test_a_channel_built_on_another_takes_its_profile_and_voice(tmp_path):
    import shutil
    from pathlib import Path

    from pipeline import tts
    from pipeline.context import channel_profile

    shutil.copy(Path(__file__).resolve().parents[1] / "config.yaml", tmp_path / "config.yaml")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "gimnasia.yaml").write_text("format: historia\nideas: {about: gim, my_channel: '@yo'}\n")
    (tmp_path / "canales" / "atletismo.yaml").write_text("base: gimnasia\nideas: {about: atle}\n")
    profile = channel_profile(tmp_path, "atletismo")
    assert profile["format"] == "historia" and profile["ideas"] == {"about": "atle", "my_channel": "@yo"}
    assert "base" not in profile
    (tmp_path / "out").mkdir()
    real = tts.voices
    tts.voices = lambda root: {"gimnasia": {"voice_id": "v1"}}
    try:
        assert tts.voice_for(tmp_path, "atletismo") == {"voice_id": "v1"}
        assert tts.voice_for(tmp_path, "negocios") is None
    finally:
        tts.voices = real
