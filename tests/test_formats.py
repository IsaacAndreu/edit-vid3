import pytest

from pipeline import formats, graphics, planner
from pipeline.config import PROJECT_ROOT, ConfigError
from pipeline.context import RunContext

NEW = ["explicativo", "cronologia", "investigacion", "que-fue-de", "mitos", "misterio"]
OLD = ["historia", "ranking", "prohibidos", "tecnica", "final", "rivalidad", "records", "lista"]


def test_every_format_is_a_file_with_its_prompt():
    found = formats.available(PROJECT_ROOT)
    assert set(OLD + NEW) <= set(found)
    for name, data in found.items():
        assert data.get("nombre") and data.get("descripcion"), name
        if name != "historia":
            assert data.get("guion"), name
    for name in NEW:
        data = found[name]
        assert data.get("graficos") and data.get("titulos") and data.get("segundos_por_grafico"), name
        mentioned = {t for t in graphics.TYPES if f'"{t}"' in data["graficos"]}
        assert mentioned and mentioned <= set(graphics.TYPES), name


def test_format_reaches_the_planner_and_graphics():
    for name, word in [("explicativo", "EXPLICA"), ("cronologia", "CRONOLOGÍA"), ("investigacion", "INVESTIGACIÓN"),
                       ("que-fue-de", "QUÉ FUE DE"), ("mitos", "MITOS"), ("misterio", "MISTERIO"), ("ranking", "RANKING")]:
        ctx = RunContext.create("_t", root=PROJECT_ROOT, config={"format": name})
        assert word in planner.outline_system(ctx), name
    assert "EXPLICA" not in planner.outline_system(RunContext.create("_t", root=PROJECT_ROOT, config={"format": "historia"}))


def test_unknown_format_fails_early(tmp_path):
    (tmp_path / "config.yaml").write_text("format: nope\n")
    with pytest.raises(ConfigError, match="explicativo"):
        RunContext.create("v", root=tmp_path)


def test_series_adds_to_its_format():
    ctx = RunContext.create("_t", root=PROJECT_ROOT, channel="negocios", series="auge-caida")
    system = planner.outline_system(ctx)
    assert "CRONOLOGÍA" in system and "AUGE Y CAÍDA" in system
    assert ctx.format["segundos_por_grafico"] == 60


def test_listing_names_every_format():
    text = formats.listing(PROJECT_ROOT)
    assert all(name in text for name in OLD + NEW)
