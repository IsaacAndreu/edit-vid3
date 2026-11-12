"""Buscador de casos: qué investigaciones de la NTSB tienen publicada la tabla de datos del FDR (lo que necesitan las
reconstrucciones), con su fecha y su descripción, sacado de cada expediente público (data.ntsb.gov/Docket).

    python3 scripts/accidentes/buscar_casos.py DCA09MA026 DCA16MA069 …        expedientes concretos
    python3 scripts/accidentes/buscar_casos.py --escanear 2010 2024             las investigaciones mayores (DCAaaMAnnn)
                                                                                 de esos años, una a una
    python3 scripts/accidentes/buscar_casos.py --preparar DCA09MA026 us1549     descarga la tabla del FDR y escribe el
                                                                                 esqueleto de scripts/accidentes/casos/us1549.json

Resultado en out/_accidentes/casos.json y casos.md (los que tienen tabla del FDR primero). Nada se inventa: cada fila
sale de la página del expediente; un número que no existe simplemente no aparece. El escaneo pide una página por
número (1 por segundo) y recorre del 1 al 300 de cada año (van salteados): ~5 min por año.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKET = "https://data.ntsb.gov/Docket/?NTSBNumber={n}"
BASE = "https://data.ntsb.gov"
OUT = ROOT / "out" / "_accidentes"


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research script)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _text(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def docket(number: str) -> dict | None:
    """La ficha de un expediente: descripción, fecha, nº de documentos y los enlaces útiles (tabla del FDR, CVR…)."""

    page = fetch(DOCKET.format(n=number))
    plain = _text(page)
    if "NTSB Number:" not in plain:
        return None
    m_desc = re.search(r"Description:\s*(.+?)\s+Mode:", plain)
    m_date = re.search(r"Date of Accident:\s*([0-9/]+)", plain)
    m_items = re.search(r"(\d+) Docket Items", plain)
    links = []
    for href in re.findall(r'href="(/Docket/Document/docBLOB\?[^"]+)"', page):
        url = BASE + html.unescape(href)
        fname = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("FileName", [""])[0]
        links.append({"name": fname, "url": url})
    fdr = [l for l in links if re.search(r"flight data recorder", l["name"], re.I) and re.search(r"tabular|electronic|data", l["name"], re.I)
           and not re.search(r"factual report", l["name"], re.I)]
    cvr = [l for l in links if re.search(r"cockpit voice recorder|cvr", l["name"], re.I)]
    return {"number": number, "date": m_date.group(1) if m_date else None, "description": m_desc.group(1) if m_desc else "",
            "items": int(m_items.group(1)) if m_items else len(links), "fdrTable": fdr, "cvr": cvr[:3]}


def save(rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (not r["fdrTable"], r.get("date") or ""))
    (OUT / "casos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# Casos de la NTSB", "", "| Expediente | Fecha | Tabla del FDR | CVR | Descripción |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['number']} | {r.get('date') or '—'} | {'sí' if r['fdrTable'] else 'no'} | {'sí' if r['cvr'] else 'no'} | "
                     f"{(r.get('description') or '')[:140].replace('|', '/')} |")
    (OUT / "casos.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUT / 'casos.md'}: {len(rows)} expedientes, {sum(1 for r in rows if r['fdrTable'])} con tabla del FDR")


def scan(first: int, last: int) -> list[dict]:
    rows = []
    for year in range(first, last + 1):
        empty = 0
        for n in range(1, 301):
            number = f"DCA{year % 100:02d}MA{n:03d}"
            try:
                row = docket(number)
            except Exception as error:
                print(f"{number}: {error}")
                row = None
            time.sleep(1)
            if row is None:               # los números van salteados (MA142 en 2018): se recorren todos
                empty += 1
                continue
            empty = 0
            rows.append(row)
            print(f"{number} {row['date']}: {'FDR ' if row['fdrTable'] else ''}{row['description'][:90]}")
    return rows


def prepare(number: str, case: str) -> None:
    """La tabla del FDR a .cache/accidentes/<caso>/ y el esqueleto del caso, con la fuente ya rellena."""

    row = docket(number)
    if not row or not row["fdrTable"]:
        sys.exit(f"{number}: no hay tabla del FDR en el expediente")
    table = row["fdrTable"][0]
    target = ROOT / "scripts" / "accidentes" / "casos" / f"{case}.json"
    if target.exists():
        sys.exit(f"Ya existe {target.relative_to(ROOT)}")
    skeleton = {
        "id": case, "flight": "COMPLETAR (del informe)", "aircraft": "COMPLETAR", "registration": "COMPLETAR",
        "date": "COMPLETAR (AAAA-MM-DD)", "timezone": "COMPLETAR (la de las horas de la tabla)",
        "from": "COMPLETAR hh:mm:ss", "to": "COMPLETAR hh:mm:ss",
        "source": {"document": f"NTSB {number} — {table['name']}", "url": DOCKET.format(n=number), "table": table["url"],
                   "report": "COMPLETAR (informe final)", "reportUrl": "COMPLETAR", "license": "Obra del Gobierno de EE. UU. (dominio público)"},
        "altitude": {"offsetFt": 0, "method": "COMPLETAR: corrección de la altitud de presión con el altímetro del informe", "ref": "COMPLETAR"},
        "notes": [],
        "events": [{"clock": "hh:mm:ss", "kind": "cvr|atc|event", "who": "", "text": "cita literal del informe", "ref": "página"}],
        "facts": [{"label": "", "value": 0, "text": "", "ref": "página"}],
        "description": row["description"],
    }
    target.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{target.relative_to(ROOT)}: esqueleto escrito. Tabla del FDR: {table['url']}\n"
          f"En escenas.json: {{\"kind\": \"flight\", \"case\": \"{case}\", \"table\": \"{table['url']}\"}}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "--preparar" and len(args) == 3:
        prepare(args[1], args[2])
        return
    if args[0] == "--escanear" and len(args) == 3:
        save(scan(int(args[1]), int(args[2])))
        return
    rows = [r for r in (docket(n) for n in args) if r]
    save(rows)


if __name__ == "__main__":
    main()
