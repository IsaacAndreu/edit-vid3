"""Build remotion/data/cities.json: Natural Earth's populated places (public domain) for the atlas's city lights on the
night side — [lon, lat, size 1-4] for the ~3,000 biggest places (size from the population).

    python3 -m pip install pyshp
    curl -LO https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places_simple.zip && unzip … -d pp
    python3 scripts/build_cities.py pp
"""

import json
import math
import sys
from pathlib import Path

import shapefile

KEEP = 3000


def main(folder: str) -> None:
    path = next(Path(folder).rglob("ne_10m_populated_places_simple.shp"))
    reader = shapefile.Reader(str(path))
    names = [f[0] for f in reader.fields[1:]]
    rows = []
    for record in reader.records():
        row = dict(zip(names, record))
        pop = max(int(row.get("pop_max") or 0), 1)
        rows.append((pop, round(float(row["longitude"]), 2), round(float(row["latitude"]), 2)))
    rows.sort(reverse=True)
    out = []
    for pop, lon, lat in rows[:KEEP]:
        size = 4 if pop > 5e6 else 3 if pop > 1e6 else 2 if pop > 2e5 else 1
        out.append([lon, lat, size])
    target = Path(__file__).resolve().parents[1] / "remotion" / "data" / "cities.json"
    target.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(target, len(out), f"{target.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pp")
