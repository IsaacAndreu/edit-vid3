"""Buscador de casos de la NTSB: lectura de la página de un expediente (sin red: HTML de ejemplo)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("buscar_casos", ROOT / "scripts" / "accidentes" / "buscar_casos.py")
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)

PAGE = """<div>Project Summary: Aviation Investigation - 2 Docket Items - DCA09MA026</div>
<div>Description: USAirways flight 1549 ditched in Hudson River</div><div>Mode: Aviation</div>
<div>NTSB Number: DCA09MA026</div><div>Date of Accident: 01/15/2009</div>
<a href="/Docket/Document/docBLOB?ID=1&amp;FileExtension=zip&amp;FileName=Flight%20Data%20Recorder%2010B%20-%20Attachment%201%20-%20Tabular%20Data-Master">x</a>
<a href="/Docket/Document/docBLOB?ID=2&amp;FileExtension=.PDF&amp;FileName=Flight%20Data%20Recorder%2010A%20-%20Factual%20Report%20of%20Group%20Chairman-Master.PDF">y</a>"""


def test_docket_reads_description_date_and_fdr_table(monkeypatch):
    monkeypatch.setattr(bc, "fetch", lambda url, timeout=60: PAGE)
    row = bc.docket("DCA09MA026")
    assert row["date"] == "01/15/2009" and "Hudson" in row["description"]
    assert len(row["fdrTable"]) == 1 and "Tabular" in row["fdrTable"][0]["name"]


def test_missing_docket(monkeypatch):
    monkeypatch.setattr(bc, "fetch", lambda url, timeout=60: "<html>nothing</html>")
    assert bc.docket("DCA99MA999") is None
