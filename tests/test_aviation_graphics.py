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


def test_satellite_needs_a_named_place_and_builds_centred_layers(tmp_path, monkeypatch):
    import io

    from PIL import Image

    from pipeline import satellite

    monkeypatch.setattr("pipeline.graphics.geocode", lambda c, q: (-122.2741, 47.9217))
    text = "En la fábrica de Boeing en Everett, junto a Paine Field, se montaba el 777X."
    g = clean("satellite", {"place": "Fábrica de Boeing en Everett", "query": "Boeing Everett Factory",
                            "labels": [{"name": "Paine Field"}, {"name": "Toulouse"}]}, text, ctx(tmp_path), set())
    assert g["place"] == "Fábrica de Boeing en Everett" and [l["name"] for l in g["labels"]] == ["Paine Field"]
    assert clean("satellite", {"place": "Hangar de Airbus en Hamburgo"}, text, ctx(tmp_path), set()) is None

    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (40, 90, 60)).save(buf, "JPEG")
    calls = []
    monkeypatch.setattr(satellite, "_tile", lambda c, src, z, x, y, s: calls.append((src, z)) or buf.getvalue())
    c = ctx(tmp_path)
    ready = satellite.prepare(c, g)
    assert [l["z"] for l in ready["layers"]] == [10, 12, 14, 16]
    assert {src for src, z in calls if z <= 12} == {"eox"} and {src for src, z in calls if z >= 14} == {"usgs"}
    assert "USGS" in ready["credit"] and "CC BY 4.0" in ready["credit"]
    assert Image.open(c.work_dir / ready["layers"][0]["media"]["src"]).size == (1920, 1080)
    abroad = satellite.prepare(c, {**g, "lon": 1.36, "lat": 43.63, "labels": []})        # Toulouse: Sentinel only
    assert [l["z"] for l in abroad["layers"]] == [7, 9, 11, 13] and "USGS" not in abroad["credit"]
