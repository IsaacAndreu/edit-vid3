"""27-11 [A3]: the per-video cap was per attempt (five attempts of 1.40 $ = 7 $ with the cap at 1.50 $) and was
only looked at between stages and in the judge and the fill-in (one text stage spent 6 $ before stopping)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from pipeline import budget, llm
from pipeline.context import RunContext


def _ctx(tmp_path, cap=1.5):
    (tmp_path / "config.yaml").write_text(f"budget: {{per_video_usd: {cap}}}\nplanner: {{model: deepseek-flash}}\n")
    (tmp_path / "materiales" / "v1").mkdir(parents=True)
    ctx = RunContext.create("v1", root=tmp_path)
    ctx.work_dir.mkdir(parents=True)
    return ctx


def _spent(ctx, *amounts, days_ago=0):
    at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    path = ctx.work_dir / "costs.json"
    old = json.loads(path.read_text()) if path.is_file() else {"entries": []}
    entries = old["entries"] + [{"at": at, "stage": "planner", "provider": "x", "usd": a} for a in amounts]
    path.write_text(json.dumps({"totalUsd": sum(e["usd"] for e in entries), "entries": entries}))


def test_the_cap_adds_every_attempt_of_the_day(tmp_path):
    ctx = _ctx(tmp_path)
    _spent(ctx, 1.0, days_ago=1)                          # yesterday does not count
    _spent(ctx, 0.6, 0.6)                                 # two attempts today: 1.20 $
    budget.ATTEMPT_START[str(ctx.work_dir)] = budget.video_spent(ctx.work_dir)   # a third attempt starts now
    budget.before_paid_call(ctx)                          # 1.20 ≤ 1.50: goes on
    _spent(ctx, 0.4)                                      # 1.60 today, though only 0.40 in this attempt
    with pytest.raises(budget.VideoOverBudget):
        budget.before_paid_call(ctx)


def test_every_model_request_asks_first(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, cap=0.5)
    _spent(ctx, 0.6)
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: (_ for _ in ()).throw(AssertionError("no request may go out")))
    with pytest.raises(budget.VideoOverBudget):
        llm.complete_json(ctx, stage="planner", system="s", user="u", section="planner", use_cache=False)


def test_the_studios_own_work_is_not_a_video(tmp_path):
    ctx = _ctx(tmp_path, cap=0.1)
    other = RunContext.create("_radar", root=tmp_path)
    budget.before_paid_call(other)                        # nothing to put on hold: no check
