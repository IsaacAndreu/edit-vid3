from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pipeline import bot, package
from pipeline.context import RunContext

REPO = Path(__file__).resolve().parent.parent


class _Http:
    def __init__(self):
        self.sent = []

    def post(self, url, data=None, json=None, timeout=None):
        if data and "text" in data:
            self.sent.append(data["text"])
        elif json and "text" in json:
            self.sent.append(json["text"])

    def get(self, *a, **k):
        raise AssertionError("no network in tests")


def _root(tmp_path: Path) -> Path:
    shutil.copy(REPO / "config.yaml", tmp_path / "config.yaml")
    shutil.copytree(REPO / "canales", tmp_path / "canales")
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=1:x\nTELEGRAM_CHAT_ID=42\n")
    folder = tmp_path / "materiales" / "avion1"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("x" * 300)
    (folder / "voz.mp3").write_bytes(b"x")
    work = tmp_path / "work" / "avion1"
    work.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (work / "costs.json").write_text(json.dumps({"totalUsd": 0.9, "entries": [
        {"at": now, "provider": "openai", "usd": 0.6}, {"at": now, "provider": "deepseek", "usd": 0.3},
        {"at": "2020-01-01T00:00:00+00:00", "provider": "openai", "usd": 5}]}))
    (work / "current.json").write_text(json.dumps({"stage": "render", "number": 13, "of": 15, "started": now}))
    return tmp_path


def _bot(root: Path) -> tuple[bot.Bot, _Http]:
    http = _Http()
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        b = bot.Bot(root, session=http)
    return b, http


def test_commands_answer_only_your_chat(tmp_path):
    root = _root(tmp_path)
    b, http = _bot(root)
    b.handle({"message": {"chat": {"id": 999}, "text": "/estado"}})
    assert http.sent == []                                             # a stranger gets nothing
    b.handle({"message": {"chat": {"id": 42}, "text": "/estado"}})
    assert "avion1 · 13/15 Render" in http.sent[-1] and "Hoy: 0,90 $" in http.sent[-1]
    b.handle({"message": {"chat": {"id": 42}, "text": "/gasto"}})
    assert "Hoy: 0,90 $" in http.sent[-1] and "openai: 0,60 $" in http.sent[-1]
    b.handle({"message": {"chat": {"id": 42}, "text": "/pausa"}})
    assert (root / "out" / "_pausa").is_file()
    b.handle({"message": {"chat": {"id": 42}, "text": "/limite 12,5"}})
    assert json.loads((root / "out" / "_ajustes.json").read_text())["daily_usd"] == 12.5
    b.handle({"message": {"chat": {"id": 42}, "text": "/loquesea"}})
    assert "/gasto" in http.sent[-1]


def test_hourly_report_and_watcher_warning(tmp_path):
    root = _root(tmp_path)
    b, http = _bot(root)
    b.state["hourly"] = time.time() - 3700
    beat = root / "out" / "_vigilar.latido"
    beat.parent.mkdir(parents=True, exist_ok=True)
    beat.write_text("x")
    old = time.time() - 3600
    os.utime(beat, (old, old))
    b.chores()
    assert any(m.startswith("🕐 Parte") for m in http.sent)
    assert any("vigilante no da señales" in m for m in http.sent)
    count = len(http.sent)
    b.chores()                                                        # no repeats within the hour
    assert len(http.sent) == count


def test_thumbnails_can_be_left_to_you(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={"miniaturas": {"enabled": False}})
    assert package.outputs(ctx) == [ctx.out_dir / "youtube.txt"]
    ctx = RunContext.create("v", root=tmp_path, config={})
    assert package.outputs(ctx) == [ctx.out_dir / "youtube.txt"]                 # off unless you ask for them
    ctx = RunContext.create("v", root=tmp_path, config={"miniaturas": {"enabled": True}})
    assert package.outputs(ctx)[0].name == "miniatura-1.jpg"


def test_a_hung_llm_call_is_cut_off_and_a_killed_run_is_not_shown_as_running(tmp_path):
    import pytest

    from pipeline import llm, web

    assert llm._within(2, lambda: 7) == 7
    with pytest.raises(TimeoutError):
        llm._within(0.2, lambda: time.sleep(3))
    with pytest.raises(ValueError):
        llm._within(2, lambda: (_ for _ in ()).throw(ValueError("x")))
    assert web.running({"stage": "planner", "pid": os.getpid()})
    assert web.running({"stage": "planner", "pid": 999999}) is None             # the process is gone
    assert web.running({"stage": "planner"})                                     # old files without pid


def test_whisper_audio_is_decoded_by_ffmpeg(tmp_path):
    import subprocess

    from pipeline.whisper_local import decode_audio

    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-ar", "44100", str(wav)], check=True)
    audio = decode_audio(wav)
    assert audio.dtype.name == "float32" and 15000 <= len(audio) <= 17000 and float(abs(audio).max()) <= 1.0


def test_calendar_commands_morning_and_the_uploaded_button(tmp_path):
    root = _root(tmp_path)
    (root / "work" / "avion1" / "current.json").unlink()
    (root / "out" / "avion1").mkdir(parents=True)
    (root / "out" / "avion1" / "video-final.mp4").write_bytes(b"x")
    b, http = _bot(root)
    for command in ("/hoy", "/semana", "/huecos"):
        b.handle({"message": {"chat": {"id": 42}, "text": command}})
    assert len(http.sent) == 3 and http.sent[0].startswith("📅")
    noon = datetime.now().replace(hour=12, minute=0).timestamp()
    b.calendar_chores(noon)
    b.calendar_chores(noon + 60)                                       # the morning summary only once a day
    assert sum(t.startswith("☀️") for t in http.sent) == 1
    b.handle({"callback_query": {"id": "1", "data": "subido:avion1", "message": {"chat": {"id": 42}}}})
    assert (root / "out" / "avion1" / "publicado.json").is_file() and "marcado como subido" in http.sent[-1]


def test_material_for_your_own_thumbnail(tmp_path):
    import subprocess

    from pipeline.schemas import Timeline

    ctx = RunContext.create("v", root=tmp_path, config={})
    clip = ctx.work_dir / "media" / "s1.mp4"
    clip.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=1",
                    str(clip)], check=True)
    cut = ctx.work_dir / "people" / "ana.png"
    cut.parent.mkdir(parents=True)
    cut.write_bytes(b"png")
    timeline = Timeline.model_construct(fps=30, shots=[type("S", (), {"coldOpen": False, "from_": 0, "media": type(
        "M", (), {"kind": "video", "src": "media/s1.mp4"})()})()])
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    (ctx.out_dir / "youtube.txt").write_text("TÍTULO\nX\n", encoding="utf-8")
    assert package.material_for_thumbnail(ctx, timeline, ["ÚLTIMO DE 91", "DOBLE ORO"], "people/ana.png") == 1
    still = ctx.out_dir / "fotogramas" / "fotograma-1.jpg"
    import cv2

    assert cv2.imread(str(still)).shape[:2] == (1080, 1920)
    assert (ctx.out_dir / "fotogramas" / "recorte.png").is_file()
    package.material_for_thumbnail(ctx, timeline, ["ÚLTIMO DE 91"], None)          # a rerun: one block, not two
    text = (ctx.out_dir / "youtube.txt").read_text("utf-8")
    assert text.count("IDEAS PARA LA MINIATURA") == 1 and "- ÚLTIMO DE 91" in text
