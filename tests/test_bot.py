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
        if data:
            self.sent.append(data["text"])

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
    assert package.outputs(ctx)[0].name == "miniatura-1.jpg"
