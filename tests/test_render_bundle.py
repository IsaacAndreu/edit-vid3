"""Fase 4.1: Remotion's code is bundled once per code signature; each job gets its own folder (hard links) with its
own public files, so two renders can overlap. (Checked by hand on 19-11: the same PNG, byte for byte, as before.)"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline import render
from pipeline.context import RunContext


def test_one_bundle_per_code_and_a_folder_per_job(tmp_path, monkeypatch):
    (tmp_path / "remotion").mkdir()
    (tmp_path / "remotion" / "index.ts").write_text("export {}")
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={})
    (ctx.work_dir / "media").mkdir(parents=True)
    (ctx.work_dir / "media" / "a.jpg").write_bytes(b"jpg")
    bundles = []

    def run(cmd, **kw):
        if "bundle" in cmd:
            out = Path(next(c for c in cmd if c.startswith("--out-dir=")).split("=", 1)[1])
            out.mkdir(parents=True)
            (out / "index.html").write_text("<html>")
            (out / "main.bundle.js").write_text("js")
            bundles.append(out)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render.subprocess, "run", run)
    monkeypatch.setattr(render, "ensure_node_modules", lambda root: None)
    r = render.Renderer(ctx)
    one = r._job_bundle({"media/a.jpg"}, "A")
    two = r._job_bundle(set(), "B")
    assert len(bundles) == 1                                         # bundled once
    assert (one / "main.bundle.js").is_file() and (one / "public" / "media" / "a.jpg").read_bytes() == b"jpg"
    assert not (two / "public" / "media").exists() and one != two   # each job its own public/
    (tmp_path / "remotion" / "index.ts").write_text("export const x = 1")
    r._job_bundle(set(), "C")
    assert len(bundles) == 2                                         # new code: a new bundle
