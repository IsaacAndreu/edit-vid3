"""Automatic dubbing (pipeline/doblaje.py): off by default; when on, translated script + voice for the queue."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import doblaje, dub, tts


def _done_video(tmp_path: Path, channel_yaml: str) -> Path:
    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "negocios.yaml").write_text(channel_yaml, encoding="utf-8")
    folder = tmp_path / "materiales" / "negocios" / "n1"
    folder.mkdir(parents=True)
    (folder.parent / "config.yaml").write_text("canal: negocios\n", encoding="utf-8")
    (folder / "guion.txt").write_text("## EL INICIO\n" + "La multa de Booking. " * 40, encoding="utf-8")
    (folder / "titulo.txt").write_text("La multa", encoding="utf-8")
    (folder / "voz.mp3").write_bytes(b"mp3")
    out = tmp_path / "out" / "n1"
    out.mkdir(parents=True)
    (out / "video-final.mp4").write_bytes(b"x")
    return folder


def test_off_by_default(tmp_path, monkeypatch):
    _done_video(tmp_path, "format: historia\n")
    monkeypatch.setattr("pipeline.llm.complete_json", lambda *a, **k: pytest.fail("no translation"))
    assert doblaje.prepare_all(tmp_path, log=lambda *_: None) == 0


def test_on_translates_voices_and_hands_it_to_the_queue(tmp_path, monkeypatch):
    folder = _done_video(tmp_path, "format: historia\ndubbing:\n  enabled: true\n  languages: [en]\n"
                                   "  voices:\n    en: {voice_id: EN1}\n")
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **kw: {
        "title": "The fine", "script": "## THE BEGINNING\n" + "Booking's fine. " * 40})
    spoken = {}

    def fake_generate(token, text, voice, target, session=None, log=print):
        spoken.update(text=text, voice=voice["voice_id"])
        target.write_bytes(b"mp3-en")
        (target.parent / "voz-en.palabras.json").write_text("{}")
        return {"chars": len(text), "pieces": 1, "tasks": ["t"]}

    monkeypatch.setattr(tts, "generate", fake_generate)
    assert doblaje.prepare_all(tmp_path, log=lambda *_: None) == 1
    assert (folder / "guion-en.txt").read_text("utf-8").startswith("## THE BEGINNING")
    assert (folder / "titulo-en.txt").read_text("utf-8").strip() == "The fine"
    assert spoken["voice"] == "EN1" and "THE BEGINNING" not in spoken["text"]
    assert dub.pending(tmp_path) == [("n1", "en")]                          # the queue makes the dubbed video
    name = dub.prepare(tmp_path, "n1", "en")
    assert (folder.parent / name / "voz.palabras.json").is_file()             # its timings travel: no Whisper
    assert doblaje.prepare_all(tmp_path, log=lambda *_: None) == 0           # once
