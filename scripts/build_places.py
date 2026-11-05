"""Build assets/geo/places.json: the names the atlas recognises in a script by itself (pipeline/atlas.py
auto_places) — every country in Natural Earth with its name in es/pt/en/de/fr/it (key: the name the globe's map data
uses) and the biggest cities with their population. Natural Earth is public domain.

    curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson
    curl -LO https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places_simple.zip && unzip … -d pp
    python3 scripts/build_places.py ne_50m_admin_0_countries.geojson pp
"""

import json
import sys
from pathlib import Path

import shapefile

CITIES = 2500
LANGS = ("NAME", "NAME_LONG", "NAME_EN", "NAME_ES", "NAME_PT", "NAME_DE", "NAME_FR", "NAME_IT")


def main(countries_file: str, places_folder: str) -> None:
    countries = {}
    for feature in json.loads(Path(countries_file).read_text("utf-8"))["features"]:
        p = feature["properties"]
        names = sorted({str(p[k]).strip() for k in LANGS if p.get(k) and str(p[k]).strip()}, key=len)
        countries[p["NAME"]] = {"names": names, "lat": round(float(p["LABEL_Y"]), 2), "lon": round(float(p["LABEL_X"]), 2)}
    reader = shapefile.Reader(str(next(Path(places_folder).rglob("ne_10m_populated_places_simple.shp"))))
    fields = [f[0] for f in reader.fields[1:]]
    rows = []
    for record in reader.records():
        row = dict(zip(fields, record))
        rows.append((int(row.get("pop_max") or 0), str(row["name"]).strip(), round(float(row["latitude"]), 3),
                     round(float(row["longitude"]), 3), int(row.get("adm0cap") or 0)))
    rows.sort(reverse=True)
    chosen = rows[:CITIES] + [r for r in rows[CITIES:] if r[4]]          # every capital too
    seen: set[str] = set()
    cities = []
    for pop, name, lat, lon, _ in chosen:
        if name and name not in seen:
            seen.add(name)
            cities.append([name, lat, lon, pop])
    out = Path(__file__).resolve().parent.parent / "assets" / "geo" / "places.json"
    out.write_text(json.dumps({"countries": countries, "cities": cities}, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"{out}: {len(countries)} países · {len(cities)} ciudades · {out.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
