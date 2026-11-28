"""Every attempt of a video on its card: stage, error, seconds, dollars and proxy GB — what a video cost in money and
time, failures included."""

from __future__ import annotations

import json
import os
import time

import pytest

from pipeline import intentos
from pipeline.context import RunContext


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    c = RunContext.create("v1", root=tmp_path)
    c.work_dir.mkdir(parents=True)
    return c


def _now_iso(offset=0):
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + offset))


def test_a_failed_attempt_and_a_good_one_are_on_the_card(ctx):
    started = time.time() - 300
    (ctx.work_dir / "current.json").write_text(json.dumps({"stage": "sourcing", "pid": os.getpid()}))
    (ctx.work_dir / "costs.json").write_text(json.dumps({"entries": [
        {"at": "2020-01-01T00:00:00+00:00", "usd": 9.0}, {"at": _now_iso(), "usd": 0.30}]}))
    with (ctx.work_dir / "youtube_downloads.jsonl").open("w") as log:
        log.write(json.dumps({"proxy": "residencial", "proxy_bytes": 2_000_000_000, "ts": time.time()}) + "\n")
        log.write(json.dumps({"proxy": "residencial", "proxy_bytes": 5_000_000_000, "ts": 1.0}) + "\n")   # old
        log.write("{no es json\n")
    intentos.record(ctx, started, "ERROR", RuntimeError("YouTube pide confirmar que no eres un bot"))
    intentos.record(ctx, time.time() - 60, "OK")
    card = intentos.load(ctx.work_dir)
    first, second = card["attempts"]
    assert first["status"] == "ERROR" and first["stage"] == "sourcing" and "bot" in first["error"]
    assert first["seconds"] == pytest.approx(300, abs=5) and first["usd"] == pytest.approx(0.30)
    assert first["proxyGb"] == pytest.approx(2.0)
    assert second["status"] == "OK" and second["error"] == ""
    assert card["lost"]["attempts"] == 1 and card["lost"]["usd"] == pytest.approx(0.30)
    assert card["total"]["attempts"] == 2


def test_a_broken_card_starts_again_and_it_keeps_the_last_fifty(ctx):
    (ctx.work_dir / intentos.FILE).write_text("[roto")
    assert intentos.load(ctx.work_dir)["attempts"] == []
    for n in range(intentos.KEEP + 5):
        intentos.record(ctx, time.time(), "ERROR", ValueError(str(n)))
    attempts = intentos.load(ctx.work_dir)["attempts"]
    assert len(attempts) == intentos.KEEP and attempts[-1]["error"].endswith(str(intentos.KEEP + 4))


def test_the_studio_shows_the_card(tmp_path):
    from pipeline import web
    from tests.test_web import SCRIPT, _project

    _project(tmp_path)
    web.create_video(tmp_path, {"name": "v1", "channel": "aviacion", "script": SCRIPT})
    ctx = RunContext.create("v1", root=tmp_path)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    intentos.record(ctx, time.time() - 10, "en espera", None)
    detail = web.video_detail(tmp_path, "v1")
    assert detail["attempts"]["attempts"][0]["status"] == "en espera"
