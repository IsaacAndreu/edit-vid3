"""`## ` chapters written into a new script (pipeline/capitulos.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import capitulos

SCRIPT = "\n\n".join(f"Párrafo {n} con su texto." for n in range(8))


def test_the_titles_go_before_the_chosen_paragraphs():
    text = capitulos.with_chapters(SCRIPT, [{"paragraph": 2, "title": "la cláusula"}, {"paragraph": 5, "title": "Europa"},
                                            {"paragraph": 0, "title": "no"}, {"paragraph": 99, "title": "no"}])
    lines = [l for l in text.splitlines() if l]
    assert lines[2] == "## LA CLÁUSULA" and lines[3] == "Párrafo 2 con su texto."
    assert lines[6] == "## EUROPA" and "## NO" not in text
    with pytest.raises(ValueError):
        capitulos.with_chapters(SCRIPT, [{"paragraph": 2, "title": "solo uno"}])


def _video(tmp_path: Path, script: str = SCRIPT):
    from pipeline.context import RunContext

    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    folder = tmp_path / "materiales" / "v1"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text(script, encoding="utf-8")
    return RunContext.create("v1", root=tmp_path), folder


def test_a_new_video_gets_them_once_and_keeps_the_original(tmp_path, monkeypatch):
    ctx, folder = _video(tmp_path)
    calls = []

    def fake(ctx, **kwargs):
        calls.append(kwargs["user"])
        return {"chapters": [{"paragraph": 2, "title": "UNO"}, {"paragraph": 5, "title": "DOS"}]}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    assert capitulos.ensure(ctx) is True
    assert "## UNO" in (folder / "guion.txt").read_text("utf-8")
    assert (folder / capitulos.BACKUP).read_text("utf-8") == SCRIPT
    assert capitulos.ensure(ctx) is False and len(calls) == 1


def test_a_video_already_started_or_with_chapters_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.llm.complete_json", lambda *a, **k: pytest.fail("no call"))
    ctx, folder = _video(tmp_path, "## MÍO\n\n" + SCRIPT)
    assert capitulos.ensure(ctx) is False
    (folder / "guion.txt").write_text(SCRIPT, encoding="utf-8")
    (ctx.work_dir / ".stages").mkdir(parents=True)
    (ctx.work_dir / ".stages" / "align.json").write_text("{}")
    assert capitulos.ensure(ctx) is False
