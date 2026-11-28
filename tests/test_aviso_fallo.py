"""The failure notice says what really happened in THIS attempt and when the next one is — and says nothing for a
wait or a restart, nor the same failure twice in a row."""

from __future__ import annotations

import json
import os
import time

import pytest

from pipeline import aviso_fallo
from pipeline.context import RunContext


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "config.yaml").write_text("watch: {retry_now: 2, retry_minutes: 1, retry_hours: 6}\n")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "_vigilar.latido").write_text("x")          # the watcher is alive
    c = RunContext.create("v1", root=tmp_path)
    c.work_dir.mkdir(parents=True)
    return c


def _current(ctx, stage, pid):
    (ctx.work_dir / "current.json").write_text(json.dumps({"stage": stage, "number": 4, "of": 15, "pid": pid}))


def test_the_stage_is_this_attempts_and_the_next_try_is_in_a_minute(ctx):
    _current(ctx, "render", pid=1)                      # left by an attempt of another process
    started = time.time() - 125
    text = aviso_fallo.text(ctx, KeyError("x"), started=started, signature="s1")
    assert "render" not in text and "antes de la primera etapa" in text
    assert "KeyError" in text and "intento 1" in text and "en 1 min" in text and "unas horas" not in text
    _current(ctx, "planner", pid=os.getpid())
    text = aviso_fallo.text(ctx, KeyError("x"), started=started, signature="s1")
    assert "etapa 4/15 (planner)" in text and "2 min" in text


def test_spend_of_the_attempt_and_the_wait_after_a_few(ctx):
    started = time.time() - 60
    (ctx.work_dir / "costs.json").write_text(json.dumps({"entries": [
        {"at": "2020-01-01T00:00:00+00:00", "usd": 5.0},                  # an earlier attempt: not this one's
        {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "usd": 0.42},
        {"at": "roto", "usd": "x"}]}))                                     # a broken entry never breaks the notice
    (ctx.root / "out" / "_vigilar.json").write_text(json.dumps({"v1": {"sig": "s1", "tries": 2, "at": time.time(),
                                                                       "day": time.strftime("%Y-%m-%d"), "dayFails": 2}}))
    text = aviso_fallo.text(ctx, RuntimeError("boom"), started=started, signature="s1")
    assert "0.42 $" in text and "intento 3" in text and "en 6 h" in text
    (ctx.root / "out" / "_vigilar.json").write_text(json.dumps({"v1": {"sig": "s1", "tries": 4, "at": time.time(),
                                                                       "day": time.strftime("%Y-%m-%d"), "dayFails": 4}}))
    assert "mañana" in aviso_fallo.text(ctx, RuntimeError("boom"), started=started, signature="s1")
    (ctx.root / "out" / "_vigilar.latido").unlink()                    # no watcher: it does not retry by itself
    assert "Reintentar" in aviso_fallo.text(ctx, RuntimeError("boom"), started=started, signature="s9")


def test_the_same_failure_again_is_not_sent_twice(ctx):
    assert aviso_fallo.first_time(ctx, RuntimeError("Cannot allocate memory at 0x7f12"), "render")
    assert not aviso_fallo.first_time(ctx, RuntimeError("Cannot allocate memory at 0x9a33"), "render")
    assert aviso_fallo.first_time(ctx, ValueError("otra cosa"), "render")
    (ctx.root / "out" / aviso_fallo.SENT).write_text("{roto")              # a broken record: sent, not a crash
    assert aviso_fallo.first_time(ctx, ValueError("otra cosa"), "render")


def test_waits_and_restarts_are_no_failure():
    import main
    from pipeline.budget import BudgetReached

    assert not main.is_failure(BudgetReached("tope del día"))
    assert not main.is_failure(main.Stopped("reinicio"))
    assert not main.is_failure(RuntimeError("Error code: 402 - Insufficient Balance"))
    assert main.is_failure(KeyError("x"))
