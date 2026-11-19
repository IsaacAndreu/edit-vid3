"""Fase 2.5: the queue checks what would make its videos fail before starting, and each video before it pays the
proxy."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pipeline import preflight, runner
from pipeline.context import RunContext
from pipeline.runner import Stage, run_stages


def test_a_broken_channel_profile_is_a_warning_and_missing_tools_block(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "roto.yaml").write_text("ideas: [sin cerrar\n")
    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)
    from pipeline import chequeo

    monkeypatch.setattr(chequeo.shutil, "which", lambda name: None)
    blockers, warnings = preflight.queue_problems(tmp_path, imports=False)
    assert any("ffmpeg" in b for b in blockers) and any("node_modules/remotion" in b for b in blockers)
    assert any("roto.yaml" in w for w in warnings)


def test_a_video_is_stopped_before_its_first_paid_stage(tmp_path, monkeypatch):
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(RunContext, "env", lambda self, name, required=True: "")
    ran = []
    stage = Stage("sourcing", lambda c: [c.work_dir / "x.json"], lambda c: [], lambda c: ran.append(1), None, ())
    with patch.multiple(runner, STAGES=[stage], STAGE_NAMES=["sourcing"]):
        with pytest.raises(RuntimeError, match="No empiezo a gastar proxy.*OPENAI_API_KEY"):
            run_stages(ctx)
    assert ran == []
