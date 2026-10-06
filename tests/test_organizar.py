"""«Para subir» and «Guiones» (pipeline/organizar.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import organizar
from test_agenda import _site, _video

YOUTUBE = """TÍTULO (elige uno)
1. La multa más grande
2. Booking contra la CNMC
3. 413 millones

DESCRIPCIÓN
Una historia de hoteles.

0:00 Intro
3:11 La cláusula

ETIQUETAS
booking, cnmc

COMENTARIO FIJADO (publícalo tú y fíjalo)
¿Reservas directo?

POST DE COMUNIDAD (el día de la publicación)
¡Nuevo vídeo!

SUBTÍTULOS: sube subtitulos.es.srt en YouTube Studio → Subtítulos
"""


def test_youtube_txt_in_sections():
    s = organizar.youtube_sections(YOUTUBE)
    assert s["DESCRIPCIÓN"].startswith("Una historia") and "3:11 La cláusula" in s["DESCRIPCIÓN"]
    assert s["ETIQUETAS"] == "booking, cnmc" and s["COMENTARIO FIJADO"] == "¿Reservas directo?"
    assert s["SUBTÍTULOS"].startswith("sube subtitulos")


def test_done_videos_come_with_titles_texts_and_files(tmp_path: Path):
    root = _site(tmp_path)
    _video(root, "negocios", "n1", done=True)
    _video(root, "negocios", "n2", published="2026-10-01")
    out = root / "out" / "n1"
    (out / "youtube.txt").write_text(YOUTUBE, encoding="utf-8")
    (out / "miniaturas").mkdir()
    (out / "miniaturas" / "miniatura-1.jpg").write_bytes(b"jpg")
    (out / "subtitulos.es.srt").write_text("1\n", encoding="utf-8")
    videos = organizar.to_upload(root)
    assert [v["slug"] for v in videos] == ["n1"]                         # the uploaded one is not there
    v = videos[0]
    assert v["titles"] == ["La multa más grande", "Booking contra la CNMC", "413 millones"]
    assert {f["path"] for f in v["files"]} == {"video-final.mp4", "miniaturas/miniatura-1.jpg", "subtitulos.es.srt"}
    assert v["date"]                                                      # its day in the calendar


def test_the_scripts_each_channel_still_needs(tmp_path: Path):
    root = _site(tmp_path)
    _video(root, "gimnasia", "g1", done=True)
    from pipeline import agenda

    agenda.add_idea(root, "La caída de Biles", channel="gimnasia")
    needed = {c["channel"]: c for c in organizar.scripts_needed(root, 14)}
    gim, neg = needed["gimnasia"], needed["negocios"]
    assert neg["missing"] == neg["slots"] and gim["missing"] == gim["slots"] - 1
    assert gim["ideas"][0]["title"] == "La caída de Biles" and gim["ready"] == 1
    assert "Te faltan" in organizar.scripts_text(root)


def test_a_draft_uses_the_channels_style_and_length(tmp_path: Path, monkeypatch):
    root = _site(tmp_path)
    _video(root, "negocios", "n1")
    (root / "materiales" / "negocios" / "n1" / "guion.txt").write_text("Estilo del canal. " * 300, encoding="utf-8")
    seen = {}

    def fake(ctx, **kwargs):
        seen.update(kwargs)
        return {"title": "Booking", "script": "## UNO\n" + "Frase del guion. " * 250 + "Dato [COMPROBAR]."}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    d = organizar.draft_script(root, "negocios", {"title": "Booking y la CNMC", "note": "la multa"})
    assert "Estilo del canal" in seen["user"] and "unas 900 palabras" in seen["user"] and "NOTA: la multa" in seen["user"]
    assert d["check"] == 1 and d["script"].startswith("## UNO")
    with pytest.raises(ValueError):
        organizar.draft_script(root, "negocios", {"title": ""})


def test_finished_videos_get_stills_for_your_thumbnail(tmp_path: Path):
    import subprocess

    root = _site(tmp_path)
    _video(root, "negocios", "n1", done=True)
    final = root / "out" / "n1" / "video-final.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=4",
                    str(final)], check=True)
    v = organizar.to_upload(root)[0]
    stills = [f for f in v["files"] if f.get("still")]
    assert len(stills) == 8 and stills[0]["path"] == "fotogramas/fotograma-1.jpg"


def test_a_real_case_draft_follows_its_structure(tmp_path: Path, monkeypatch):
    import shutil

    root = _site(tmp_path)
    (root / "formatos").mkdir()
    for name in ("caso-real", "historia"):
        shutil.copy(Path(__file__).parents[1] / "formatos" / f"{name}.yaml", root / "formatos" / f"{name}.yaml")
    seen = {}

    def fake(ctx, **kwargs):
        seen.update(kwargs)
        return {"title": "Christa Pike", "script": "Miércoles 30 de septiembre. " * 100}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    d = organizar.draft_script(root, "negocios", {"title": "Christa Pike", "format": "caso-real"})
    assert "ESTRUCTURA OBLIGATORIA DEL FORMATO «caso-real»" in seen["user"] and "EL CLÍMAX" in seen["user"]
    assert d["format"] == "caso-real"
