"""The serial queue (one video at a time, in the queue's own process) has its watchdog too."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import main
from tests.test_queue import _materials


def test_a_stage_that_hangs_in_the_serial_queue_is_cut_and_the_night_goes_on(tmp_path):
    for slug in ("A", "B"):
        _materials(tmp_path, slug)
    done, notices = [], []

    def fake_run(slug, **kwargs):
        if slug == "A":                                  # the render has been running for 2 h and never ends
            (tmp_path / "work" / "A").mkdir(parents=True, exist_ok=True)
            started = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            (tmp_path / "work" / "A" / "current.json").write_text(json.dumps({"stage": "render", "started": started}))
            threading.Event().wait(30)
        done.append(slug)

    cfg = {"check_seconds": 0.05, "stage_minutes": 60, "stage_minutes_per_video_minute": 0, "grace_seconds": 1}
    began = time.monotonic()
    with patch.object(main, "run_one", side_effect=fake_run), patch.object(main, "_queue_cfg", lambda root: cfg), \
            patch.object(main, "notify", lambda root, text, **k: notices.append(text)):
        failures = main.run_queue(force=set(), until=None, review=False, root=tmp_path, check=False)
    report = (tmp_path / main.QUEUE_REPORT).read_text()
    assert time.monotonic() - began < 10
    assert failures == 1 and done == ["B"]
    assert "| A | ERROR |" in report and "perro guardián" in report and "render" in report
    assert any("✂ A" in n for n in notices)


def test_a_slow_stage_within_its_limit_is_never_cut(tmp_path):
    _materials(tmp_path, "A")

    def fake_run(slug, **kwargs):
        (tmp_path / "work" / "A").mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc).isoformat()       # just started: far from its limit
        (tmp_path / "work" / "A" / "current.json").write_text(json.dumps({"stage": "render", "started": started}))
        time.sleep(0.5)

    cfg = {"check_seconds": 0.05, "stage_minutes": 60, "silent_minutes": 0.001}   # (no output to hear in-process)
    with patch.object(main, "run_one", side_effect=fake_run), patch.object(main, "_queue_cfg", lambda root: cfg):
        assert main.run_queue(force=set(), until=None, review=False, root=tmp_path, check=False) == 0
