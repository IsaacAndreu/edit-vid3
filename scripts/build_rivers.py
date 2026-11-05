"""Build remotion/data/rivers.json: Natural Earth's rivers and lake centre lines at 1:10m (public domain) for the
atlas's close maps (pipeline/atlas.py zoom 4.4+): a FeatureCollection of MultiLineStrings with "r" (Natural Earth's
scalerank 0-10: the bigger the river, the lower) and the river's name, coordinates rounded to 0.05° (≈ 5 km, about
than a close map shows) without repeated points.

    curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_rivers_lake_centerlines.geojson
    python3 scripts/build_rivers.py ne_10m_rivers_lake_centerlines.geojson
"""

import json
import sys
from pathlib import Path

STEP = 0.05
MAX_RANK = 8          # 9-10 are the smallest streams: noise even on a close map


def _line(coords: list) -> list:
    out: list = []
    for lon, lat, *_ in coords:
        point = [round(round(lon / STEP) * STEP, 2), round(round(lat / STEP) * STEP, 2)]
        if not out or out[-1] != point:
            out.append(point)
    return out if len(out) > 1 else []


def main(source: str) -> None:
    data = json.loads(Path(source).read_text("utf-8"))
    merged: dict[tuple, list] = {}
    for feature in data["features"]:
        props, geometry = feature["properties"], feature.get("geometry") or {}
        rank = int(props.get("scalerank") or 0)
        if rank > MAX_RANK or not geometry:
            continue
        parts = geometry["coordinates"] if geometry["type"] == "MultiLineString" else [geometry["coordinates"]]
        name = str(props.get("name") or "")
        merged.setdefault((rank, name), []).extend(line for line in (_line(p) for p in parts) if line)
    features = [{"type": "Feature", "properties": {"r": rank, "name": name},
                 "geometry": {"type": "MultiLineString", "coordinates": lines}}
                for (rank, name), lines in sorted(merged.items()) if lines]
    out = Path(__file__).resolve().parent.parent / "remotion" / "data" / "rivers.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), "utf-8")
    print(f"{out}: {len(features)} ríos · {out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1])
