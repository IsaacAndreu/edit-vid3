"""Tabla de datos de un FDR (anexo tabular de un informe de la NTSB) → public/accidentes/<caso>/vuelo.json.

    python3 scripts/accidentes/vuelo.py <tabla.csv> scripts/accidentes/casos/<caso>.json

El caso (JSON) dice de dónde salen los datos (documento, URL, licencia), el tramo de tiempo, la corrección de
altitud con su fuente y los hechos del informe (hora, cita literal, página). Nada se inventa aquí: las posiciones
llegan del FDR (cada 4 s; entre dos se interpola en línea recta y se dice) y todo lo demás del informe.
Al final valida el resultado (`check`): tiempos crecientes, sin saltos imposibles, cada hecho con su fuente.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# columnas del FDR → claves de vuelo.json (A320 de la NTSB; otro avión puede traer otros nombres: se añaden aquí)
COLUMNS = {
    "lat": "Latitude", "lon": "Longitude", "palt": "Altitude Press", "ra": "Altitude Radio 1", "kias": "Airspeed Ind",
    "gs": "Ground Speed", "hdg": "Heading", "pitch": "Pitch", "roll": "Roll", "n1l": "Eng1 N1 Act", "n1r": "Eng2 N1 Act",
    "flap": "Flap Pos", "wow": "Gear WOW-N", "gearDown": "Gear Down Locked", "gearUp": "Gear Up Locked",
}


def clock_to_s(clock: str) -> float:
    h, m, *rest = clock.split(":")
    return int(h) * 3600 + int(m) * 60 + (float(rest[0]) if rest else 0.0)


def s_to_clock(s: float) -> str:
    s = round(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def dms(value: str) -> float | None:
    """N40:46:13 → 40.7703; W73:51:46 → -73.8628."""

    value = value.strip()
    if not value or value[0] not in "NSEW":
        return None
    d, m, s = (float(x) for x in value[1:].split(":"))
    out = d + m / 60 + s / 3600
    return -out if value[0] in "SW" else out


def number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def read_fdr(path: Path) -> dict[str, list[tuple[float, Any]]]:
    """Cada parámetro como su propia serie (t, valor): el FDR los graba a ritmos distintos."""

    with path.open(newline="", encoding="latin-1") as f:
        rows = list(csv.reader(f))
    start = next(i for i, r in enumerate(rows) if r and r[0].strip() == "EST")
    header = [h.strip() for h in rows[start]]
    idx = {key: header.index(col) for key, col in COLUMNS.items() if col in header}
    series: dict[str, list[tuple[float, Any]]] = {k: [] for k in COLUMNS}      # vacía si el FDR no la tiene
    for row in rows[start + 2:]:
        t = number(row[0]) if row else None
        if t is None:
            continue
        for key, i in idx.items():
            if i >= len(row) or not row[i].strip() or row[i].strip() == "NUMBER":
                continue
            raw = row[i].strip()
            v: Any = (dms(raw) if key in ("lat", "lon") else raw == "Grnd" if key == "wow"
                      else raw.startswith(("Dn", "Up")) if key in ("gearDown", "gearUp") else number(raw))
            if key == "kias" and v is not None and v >= 511:
                v = None            # 511,875 = el máximo del código: por debajo de ~30 kt el anemómetro no da lectura
            if v is not None:
                series[key].append((t, v))
    # una muestra suelta de 16380 ft al cruzar el cero en la altitud de presión: es −4 en complemento a dos de
    # 14 bits (las vecinas van 8 → ? → −4 → −16); se corrige solo si las dos vecinas están cerca de cero
    p = series["palt"]
    for i in range(1, len(p) - 1):
        if p[i][1] > 15000 and abs(p[i - 1][1]) < 500 and abs(p[i + 1][1]) < 500:
            p[i] = (p[i][0], p[i][1] - 16384)
    return series


def at(points: list[tuple[float, Any]], t: float, kind: str = "linear") -> Any:
    """Valor de una serie en t: interpolado (linear), el último anterior (step) o el más cercano en ±1 s (near)."""

    if not points or t < points[0][0] - 1 or t > points[-1][0] + 1:
        return None
    lo, hi = 0, len(points) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if points[mid][0] <= t:
            lo = mid
        else:
            hi = mid - 1
    a = points[lo]
    b = points[min(lo + 1, len(points) - 1)]
    if kind == "step" or a is b or isinstance(a[1], bool):
        return a[1]
    if kind == "near":
        best = min((a, b), key=lambda p: abs(p[0] - t))
        return best[1] if abs(best[0] - t) <= 1.0 else None
    if b[0] == a[0]:
        return a[1]
    f = max(0.0, min(1.0, (t - a[0]) / (b[0] - a[0])))
    return a[1] + (b[1] - a[1]) * f


def heading_at(points: list[tuple[float, Any]], t: float) -> float | None:
    """Rumbo interpolado por el camino corto (359 → 1 pasa por 0, no por 180)."""

    a = at(points, t, "step")
    if a is None:
        return None
    later = [p for p in points if p[0] > t][:1]
    before = [p for p in points if p[0] <= t][-1:]
    if not later or not before:
        return round(a % 360, 1)
    (t0, h0), (t1, h1) = before[0], later[0]
    d = (h1 - h0 + 540) % 360 - 180
    return round((h0 + d * (t - t0) / (t1 - t0)) % 360, 1)


def build(series: dict[str, list[tuple[float, Any]]], case: dict[str, Any]) -> dict[str, Any]:
    t0, t1 = clock_to_s(case["from"]), clock_to_s(case["to"])
    offset = float(case["altitude"]["offsetFt"])
    last = min(t1, series["palt"][-1][0])
    tb = min(series["lat"][-1][0], series["lon"][-1][0])          # la última posición completa
    la_a, lo_a = at(series["lat"], tb - 4), at(series["lon"], tb - 4)
    la_b, lo_b = at(series["lat"], tb), at(series["lon"], tb)

    def position(t: float) -> tuple[float | None, float | None]:
        if t <= tb:
            return at(series["lat"], t), at(series["lon"], t)
        # después de la última posición grabada: sigue la dirección de las dos últimas posiciones a la velocidad
        # sobre el suelo del FDR (se dice en las notas)
        gs = at(series["gs"], t) or 0
        dist_nm = gs * (t - tb) / 3600
        north, east = la_b - la_a, (lo_b - lo_a) * math.cos(math.radians(la_b))
        norm = math.hypot(north, east) or 1
        return la_b + north / norm * dist_nm / 60, lo_b + east / norm * dist_nm / 60 / math.cos(math.radians(la_b))

    pts = []
    t = t0
    while t <= last + 1e-6:
        lat, lon = position(t)
        palt = at(series["palt"], t)
        if lat is None or lon is None or palt is None:
            t += 1
            continue
        ra = at(series["ra"], t, "near")
        n1l, n1r = at(series["n1l"], t), at(series["n1r"], t)
        p: dict[str, Any] = {
            "s": round(t, 2), "lat": round(lat, 5), "lon": round(lon, 5), "alt": round(palt + offset),
            "kias": None if at(series["kias"], t) is None else round(at(series["kias"], t), 1), "gs": round(at(series["gs"], t) or 0),
            "hdg": heading_at(series["hdg"], t), "pitch": round(at(series["pitch"], t) or 0, 1),
            "roll": round(at(series["roll"], t) or 0, 1),
            "n1": [round(n1l, 1) if n1l is not None else None, round(n1r, 1) if n1r is not None else None],
            "ground": bool(at(series["wow"], t, "step")),
        }
        if ra is not None and -20 < ra < 2600:
            p["ra"] = round(ra)
        flap = at(series["flap"], t)
        if flap is not None:
            p["flap"] = round(flap, 1)
        down, up = at(series["gearDown"], t, "step"), at(series["gearUp"], t, "step")
        if down is not None or up is not None:
            p["gear"] = 1.0 if down else 0.0 if up else 0.5          # bajado y blocado, recogido, o en tránsito
        pts.append(p)
        t += 1
    return {
        "id": case["id"], "flight": case["flight"], "aircraft": case["aircraft"], "registration": case.get("registration"),
        "date": case["date"], "timezone": case["timezone"], "source": case["source"], "altitude": case["altitude"],
        "notes": case.get("notes", []), "from": s_to_clock(pts[0]["s"]), "to": s_to_clock(pts[-1]["s"]),
        "points": pts,
        "events": [{**e, "s": clock_to_s(e["clock"])} for e in case.get("events", [])],
        "facts": case.get("facts", []),
    }


def check(v: dict[str, Any]) -> list[str]:
    """Lo que no puede pasar en unos datos de vuelo bien leídos."""

    errors: list[str] = []
    pts = v["points"]
    if len(pts) < 10:
        errors.append(f"solo {len(pts)} puntos")
    for a, b in zip(pts, pts[1:]):
        dt = b["s"] - a["s"]
        if dt <= 0:
            errors.append(f"tiempo no creciente en {s_to_clock(b['s'])}")
        if abs(b["alt"] - a["alt"]) / max(dt, 1e-6) > 2000 / 60 * 3:     # más de 6.000 ft/min sostenido entre dos
            errors.append(f"salto de altitud {a['alt']}→{b['alt']} ft en {s_to_clock(b['s'])}")
        km = 6371 * math.radians(math.hypot(b["lat"] - a["lat"], (b["lon"] - a["lon"]) * math.cos(math.radians(a["lat"]))))
        if km / max(dt, 1e-6) * 3600 > 1500:
            errors.append(f"salto de posición de {km:.1f} km en {s_to_clock(b['s'])}")
        if b["kias"] is not None and not 0 <= b["kias"] <= 600:
            errors.append(f"velocidad imposible {b['kias']} kt en {s_to_clock(b['s'])}")
    for e in v["events"] + v["facts"]:
        if not str(e.get("ref") or "").strip():
            errors.append(f"sin fuente: {e.get('text') or e.get('label')}")
    for e in v["events"]:
        if not pts[0]["s"] - 600 <= e["s"] <= pts[-1]["s"] + 600:
            errors.append(f"hecho fuera del tramo: {e['clock']}")
    if not str(v["source"].get("document") or "").strip():
        errors.append("falta el documento de origen")
    return errors


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    case = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    out = build(read_fdr(Path(sys.argv[1])), case)
    errors = check(out)
    if errors:
        sys.exit("vuelo.json no válido:\n  " + "\n  ".join(errors[:20]))
    dest = ROOT / "public" / "accidentes" / case["id"] / "vuelo.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{dest.relative_to(ROOT)}: {len(out['points'])} puntos ({out['from']}–{out['to']}), {len(out['events'])} hechos")


if __name__ == "__main__":
    main()
