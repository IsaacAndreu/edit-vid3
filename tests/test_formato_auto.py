"""The format chosen from the script (pipeline/formats.py: detect, ensure_auto)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import formats
from pipeline.context import RunContext


def _video(tmp_path: Path, own: str = "") -> RunContext:
    (tmp_path / "config.yaml").write_text("canal: ''\nformat: historia\n", encoding="utf-8")
    folder = tmp_path / "materiales" / "v1"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("Número 10: … Número 1: el peor fallo de la historia.", encoding="utf-8")
    if own:
        (folder / "config.yaml").write_text(own, encoding="utf-8")
    return RunContext.create("v1", root=tmp_path)


def test_a_ranking_script_gets_the_ranking_format_once(tmp_path, monkeypatch):
    calls = []

    def fake(ctx, **kw):
        calls.append(kw["user"])
        return {"format": "ranking", "why": "Cuenta del 10 al 1"}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    ctx = _video(tmp_path)
    assert formats.ensure_auto(ctx) is True
    assert "format: ranking" in (ctx.materials_dir / "config.yaml").read_text("utf-8")
    assert "HABITUAL DEL CANAL: historia" in calls[0] and "- ranking:" in calls[0]
    assert RunContext.create("v1", root=tmp_path).config["format"] == "ranking"
    assert formats.ensure_auto(RunContext.create("v1", root=tmp_path)) is False and len(calls) == 1


def test_the_channels_own_or_an_unknown_answer_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **kw: {"format": "inventado", "why": "x"})
    ctx = _video(tmp_path)
    assert formats.ensure_auto(ctx) is False
    assert not (ctx.materials_dir / "config.yaml").exists() and (ctx.materials_dir / formats.AUTO).is_file()


def test_a_format_you_chose_is_never_touched(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **kw: pytest.fail("no call"))
    ctx = _video(tmp_path, "format: misterio\n")
    assert formats.ensure_auto(ctx) is False
