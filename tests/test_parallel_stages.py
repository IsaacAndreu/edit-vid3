"""Fase 5: factcheck runs beside align and planner (waited for before the first paid stage); same markers, and an
error in the background stage still stops the video. (people stays in its place: its plan B reads the HD clips
ingest downloads.)"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from pipeline import runner
from pipeline.context import RunContext
from pipeline.runner import Stage, run_stages

NAMES = ["factcheck", "align", "planner", "sourcing", "analysis", "people", "fallback"]


def _ctx(tmp_path, **speed):
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    return RunContext.create("v", root=tmp_path, config={"speed": speed})


def _stages(log, slow=(), fail=()):
    def make(name):
        def run(ctx):
            log.append(("start", name, threading.current_thread().name))
            if name in fail:
                raise RuntimeError(f"{name} falló")
            if name in slow:
                time.sleep(0.3)
            (ctx.work_dir / f"{name}.json").write_text("{}")
            log.append(("end", name))
        return Stage(name, lambda c, n=name: [c.work_dir / f"{n}.json"], lambda c: [], run, None, ())
    return [make(n) for n in NAMES]


def test_factcheck_runs_beside_align_and_planner(tmp_path, monkeypatch):
    from pipeline import preflight

    monkeypatch.setattr(preflight, "video_problems", lambda ctx: [])
    log = []
    ctx = _ctx(tmp_path)
    with patch.multiple(runner, STAGES=_stages(log, slow=("factcheck",)), STAGE_NAMES=NAMES):
        done = run_stages(ctx)
    order = [(e[0], e[1]) for e in log]
    assert order.index(("start", "align")) < order.index(("end", "factcheck"))       # beside align
    assert order.index(("end", "factcheck")) < order.index(("start", "sourcing"))     # waited before paying
    assert order.index(("end", "ingest" if ("end", "ingest") in order else "analysis")) < order.index(("start", "people"))
    assert done == NAMES                                                               # reported in stage order
    assert all((ctx.work_dir / ".stages" / f"{n}.json").is_file() for n in NAMES)


def test_a_background_error_stops_the_video_before_paying(tmp_path, monkeypatch):
    from pipeline import preflight

    monkeypatch.setattr(preflight, "video_problems", lambda ctx: [])
    log = []
    ctx = _ctx(tmp_path)
    with patch.multiple(runner, STAGES=_stages(log, fail=("factcheck",)), STAGE_NAMES=NAMES):
        with pytest.raises(RuntimeError, match="factcheck falló"):
            run_stages(ctx)
    assert ("start", "sourcing") not in [(e[0], e[1]) for e in log]
    import json

    assert json.loads((ctx.work_dir / "current.json").read_text())["stage"] == "factcheck"   # the notice says where


def test_off_keeps_the_old_order(tmp_path, monkeypatch):
    from pipeline import preflight

    monkeypatch.setattr(preflight, "video_problems", lambda ctx: [])
    log = []
    with patch.multiple(runner, STAGES=_stages(log), STAGE_NAMES=NAMES):
        run_stages(_ctx(tmp_path, parallel_stages=False))
    assert [e[1] for e in log if e[0] == "start"] == NAMES
