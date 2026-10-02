"""Beyond Sky style: flat maps with the date, the area's name and company logos; newspaper articles."""

from pathlib import Path

from pipeline.context import RunContext
from pipeline.graphics import clean

TEXT = ("El 17 de noviembre de 2013, en el Salón de Dubái, Emirates y Qatar Airways firmaron pedidos del 777X. "
        "A precio de catálogo, los 259 aviones suman más de 95.000 millones de dólares, según The Seattle Times.")


def ctx(tmp_path):
    return RunContext.create("t", root=tmp_path, config={})


def test_map_keeps_a_said_date_the_area_name_and_named_logos(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.graphics.geocode", lambda c, q: (55.27, 25.2))
    data = {"countries": ["United Arab Emirates"], "date": "17 de noviembre de 2013", "region_label": "Salón de Dubái",
            "points": [{"name": "Dubái", "query": "Dubai", "logo": "Emirates"}, {"name": "Doha", "logo": "Etihad"}]}
    g = clean("map", data, TEXT, ctx(tmp_path), {"United Arab Emirates"})
    assert g["date"] == "17 de noviembre de 2013" and g["regionLabel"] == "Salón de Dubái"
    assert [p["logo"] for p in g["points"]] == ["Emirates", None]        # Etihad is never named
    g = clean("map", {**data, "date": "18 de noviembre de 2014"}, TEXT, ctx(tmp_path), {"United Arab Emirates"})
    assert g["date"] is None


def test_article_needs_the_scripts_words_and_circles_inside_the_body(tmp_path):
    data = {"outlet": "The Seattle Times", "author": "Dominic Gates",
            "headline": "Emirates y Qatar Airways firman pedidos del 777X en el Salón de Dubái",
            "body": "A precio de catálogo, los 259 aviones suman más de 95.000 millones de dólares.",
            "circles": ["259 aviones", "95.000 millones", "300 aviones"]}
    g = clean("article", data, TEXT, ctx(tmp_path), set())
    assert g["circles"] == ["259 aviones", "95.000 millones"] and g["outlet"] == "The Seattle Times" and g["author"] is None
    assert clean("article", {**data, "body": "Boeing vendió 600 aviones a Lufthansa en un solo día de 2015 en Berlín."},
                 TEXT, ctx(tmp_path), set()) is None
