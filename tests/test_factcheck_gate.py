"""The narration waits when the fact check finds a claim wrong (atlas channels), once per version of the script."""

from pathlib import Path

import pytest

from pipeline import factcheck, tts
from pipeline.context import RunContext


def _ctx(tmp_path: Path, style="atlas"):
    ctx = RunContext.create("v", root=tmp_path, config={"visual": {"style": style}})
    ctx.materials_dir.mkdir(parents=True, exist_ok=True)
    (ctx.materials_dir / "guion.txt").write_text("En 1955 SAS voló sobre el polo.", encoding="utf-8")
    return ctx


def test_wrong_claims_block_the_voice_and_the_check_runs_once_per_script(monkeypatch, tmp_path: Path):
    calls = []

    def fake(ctx):
        calls.append(1)
        return {"claims": [{"quote": "En 1955", "claim": "SAS voló en 1955", "verdict": "wrong", "correction": "1954"}]}

    monkeypatch.setattr(factcheck, "check", fake)
    ctx = _ctx(tmp_path)
    assert factcheck.blocks_voice(ctx)
    assert len(factcheck.gate(ctx)) == 1 and len(factcheck.gate(ctx)) == 1 and len(calls) == 1
    (ctx.materials_dir / "guion.txt").write_text("En 1954 SAS voló sobre el polo.", encoding="utf-8")
    factcheck.gate(ctx)
    assert len(calls) == 2                                   # a new script: checked again
    (ctx.materials_dir / factcheck.ACCEPTED).write_text("")
    assert factcheck.gate(ctx) == []                         # you checked them yourself


def test_tts_raises_before_paying(monkeypatch, tmp_path: Path):
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(tts, "voice_for_video", lambda c: {"voice_id": "x", "model_id": "m"})
    monkeypatch.setattr(factcheck, "gate", lambda c: [{"quote": "En 1955", "verdict": "wrong", "correction": "1954"}])
    made = []
    monkeypatch.setattr(tts, "_make", lambda *a: made.append(1))
    with pytest.raises(tts.WrongFacts):
        tts.ensure(ctx)
    assert not made and not factcheck.blocks_voice(_ctx(tmp_path / "b", style="stickman"))
