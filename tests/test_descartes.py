"""«Contenido sin topes fijos»: diagnostico.md says why material was left out and how many shots it cost."""

from __future__ import annotations

import json

from pipeline import descartes


def test_the_discarded_material_table(tmp_path):
    work, out, cache = tmp_path / "work" / "v", tmp_path / "out" / "v", tmp_path / "cache"
    (work / "candidates").mkdir(parents=True)
    (work / "scores").mkdir(parents=True)
    out.mkdir(parents=True)
    (cache / "videos").mkdir(parents=True)
    (cache / "videos" / ".rechazados.json").write_text(json.dumps({"aaaaaaaaaaa": {"at": 1, "why": "sin-hls"}}))
    (work / "candidates" / "s1.json").write_text(json.dumps({
        "shotId": "s1", "candidates": [{"id": "yt:aaaaaaaaaaa"}],
        "notes": ["yt:bbbbbbbbbbb: sin HLS y dura 40 min (> 10 min); descartado para el proxy residencial",
                  "plano difícil, se deja de buscar: 6 vídeos mirados, 1 válidos"]}))
    (work / "scores" / "s1.json").write_text(json.dumps({"options": [
        {"discarded": "texto en pantalla (35%)"}, {"discarded": None}]}))
    (out / "manifest.json").write_text(json.dumps({"shots": [{"shotId": "s1", "kind": "image"}]}))
    table = descartes.collect(work, out, cache)
    hls = "proxy: sin HLS y supera el tope (whole_max_*_residential)"
    assert table[hls] == {"candidatos": 2, "planos": 1}
    assert table["análisis: texto en pantalla"]["candidatos"] == 1
    assert table["plano difícil: tope de vídeos mirados (max_details_per_shot)"]["candidatos"] == 1
    assert "## Material descartado" in "\n".join(descartes.lines(table))
