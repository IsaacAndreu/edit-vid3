"""The spend ledger (costs.json) and the YouTube quota ledger (quota.json) keep every entry when several processes
write at once (27-11: 1 600 quota units spent by four processes, 604-714 written down)."""

from __future__ import annotations

import json
import multiprocessing
from types import SimpleNamespace

import pytest

from pipeline.context import RunContext

WRITERS, EACH = 4, 40


def _spend(root):
    from pipeline.costs import record_cost

    ctx = RunContext.create("v1", root=root)
    for _ in range(EACH):
        record_cost(ctx, stage="judge", provider="openai", operation="x", usd=0.01)


def _ask(root):
    from pipeline import ytapi

    class Answer:
        status_code = 200
        text = ""

        def json(self):
            return {"items": []}

    ctx = RunContext.create("v1", root=root)
    ctx.env = lambda name, required=False: "clave-de-prueba" if name == "YOUTUBE_API_KEY" else ""
    api = ytapi.YouTubeAPI(ctx, session=SimpleNamespace(get=lambda *a, **k: Answer()))
    for n in range(EACH):
        api.get("videos", {"id": f"{root.name}-{multiprocessing.current_process().pid}-{n}"})   # never cached


def _together(target, root):
    context = multiprocessing.get_context("fork")
    workers = [context.Process(target=target, args=(root,)) for _ in range(WRITERS)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(60)
    assert all(w.exitcode == 0 for w in workers)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config.yaml").write_text("lab: {units_per_key: 1000000}\n")
    return tmp_path


def test_every_cost_is_kept_with_four_writers(root):
    _together(_spend, root)
    data = json.loads((root / "work" / "v1" / "costs.json").read_text())
    assert len(data["entries"]) == WRITERS * EACH
    assert data["totalUsd"] == pytest.approx(0.01 * WRITERS * EACH)


def test_every_quota_unit_is_kept_with_four_writers(root):
    from pipeline import ytapi

    _together(_ask, root)
    ledger = json.loads((root / "cache" / "ytapi" / "quota.json").read_text())
    assert sum(ledger["used"].values()) == WRITERS * EACH * ytapi.COST["videos"]
