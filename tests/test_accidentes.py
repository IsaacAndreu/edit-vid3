"""Vuelos reales (scripts/accidentes/vuelo.py) y su sitio en --atlas-guion."""

import csv
import importlib.util
import json
from pathlib import Path

from pipeline import atlas_guion

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("vuelo", ROOT / "scripts" / "accidentes" / "vuelo.py")
vuelo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vuelo)

HEADER = ["EST", "Latitude", "Longitude", "Altitude Press", "Altitude Radio 1", "Airspeed Ind", "Ground Speed", "Heading",
          "Pitch", "Roll", "Eng1 N1 Act", "Eng2 N1 Act", "Flap Pos", "Gear WOW-N"]


def _table(tmp_path: Path, rows: list[list[str]]) -> Path:
    path = tmp_path / "fdr.csv"
    with path.open("w", newline="", encoding="latin-1") as f:
        w = csv.writer(f)
        w.writerow(["National Transportation Safety Board"])
        w.writerow(HEADER)
        w.writerow(["(sec)"] + ["()"] * (len(HEADER) - 1))
        w.writerows(rows)
    return path


def _row(t: float, lat: str, lon: str, palt: str, kias: str = "200") -> list[str]:
    return [str(t), lat, lon, palt, "", kias, "190", "10.0", "2.0", "0.0", "80", "80", "0", "Air"]


def _case(**over):
    base = {"id": "prueba", "flight": "X 1", "aircraft": "A320", "date": "2009-01-15", "timezone": "EST",
            "from": "10:00:00", "to": "10:00:20", "source": {"document": "NTSB X, tabla", "url": "u", "license": "l"},
            "altitude": {"offsetFt": 293, "method": "m", "ref": "r"}, "events": [], "facts": []}
    return {**base, **over}


def test_dms_and_clock():
    assert round(vuelo.dms("N40:46:13"), 4) == 40.7703
    assert round(vuelo.dms("W73:51:46"), 4) == -73.8628
    assert vuelo.s_to_clock(vuelo.clock_to_s("15:27:11")) == "15:27:11"


def test_build_interpolates_corrects_altitude_and_fixes_the_zero_crossing(tmp_path):
    t0 = vuelo.clock_to_s("10:00:00")
    rows = []
    for k in range(0, 24):
        lat = f"N40:46:{10 + k // 4:02d}" if k % 4 == 0 else ""
        lon = f"W73:51:{40 + k // 4:02d}" if k % 4 == 0 else ""
        palt = "16380" if k == 10 else str(100 - 10 * k)          # cruza el cero: una muestra de 16380 = −4
        rows.append(_row(t0 + k, lat, lon, palt, "511.875" if k < 4 else "200"))
    out = vuelo.build(vuelo.read_fdr(_table(tmp_path, rows)), _case())
    assert vuelo.check(out) == []
    by_s = {round(p["s"] - t0): p for p in out["points"]}
    assert by_s[10]["alt"] == -4 + 293
    assert by_s[0]["kias"] is None                              # 511,875 = sin lectura
    assert by_s[2]["lat"] > by_s[0]["lat"]                      # interpolada entre posiciones de 4 s


def test_check_catches_jumps_and_missing_sources(tmp_path):
    t0 = vuelo.clock_to_s("10:00:00")
    rows = [_row(t0 + k, f"N40:46:{10 + k:02d}", f"W73:51:{40 + k:02d}", "9000" if k == 8 else "1000") for k in range(16)]
    out = vuelo.build(vuelo.read_fdr(_table(tmp_path, rows)), _case(events=[{"clock": "10:00:05", "text": "x", "ref": ""}]))
    errors = vuelo.check(out)
    assert any("salto de altitud" in e for e in errors)
    assert any("sin fuente" in e for e in errors)


def test_atlas_guion_knows_flight_data():
    spec = {"kind": "flight", "case": "us1549", "table": "https://example.org/fdr.zip"}
    assert atlas_guion.data_output(spec).as_posix().endswith("public/accidentes/us1549/vuelo.json")
    assert atlas_guion.data_commands({"kind": "flight-ground", "case": "us1549"}, "x") == [
        ["atlas:data", "--", "flight-ground", "public/accidentes/us1549/vuelo.json"]]
    cmd = atlas_guion.data_commands({"kind": "terrain", "id": "t", "bbox": [0, 0, 1, 1], "region": "nueva-york"}, "x")[0]
    assert cmd[-1] == "nueva-york"


def test_reference_case_is_valid_and_sourced():
    case = json.loads((ROOT / "scripts" / "accidentes" / "casos" / "us1549.json").read_text(encoding="utf-8"))
    assert all(e["ref"] for e in case["events"] + case["facts"])
    data = json.loads((ROOT / "public" / "accidentes" / "us1549" / "vuelo.json").read_text(encoding="utf-8"))
    assert vuelo.check(data) == []
    assert all("terrain" in p for p in data["points"])
