"""Fase 0.4: the stage markers keep the turn's wait and the failed attempts apart from the work, and
pipeline/tiempos.py shows them separately."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline import runner, tiempos
from pipeline.context import RunContext
from pipeline.runner import Stage, run_stages


def _ctx(tmp_path: Path) -> RunContext:
    (tmp_path / "materiales" / "demo").mkdir(parents=True)
    return RunContext.create("demo", root=tmp_path, config={"step": {"k": 1}})


def test_marker_keeps_wait_and_failed_attempts(tmp_path):
    ctx = _ctx(tmp_path)
    calls = []

    def run(c):
        calls.append(1)
        if len(calls) == 1:
            raise NameError("name 'official' is not defined")
        (c.work_dir / "out.json").write_text("{}")

    stage = Stage("first", lambda c: [c.work_dir / "out.json"], lambda c: [], run, None, ("step",))
    clock = iter([100.0, 130.0, 160.0, 1000.0, 1010.0, 1050.0, 1050.0, 1060.0, 1070.0])
    with patch.multiple(runner, STAGES=[stage], STAGE_NAMES=["first"]), \
            patch.object(runner.time, "monotonic", lambda: next(clock, 2000.0)):
        with pytest.raises(NameError):
            run_stages(ctx)
        failures = (ctx.work_dir / ".stages" / "first.fallos.jsonl").read_text().splitlines()
        assert json.loads(failures[0])["error"] == "NameError"
        assert json.loads(failures[0])["waitSeconds"] == 30.0 and json.loads(failures[0])["seconds"] == 30.0
        run_stages(ctx)
    marker = json.loads((ctx.work_dir / ".stages" / "first.json").read_text())
    assert marker["waitSeconds"] == 10.0
    assert marker["failedSeconds"] == 30.0 and marker["failedAttempts"][0]["error"] == "NameError"
    assert not (ctx.work_dir / ".stages" / "first.fallos.jsonl").exists()
    assert tiempos.stage_seconds(ctx.work_dir) == {"first": marker["seconds"]}      # the .jsonl is not a stage


def test_report_shows_wait_and_lost_work(tmp_path):
    done = tmp_path / "work" / "hecho" / ".stages"
    done.mkdir(parents=True)
    (done / "render.json").write_text(json.dumps({"seconds": 600, "waitSeconds": 1200}))
    (done / "sourcing.json").write_text(json.dumps({"seconds": 1800, "failedSeconds": 900, "failedWaitSeconds": 60}))
    dead = tmp_path / "work" / "muerto" / ".stages"
    dead.mkdir(parents=True)
    (dead / "coldopen.fallos.jsonl").write_text(json.dumps({"error": "NameError", "seconds": 4 * 3600, "waitSeconds": 0}) + "\n")
    text = tiempos.markdown(tiempos.report(tmp_path))
    assert "Espera de turno" in text and "| render | 10 min | 10 min | 25% | 20 min | — |" in text
    assert "15 min + 1 min" in text
    assert "muerto (4 h 00 min, sobre todo apertura)" in text
