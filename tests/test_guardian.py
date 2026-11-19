"""Fase 2.3-2.4: a hung video is cut (not only reported), the queue closes its children when it stops, and each
result reaches out/_vigilar.json as soon as the video ends."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from pipeline.guardian import Guardian, running_stage


def _current(root, slug, **fields):
    folder = root / "work" / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "current.json").write_text(json.dumps({"stage": "render", "pid": 1, **fields}))


def _sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_a_stage_over_its_limit_is_cut(tmp_path):
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
    _current(tmp_path, "v", started=long_ago)
    (tmp_path / "work" / "v" / "words.json").write_text(json.dumps({"durationSeconds": 600}))
    guardian = Guardian(tmp_path, {"grace_seconds": 5})
    process = _sleeper()
    guardian.watch("v", process)
    assert guardian.limit_seconds("v") == 60 * (360 + 20 * 10)            # 9.3 h for a 10-min video
    assert guardian.check() == []                                            # 9 h: still inside
    _current(tmp_path, "v", started=(datetime.now(timezone.utc) - timedelta(hours=10)).isoformat())
    assert guardian.check() == ["v"]
    process.wait(10)
    assert "etapa render" in guardian.done("v")


def test_silence_counts_only_while_a_stage_runs(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    guardian = Guardian(tmp_path, {"silent_minutes": 0.001, "grace_seconds": 5})
    process = _sleeper()
    _current(tmp_path, "v", started=now, waiting=True)                     # waiting for its turn: never cut
    guardian.watch("v", process)
    time.sleep(0.2)
    assert guardian.check() == [] and running_stage(tmp_path, "v") is None
    _current(tmp_path, "v", started=now)
    assert guardian.check() == ["v"]
    process.wait(10)
    assert "sin escribir nada" in guardian.done("v")


def test_stopping_the_queue_closes_every_child(tmp_path):
    guardian = Guardian(tmp_path, {"grace_seconds": 5})
    children = [_sleeper(), _sleeper()]
    for n, child in enumerate(children):
        guardian.watch(f"v{n}", child)
    guardian.stop_all()
    assert all(child.poll() is not None for child in children)


def test_the_parallel_queue_reports_each_result_at_once_and_stops_on_new_code(monkeypatch, tmp_path):
    import main

    nap = time.sleep
    started, results_seen = [], []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            started.append(args[args.index("--slug") + 1])
            self.stdout = iter(["hecho\n"])

        def wait(self):
            nap(0.05)
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    for name, value in (("is_drawn", lambda root, slug: False), ("needs_youtube", lambda root, slug: True),
                        ("footage_at_once", lambda root: 1), ("waits_for_youtube", lambda root, slug: False),
                        ("on_hold", lambda root, slug: False),
                        ("voice_in_background", lambda root, slug, folders=None: False),
                        ("_write_report", lambda root, results: None), ("notify", lambda root, text: None)):
        monkeypatch.setattr(main, name, value)
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.02)))
    checks = []

    def new_code():
        checks.append(1)
        return len(checks) >= 2

    clock = [0.0]
    real = time.monotonic
    monkeypatch.setattr(main.time, "monotonic", lambda: real() + clock[0])

    def on_result(slug, status):
        results_seen.append((slug, status))
        clock[0] += 200                    # each video «takes» 200 s: the new-code check is due before the next

    main.run_parallel(["v1", "v2", "v3", "v4"], 1, force=set(), until=None, review=False, root=tmp_path,
                      new_code=new_code, on_result=on_result)
    assert results_seen[:2] == [("v1", "OK"), ("v2", "OK")]
    assert started == ["v1", "v2"]                                   # new code: nothing more starts
