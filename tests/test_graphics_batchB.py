"""Tanda B: tier list, iceberg and cost breakdown (receipt)."""

from pipeline import graphics
from pipeline.config import PROJECT_ROOT
from pipeline.context import RunContext

SENTS = [{"n": i, "start": 10.0 * i, "end": 10.0 * i + 8, "text": t} for i, t in enumerate([
    "Hoy clasifico los supermercados de España.",
    "Mercadona va directo al nivel S.",
    "Lidl se queda en el nivel A por poco.",
    "Y Dia, lo siento, nivel D.",
    "Un local cuesta 2.000.000 €, las obras 1.500.000 €, la maquinaria 800.000 € y el total 4.300.000 €.",
])]


def _ctx(fmt):
    return RunContext.create("_t", root=PROJECT_ROOT, config={"format": fmt, "graphics": {"types": ["map"]}})


def test_tier_list_places_each_element_with_the_board_so_far(monkeypatch):
    monkeypatch.setattr(graphics, "complete_json", lambda ctx, **kw: {"tiers": ["S", "A", "B", "C", "D"], "items": [
        {"sentence": 1, "name": "Mercadona", "tier": "S"}, {"sentence": 2, "name": "Lidl", "tier": "A"},
        {"sentence": 3, "name": "Dia", "tier": "D"}, {"sentence": 3, "name": "Carrefour", "tier": "B"},   # not said
        {"sentence": 2, "name": "Aldi", "tier": "Z"}]})
    out = graphics.tier(_ctx("tier-list"), SENTS)
    assert [o["graphic"]["current"] for o in out] == [0, 1, 2]
    assert [i["name"] for i in out[-1]["graphic"]["items"]] == ["Mercadona", "Lidl", "Dia"]
    assert out[0]["graphic"]["items"] == [{"name": "Mercadona", "tier": "S"}]


def test_iceberg_sinks_level_by_level(monkeypatch):
    sents = [{"n": i, "start": 20.0 * i, "end": 20.0 * i + 15, "text": t} for i, t in enumerate([
        "Nivel uno: lo que sabe todo el mundo.", "La marca Hacendado es suya.",
        "Nivel dos: lo que saben los empleados.", "El sistema de turnos rotativos.",
        "Nivel tres: lo que nadie cuenta.", "Los proveedores totaler."])]
    monkeypatch.setattr(graphics, "complete_json", lambda ctx, **kw: {
        "levels": [{"sentence": 0, "title": "Lo que sabe todo el mundo"}, {"sentence": 2, "title": "Lo que saben los empleados"},
                   {"sentence": 4, "title": "Lo que nadie cuenta"}],
        "items": [{"sentence": 1, "name": "Hacendado", "level": 1}, {"sentence": 3, "name": "turnos rotativos", "level": 2},
                  {"sentence": 5, "name": "Algo inventado", "level": 3}]})
    out = graphics.iceberg(_ctx("iceberg"), sents)
    assert [o["graphic"]["current"] for o in out] == [0, 1, 2]
    assert out[1]["graphic"]["items"] == [{"name": "Hacendado", "level": 0}]
    assert [i["name"] for i in out[2]["graphic"]["items"]] == ["Hacendado", "turnos rotativos"]


def test_receipt_keeps_only_said_figures():
    text = SENTS[4]["text"]
    clean = graphics.clean("receipt", {"title": "Abrir un súper", "items": [
        {"label": "Local", "value": "2.000.000 €"}, {"label": "Obras", "value": "1.500.000 €"},
        {"label": "Maquinaria", "value": "800.000 €"}, {"label": "Luz", "value": "9.999 €"}],
        "total": {"label": "TOTAL", "value": "4.300.000 €"}}, text, None, set())
    assert [i["label"] for i in clean["items"]] == ["Local", "Obras", "Maquinaria"] and clean["total"]["value"] == "4.300.000 €"
    assert graphics.clean("receipt", {"items": [{"label": "a", "value": "2.000.000 €"}]}, text, None, set()) is None


def test_formats_bring_their_own_graphic_types(monkeypatch):
    seen = {}
    monkeypatch.setattr(graphics, "complete_json", lambda ctx, **kw: seen.update(kw) or {"graphics": []})
    graphics.plan(_ctx("cuanto-cuesta"), SENTS * 8, 400)
    assert "receipt" in seen["system"].split("Tipos permitidos en este canal:")[1]
    for name in ("tier-list", "iceberg", "cuanto-cuesta"):
        assert RunContext.create("_t", root=PROJECT_ROOT, config={"format": name}).format["guion"]
