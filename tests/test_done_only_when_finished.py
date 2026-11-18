"""Fase 2.1: a video is «done» only when every stage went through — not as soon as the render put its file down."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pipeline import housekeeping, render, runner
from pipeline.context import RunContext
from pipeline.runner import Stage, run_stages


def test_is_done_needs_the_last_stage(tmp_path):
    out = tmp_path / "out" / "v"
    out.mkdir(parents=True)
    (out / "video-final.mp4").write_bytes(b"x")
    assert housekeeping.is_done(tmp_path, "v")                       # finished before the mark existed
    (out / render.IN_PROGRESS).write_text("x")
    assert not housekeeping.is_done(tmp_path, "v")                   # rendered, Shorts or package still to come
    (out / housekeeping.REMOVED).write_text("{}")
    assert housekeeping.is_done(tmp_path, "v")                       # uploaded and cleaned up


def _stages(fail_last: bool):
    def mark(ctx):
        (ctx.out_dir).mkdir(parents=True, exist_ok=True)
        (ctx.out_dir / render.IN_PROGRESS).write_text("x")
        (ctx.out_dir / "video-final.mp4").write_bytes(b"x")
        (ctx.work_dir / "r.json").write_text("{}")

    def last(ctx):
        if fail_last:
            raise RuntimeError("shorts falló")
        (ctx.work_dir / "p.json").write_text("{}")

    return [Stage("render", lambda c: [c.work_dir / "r.json"], lambda c: [], mark, None, ()),
            Stage("package", lambda c: [c.work_dir / "p.json"], lambda c: [], last, None, ())]


def test_the_mark_goes_only_when_the_last_stage_ends(tmp_path):
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={})
    stages = _stages(fail_last=True)
    with patch.multiple(runner, STAGES=stages, STAGE_NAMES=["render", "package"]):
        with pytest.raises(RuntimeError):
            run_stages(ctx)
        assert not housekeeping.is_done(tmp_path, "v")
        run_stages(ctx, until="render")
        assert not housekeeping.is_done(tmp_path, "v")
    with patch.multiple(runner, STAGES=_stages(fail_last=False), STAGE_NAMES=["render", "package"]):
        run_stages(ctx)
    assert housekeeping.is_done(tmp_path, "v")
