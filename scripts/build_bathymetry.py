"""Build remotion/data/bathymetry.json: Natural Earth's 1:10m bathymetry (public domain), a few depth levels,
simplified for a whole-globe view (the atlas format's ocean: deeper water, darker blue).

    python3 -m pip install pyshp shapely
    curl -LO https://naciscdn.org/naturalearth/10m/physical/ne_10m_bathymetry_all.zip && unzip ne_10m_bathymetry_all.zip -d ne
    python3 scripts/build_bathymetry.py ne

Run once; the output is committed. Each feature: {"depth": metres, geometry: (Multi)Polygon of the sea deeper than that}.
"""

import json
import sys
from pathlib import Path

import shapefile
from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

LEVELS = {"K_200": 200, "I_2000": 2000, "G_4000": 4000, "E_6000": 6000}
TOLERANCE = 0.18          # degrees: plenty for a globe that fills ~800 px
MIN_AREA = 0.8            # square degrees: no specks


def rounded(geometry, digits=2):
    def walk(value):
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], (int, float)):
            return [round(value[0], digits), round(value[1], digits)]
        return [walk(v) for v in value]
    return {"type": geometry["type"], "coordinates": walk(geometry["coordinates"])}


def main(folder: str) -> None:
    features = []
    for name, depth in LEVELS.items():
        path = next(Path(folder).rglob(f"ne_10m_bathymetry_{name}.shp"))
        polys = [shape(s.__geo_interface__) for s in shapefile.Reader(str(path)).shapes()]
        merged = unary_union([p.buffer(0) for p in polys]).simplify(TOLERANCE, preserve_topology=True)
        parts = [g for g in getattr(merged, "geoms", [merged]) if g.area >= MIN_AREA]
        # d3-geo wants each ring clockwise on the sphere (GeoJSON's counter-clockwise would fill the rest of the world)
        geometry = unary_union(parts)
        geometry = type(geometry)([orient(g, -1.0) for g in geometry.geoms]) if hasattr(geometry, 'geoms') else orient(geometry, -1.0)
        features.append({"type": "Feature", "properties": {"depth": depth}, "geometry": rounded(mapping(geometry))})
        print(name, len(parts), "partes")
    out = Path(__file__).resolve().parents[1] / "remotion" / "data" / "bathymetry.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ne")
