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
from shapely.geometry import box, mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

LEVELS = {"K_200": 200, "I_2000": 2000, "G_4000": 4000, "E_6000": 6000}
TOLERANCE = 0.18          # degrees: plenty for a globe that fills ~800 px
MIN_AREA = 0.8            # square degrees: no specks
HOLE_MIN = 3.0            # square degrees: smaller holes in a level (seamounts) are filled
TILE = 30                 # degrees: the size of the pieces each level is cut into


def rounded(geometry, digits=2):
    def walk(value):
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], (int, float)):
            # a vertex exactly on the antimeridian: d3-geo cuts there itself, and two pieces meeting on ±180 made it
            # lose track of which side is inside as the globe turned (the band flickered): a hair off it
            lon = max(-179.98, min(179.98, value[0]))
            return [round(lon, digits), round(value[1], digits)]
        return [walk(v) for v in value]
    return {"type": geometry["type"], "coordinates": walk(geometry["coordinates"])}


def main(folder: str) -> None:
    features = []
    for name, depth in LEVELS.items():
        path = next(Path(folder).rglob(f"ne_10m_bathymetry_{name}.shp"))
        polys = [shape(s.__geo_interface__) for s in shapefile.Reader(str(path)).shapes()]
        # no ring on a pole: Natural Earth closes the Southern Ocean along lat -90, and d3-geo cannot tell inside from
        # outside on an edge through the pole — the band flickered on and off as the globe turned (only ice is there)
        merged = unary_union([p.buffer(0) for p in polys]).intersection(box(-180, -84, 180, 89)).simplify(TOLERANCE, preserve_topology=True)
        parts = [g for g in getattr(merged, "geoms", [merged]) if g.area >= MIN_AREA]
        geometry = unary_union(parts)
        # cut into 30° x 30° tiles: a polygon that wraps most of the globe (all the sea deeper than 200 m) or rings the
        # pole made d3-geo's clipping lose track of which side is inside as the globe turned — the band around
        # Antarctica flickered on and off. Small pieces are always unambiguous; the component strokes them in their
        # own colour so the seams never show. d3-geo wants each ring clockwise on the sphere.
        pieces = []
        # tile edges off the round meridians (0, ±90…), where a globe looking at a round longitude has its horizon
        for lon in [-180 + 7.3 + TILE * k for k in range(-1, 360 // TILE + 1)]:
            for lat in range(-84, 89, TILE):
                cut = geometry.intersection(box(max(lon, -180), lat, min(lon + TILE, 180), min(lat + TILE, 89)))
                for g in getattr(cut, "geoms", [cut]):
                    if g.geom_type == "Polygon" and g.area > 0.05:
                        # no small holes (seamounts): a piece behind the globe with many of them was taken for the
                        # whole visible side now and then
                        from shapely.geometry import Polygon

                        g = Polygon(g.exterior, [r for r in g.interiors if Polygon(r).area >= HOLE_MIN])
                        pieces.append(orient(g, -1.0))
        from shapely.geometry import MultiPolygon

        geometry = MultiPolygon(pieces)
        features.append({"type": "Feature", "properties": {"depth": depth}, "geometry": rounded(mapping(geometry))})
        print(name, len(parts), "partes")
    out = Path(__file__).resolve().parents[1] / "remotion" / "data" / "bathymetry.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ne")
