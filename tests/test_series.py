import json

import pytest

from pipeline import graphics, ideas, planner, series_report
from pipeline.config import PROJECT_ROOT, ConfigError
from pipeline.context import RunContext


def _root(tmp_path):
    (tmp_path / "config.yaml").write_text("x: 1\ngraphics: {types: [map]}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "n.yaml").write_text(
        "brand: {accent: '#0f0'}\nideas: {about: canal, my_channel: '@yo'}\n"
        "series:\n"
        "  estafas: {graphics: {types: [press], hint: usa press}, planner: {outline: TRUE CRIME}, ideas: {about: estafas}}\n"
        "  auge: {format: ranking, package: {hint: patrón auge}}\n")
    return tmp_path


def _video(root, slug, text):
    (root / "materiales" / slug).mkdir(parents=True)
    (root / "materiales" / slug / "config.yaml").write_text(text)


def test_series_sits_between_channel_and_video(tmp_path):
    root = _root(tmp_path)
    _video(root, "v", "canal: n\nserie: estafas\nx: 3\n")
    ctx = RunContext.create("v", root=root)
    assert ctx.series == "estafas" and ctx.section("graphics")["types"] == ["press"]
    assert ctx.section("ideas") == {"about": "estafas", "my_channel": "@yo"} and ctx.config["x"] == 3
    assert "series" not in ctx.config and ctx.config["brand"]["accent"] == "#0f0"
    assert "TRUE CRIME" in planner.outline_system(ctx)
    assert RunContext.create("_i", root=root, channel="n", series="auge").config["format"] == "ranking"
    assert RunContext.create("_i", root=root, channel="n").series == ""
    assert RunContext.create("_i", root=root, channel="n", series="auge").section("package")["hint"] == "patrón auge"


def test_unknown_series_is_an_error(tmp_path):
    root = _root(tmp_path)
    with pytest.raises(ConfigError, match="estafas, auge"):
        RunContext.create("_i", root=root, channel="n", series="zzz")


def test_repo_business_series_load():
    catalog = ideas.series_of(RunContext.create("_t", root=PROJECT_ROOT, channel="negocios"))
    assert list(catalog) == ["auge-caida", "estafas", "negocio-oculto", "deporte-dinero", "economia"]
    for name in catalog:
        ctx = RunContext.create("_t", root=PROJECT_ROOT, channel="negocios", series=name)
        allowed = set(graphics.TYPES)
        assert set(ctx.section("graphics")["types"]) <= allowed, name
        assert ctx.section("planner").get("outline") and ctx.section("ideas").get("about") and ctx.section("lab")["queries"]
    video = RunContext.create("Video1", root=PROJECT_ROOT)
    assert video.channel == "negocios" and video.series == "negocio-oculto"


def test_weekly_asks_one_idea_per_series(tmp_path, monkeypatch):
    root = _root(tmp_path)
    seen = []
    monkeypatch.setattr(ideas, "gather", lambda ctx: ([{"id": ctx.series, "title": "t"}], []))

    def propose(ctx, outliers, best, count, taken):
        seen.append((ctx.series, count, list(taken)))
        return [{"title": f"idea {ctx.series}", "hook": "h"}]

    monkeypatch.setattr(ideas, "propose", propose)
    monkeypatch.setattr(ideas.notify, "send", lambda *a, **k: None)
    out = ideas.weekly("n", root=root)
    assert [s[:2] for s in seen] == [("estafas", 1), ("auge", 1)]
    assert "idea estafas" in seen[1][2]                               # no repeats inside the week
    text = out.read_text("utf-8")
    assert "[estafas] idea estafas" in text and "serie: auge" in text
    history = json.loads((root / "out" / "_ideas" / "n" / "historial.json").read_text("utf-8"))
    assert {h["serie"] for h in history} == {"estafas", "auge"}
    ctx = RunContext.create("v", root=root, channel="n", series="auge")
    assert ideas.outliers_path(ctx).name == "outliers-auge.json"


def test_series_report_groups_uploads_by_series(tmp_path, monkeypatch):
    root = _root(tmp_path)
    _video(root, "a", "canal: n\nserie: estafas\nestadisticas: {ctr: 6.0, retencion: 40}\n")
    (root / "materiales" / "a" / "titulo.txt").write_text("La estafa de Fórum Filatélico")
    _video(root, "b", "canal: n\nserie: auge\nyoutube: https://www.youtube.com/watch?v=BBBBBBBBBBB\n")
    _video(root, "c", "canal: n\nserie: auge\n")
    (root / "materiales" / "c" / "titulo.txt").write_text("Algo que no se publicó")
    _video(root, "g", "canal: otro\nserie: auge\n")
    uploads = [{"id": "AAAAAAAAAAA", "title": "LA ESTAFA de FORUM FILATELICO", "views": 900, "viewsPerDay": 90, "ratio": 2.0},
               {"id": "BBBBBBBBBBB", "title": "otro título", "views": 300, "viewsPerDay": 30, "ratio": 0.7}]
    monkeypatch.setattr(series_report, "channel_uploads", lambda ctx, handle: uploads)
    text = series_report.report("n", root=root).read_text("utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| estafas") or line.startswith("| auge")]
    assert rows[0].startswith("| estafas | 1 | 900 | 90 | 2.0 | 6.0 % | 40 %")
    assert rows[1].startswith("| auge | 1 | 300")
    assert "- c" in text and "- g" not in text



def test_videos_inside_a_channel_folder_take_its_config(tmp_path):
    from main import pending_slugs
    from pipeline.context import RunContext

    root = _root(tmp_path)
    group = root / "materiales" / "n"
    (group / "avion1").mkdir(parents=True)
    (group / "config.yaml").write_text("canal: n\n")
    for name in ("guion.txt", "voz.mp3"):
        (group / "avion1" / name).write_text("x")
    (root / "materiales" / "_hechos" / "viejo").mkdir(parents=True)
    for name in ("guion.txt", "voz.mp3"):
        (root / "materiales" / "_hechos" / "viejo" / name).write_text("x")
    ctx = RunContext.create("avion1", root=root)
    assert ctx.materials_dir == group / "avion1" and ctx.channel == "n"
    assert ctx.work_dir == root / "work" / "avion1"
    assert pending_slugs(root) == ["avion1"]                 # _hechos/ is never processed


def test_config_local_yaml_is_this_machines_layer_on_top_of_config_yaml(tmp_path):
    from pipeline.context import RunContext

    root = _root(tmp_path)
    (root / "config.local.yaml").write_text("sourcing:\n  youtube:\n    cookies: never\n")
    ctx = RunContext.create("x", root=root)
    assert ctx.section("sourcing")["youtube"]["cookies"] == "never"
