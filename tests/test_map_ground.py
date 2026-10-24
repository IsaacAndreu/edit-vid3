"""Satellite ground under the flat maps (pipeline/satellite.ground): tile-aligned mosaics with their lon/lat edges."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from pipeline import satellite
from pipeline.context import RunContext

ROOT = Path(__file__).resolve().parents[1]


def test_country_boxes_come_from_the_maps_own_atlas():
    boxes = satellite.country_boxes(ROOT)
    west, south, east, north = boxes["spain"]
    assert -10 < west < -9 and 35 < south < 37 and 3 < east < 4 and 43 < north < 44      # no Canaries


def test_a_map_gets_a_wide_layer_and_a_close_one_where_it_zooms(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "node_modules").symlink_to(ROOT / "node_modules")
    ctx = RunContext.create("m", root=tmp_path)
    asked = []

    def tile(ctx_, source, z, x, y, session):
        asked.append(z)
        buffer = io.BytesIO()
        Image.new("RGB", (256, 256), (40, 90, 40)).save(buffer, "JPEG")
        return buffer.getvalue()

    monkeypatch.setattr(satellite, "_tile", tile)
    graphic = {"type": "map", "countries": ["Germany"], "points": [{"name": "Berlín", "lon": 13.4, "lat": 52.52}], "zoom": 0}
    layers = satellite.ground(ctx, graphic)
    assert len(layers) == 2 and layers[1]["zoom"] > layers[0]["zoom"]
    wide = layers[0]
    assert wide["west"] < 5 and wide["east"] > 16 and wide["south"] < 47 and wide["north"] > 55     # Germany and margins
    image = Image.open(ctx.work_dir / wide["media"]["src"])
    assert image.width % 256 == 0 and image.height % 256 == 0 and len(asked) <= 150 + 120
    assert satellite.ground(ctx, {**graphic, "globe": True}) == [] and satellite.ground(ctx, {**graphic, "style": "pins"}) == []
