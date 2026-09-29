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
    assert [(o["graphic"]["type"], o["graphic"].get("rank")) for o in out] == [("rank", 3), ("map", None), ("rank", 1)]
    assert out[0]["graphic"]["stats"] == [{"label": "Robots", "value": "900"}] and out[0]["graphic"]["total"] == 3
    assert out[1]["start"] == out[0]["end"] and out[1]["graphic"]["countries"] == ["China"]
    assert out[1]["graphic"]["zoom"] == 0


def test_report_without_protagonist():
    text = report.text({"person": "", "protagonist": 0.0, "stock": 0.02, "weak": [], "wrong": [], "problems": []})
    assert "en pantalla" not in text and text.startswith("✅")
