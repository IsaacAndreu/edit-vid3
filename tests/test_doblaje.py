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


def test_turned_on_in_the_studio_with_the_channel_voice_and_only_new_videos_if_asked(tmp_path, monkeypatch):
    import os
    import time

    folder = _done_video(tmp_path, "format: historia\n")
    tts.set_voice(tmp_path, "negocios", {"voice_id": "ES1", "model_id": "eleven_flash_v2_5"})
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **kw: {"title": "T", "script": "A multa da Booking aqui. " * 40})
    spoken = []

    def fake_generate(token, text, voice, target, session=None, log=print):
        spoken.append((target.name, voice["voice_id"], voice["model_id"]))
        target.write_bytes(b"mp3")
        return {"chars": len(text), "pieces": 1, "tasks": ["t"]}

    monkeypatch.setattr(tts, "generate", fake_generate)
    final = tmp_path / "out" / "n1" / "video-final.mp4"
    os.utime(final, (time.time() - 3600, time.time() - 3600))                  # made before dubbing was turned on
    tts.set_dubbing(tmp_path, "negocios", {"languages": ["pt", "de", "xx"], "voices": {"de": {"voice_id": "DE1"}},
                                           "existing": False})
    assert doblaje.prepare_all(tmp_path, log=lambda *_: None) == 0             # only the new ones
    tts.set_dubbing(tmp_path, "negocios", {"languages": ["pt", "de"], "voices": {"de": {"voice_id": "DE1"}}})
    assert doblaje.prepare_all(tmp_path, log=lambda *_: None) == 2
    assert sorted(spoken) == [("voz-de.mp3", "DE1", "eleven_multilingual_v2"),
                              ("voz-pt.mp3", "ES1", "eleven_multilingual_v2")]   # no own voice: the channel's, multilingual
    assert sorted(lang for _, lang in dub.pending(tmp_path)) == ["de", "pt"]
    assert tts.voices(tmp_path).keys() == {"negocios"}                         # the dubbing entry is no voice
    tts.set_dubbing(tmp_path, "negocios", {"languages": []})
    assert tts.dubbing_for(tmp_path, "negocios") == {}


def test_a_channel_dubbed_from_the_studio_keeps_its_clips_after_the_video(tmp_path):
    from pipeline import housekeeping
    from pipeline.context import RunContext

    folder = _done_video(tmp_path, "format: historia\ncleanup: {after_video: true}\n")
    tts.set_dubbing(tmp_path, "negocios", {"languages": ["pt"]})
    ctx = RunContext.create("n1", root=tmp_path)
    (ctx.work_dir / "media").mkdir(parents=True)
    (ctx.work_dir / "render").mkdir(parents=True)
    housekeeping.after_video(ctx)
    assert (ctx.work_dir / "media").is_dir() and not (ctx.work_dir / "render").exists()   # the dub needs the clips


def test_your_own_translation_is_used_and_a_hand_made_dub_is_never_redone(tmp_path):
    import json

    from pipeline import doblaje, tts
    from pipeline.housekeeping import is_done

    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "gimnasia.yaml").write_text("format: historia\n")
    video = tmp_path / "materiales" / "gimnasia" / "yulo"
    video.mkdir(parents=True)
    (video / "config.yaml").write_text("canal: gimnasia\n")
    (video / "guion.txt").write_text("hola " * 80)
    (video / "voz-pt.mp3").write_bytes(b"old")
    tts.set_dubbing(tmp_path, "gimnasia", {"languages": ["pt"], "voices": {"pt": {"voice_id": "v1"}}, "existing": False})
    with pytest.raises(ValueError):
        doblaje.set_script(tmp_path, "yulo", "pt", "muito curto")
    doblaje.set_script(tmp_path, "yulo", "pt", "olá " * 80, "Yulo: o ginasta")
    assert (video / "guion-pt.txt").read_text().startswith("olá") and not (video / "voz-pt.mp3").exists()
    [state] = doblaje.status(tmp_path, "yulo")
    assert state["own"] and state["title"] == "Yulo: o ginasta" and state["voiceId"] and not state["done"]
    doblaje.mark_manual(tmp_path, "yulo", "pt")
    assert is_done(tmp_path, "yulo-pt") and doblaje.status(tmp_path, "yulo")[0]["manual"]
    doblaje.mark_manual(tmp_path, "yulo", "pt", False)
    assert not is_done(tmp_path, "yulo-pt")


def test_a_new_video_in_portuguese_uses_the_portuguese_voice_and_words(tmp_path):
    from pipeline import tts, web
    from pipeline.context import RunContext
    from pipeline.timeline import locale_for

    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "gimnasia.yaml").write_text("format: historia\n")
    tts.set_voice(tmp_path, "gimnasia", {"voice_id": "es-voice"})
    tts.set_dubbing(tmp_path, "gimnasia", {"languages": ["pt"], "voices": {"pt": {"voice_id": "pt-voice"}}})
    made = web.create_video(tmp_path, {"name": "biles-pt", "channel": "gimnasia", "script": "Olá. " * 60, "language": "pt"})
    ctx = RunContext.create(made["slug"], root=tmp_path)
    assert ctx.section("align")["language"] == "pt" and tts.voice_for_video(ctx)["voice_id"] == "pt-voice"
    spanish = web.create_video(tmp_path, {"name": "biles", "channel": "gimnasia", "script": "Hola. " * 60})
    assert tts.voice_for_video(RunContext.create(spanish["slug"], root=tmp_path))["voice_id"] == "es-voice"
    assert locale_for("pt")["chapter"] == "CAPÍTULO" and locale_for("pt")["subscribe"] == "INSCREVA-SE" and locale_for("es") == {}
    with pytest.raises(ValueError):
        web.create_video(tmp_path, {"name": "x", "channel": "gimnasia", "script": "Hola. " * 60, "language": "xx"})


def test_a_dub_of_a_cleaned_original_downloads_its_clips_again(tmp_path, monkeypatch):
    import json

    from pipeline import dub, runner
    from pipeline.context import RunContext

    (tmp_path / "config.yaml").write_text("{}\n")
    video = tmp_path / "materiales" / "atleti10"
    video.mkdir(parents=True)
    ctx = RunContext.create("atleti10", root=tmp_path, config={})
    ctx.work_dir.mkdir(parents=True)
    (ctx.work_dir / "timeline.json").write_text(json.dumps({"shots": [{"media": {"src": "coldopen/c01.mp4"}},
                                                                      {"media": {"src": "audio/voz.mp3"}}]}))
    (ctx.work_dir / "audio").mkdir()
    (ctx.work_dir / "audio" / "voz.mp3").write_bytes(b"x")
    assert dub.missing_media(ctx) == ["coldopen/c01.mp4"]
    calls = []

    def fake(c, force, until):
        calls.append((sorted(force), until))
        (c.work_dir / "coldopen").mkdir()
        (c.work_dir / "coldopen" / "c01.mp4").write_bytes(b"x")

    monkeypatch.setattr(runner, "run_stages", fake)
    dub.restore_original(ctx)
    assert calls == [(["coldopen", "fallback", "ingest", "people", "timeline"], "timeline")] and not dub.missing_media(ctx)
