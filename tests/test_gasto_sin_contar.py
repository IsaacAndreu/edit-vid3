"""Spend that went uncounted: AI84 voices at 0 $, Serper's searches, and the studio's own work past the daily cap."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pipeline import budget, costs, tts
from pipeline.context import RunContext


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    return RunContext.create("v1", root=tmp_path)


def _entries(ctx):
    return json.loads((ctx.work_dir / "costs.json").read_text())["entries"]


def test_an_ai84_voice_without_a_price_says_so(ctx):
    usd, details = tts.voice_cost(ctx, {"model_id": "m"}, 14000, {"provider": "ai84", "credits": 900, "chars": 14000,
                                                                  "pieces": 3})
    assert usd == 0 and details["unpriced"] is True and details["credits"] == 900
    ctx.config.setdefault("tts", {})["ai84_usd_per_1k_credits"] = 2.0
    usd, details = tts.voice_cost(ctx, {"model_id": "m"}, 14000, {"provider": "ai84", "credits": 900, "pieces": 3})
    assert usd == pytest.approx(1.8) and "unpriced" not in details


def test_serper_searches_are_written_down(ctx):
    costs.record_searches(ctx, "sourcing", "serper", 0)                 # none made: nothing written
    assert not (ctx.work_dir / "costs.json").exists()
    costs.record_searches(ctx, "sourcing", "serper", 37)
    entry = _entries(ctx)[-1]
    assert entry["provider"] == "serper" and entry["details"] == {"searches": 37, "unpriced": True}
    ctx.config.setdefault("budget", {})["serper_usd_per_search"] = 0.001
    costs.record_searches(ctx, "fallback", "serper", 10)
    assert _entries(ctx)[-1]["usd"] == pytest.approx(0.01)


def test_image_sources_count_their_paid_searches(tmp_path):
    from pipeline.sourcing.images import ImageSources

    source = ImageSources(root=tmp_path, cache_dir=tmp_path / "cache", config={}, serper_key="k")

    class Answer:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"images": []}

    source.session = SimpleNamespace(post=lambda *a, **k: Answer())
    source.pacers = {"web": SimpleNamespace(wait=lambda: None)}
    source._serper("q", 10)
    source._serper("q2", 10)
    assert source.serper_calls == 2


def test_the_studios_own_work_stops_at_the_daily_cap(ctx, tmp_path):
    (tmp_path / "out").mkdir(exist_ok=True)
    (tmp_path / "out" / "_ajustes.json").write_text(json.dumps({"daily_usd": 1.0}))
    radar = RunContext.create("_radar", root=tmp_path)
    radar.work_dir.mkdir(parents=True)
    budget.before_paid_call(radar)                                       # nothing spent yet: goes
    costs.record_cost(radar, stage="radar", provider="anthropic", operation="x", usd=1.5)
    with pytest.raises(budget.BudgetReached):
        budget.before_paid_call(radar)
    budget.before_paid_call(SimpleNamespace(slug="_sin_nada"))           # a context with no root: never breaks
