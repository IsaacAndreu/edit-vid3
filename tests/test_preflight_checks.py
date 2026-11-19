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


def test_what_a_stage_would_download_at_night_is_fetched_before_the_queue(tmp_path, monkeypatch):
    """4.10: Node packages, Remotion's browser and the face models come before the queue, each with a time limit."""

    import json
    import subprocess

    from pipeline import identity, render

    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"remotion": "4", "nueva-fuente": "1"}}))
    (tmp_path / "node_modules" / "remotion").mkdir(parents=True)
    (tmp_path / "node_modules" / "remotion" / "package.json").write_text("{}")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("timeout")))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    monkeypatch.setattr(preflight, "remotion_browser", lambda root: False)
    monkeypatch.setattr(identity, "model_path", lambda ctx, name: None if name == "sface" else tmp_path / "m.onnx")
    warnings = preflight.prepare_assets(tmp_path, run=fake_run)
    assert calls[0][0][1:] == ["install", "--no-audit", "--no-fund"] and calls[0][1] == render.NPM_TIMEOUT
    assert calls[1][0][1:] == ["remotion", "browser", "ensure"] and calls[1][1] == preflight.ASSET_TIMEOUT
    assert warnings == ["no se pudo descargar el modelo de caras sface: se intentará en la etapa que lo use"]


def test_a_hung_npm_install_is_cut(tmp_path, monkeypatch):
    import json
    import subprocess

    from pipeline import render

    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"falta": "1"}}))

    def hangs(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(render.subprocess, "run", hangs)
    with pytest.raises(RuntimeError, match="no terminó"):
        render.ensure_node_modules(tmp_path)
