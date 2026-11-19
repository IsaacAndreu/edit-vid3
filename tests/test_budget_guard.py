"""Fase 2.6: the spend caps are checked inside the judge and the fallback, before each paid call — not only between
stages."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from pipeline import budget
from pipeline import judge as J
from pipeline.context import RunContext
import tests.test_judge as judge_tests      # not `from … import RunTests`: pytest would collect it twice


def test_the_per_video_cap_counts_this_attempt_only(tmp_path):
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={"budget": {"per_video_usd": 1.0}})
    ctx.work_dir.mkdir(parents=True)
    (ctx.work_dir / "costs.json").write_text(json.dumps({"totalUsd": 5.0}))
    budget.ATTEMPT_START[str(ctx.work_dir)] = 4.5             # this attempt: 0.5 $ so far
    budget.guard(ctx)
    (ctx.work_dir / "costs.json").write_text(json.dumps({"totalUsd": 5.6}))
    with pytest.raises(budget.VideoOverBudget):
        budget.guard(ctx)


def test_the_judge_stops_at_the_cap_instead_of_swallowing_it_as_one_shots_error():
    broll = {"visualIntent": "roulette", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}
    shots = [{"id": "s000", "type": "broll", "startWord": 0, "endWord": 0, "start": 0.0, "end": 2.0,
              "text": "t", "chapter": 0, "broll": broll}]
    board = {"sheets": ["x.jpg"], "columns": 1, "rows": 1, "tileWidth": 1, "tileHeight": 1, "interval": 5, "frames": 1}
    video = {"id": "yt:a", "source": "youtube", "kind": "video", "url": "https://y/a", "title": "t", "channel": "A",
             "license": "l", "credit": "Fuente: A", "attribution": "a", "query": "q", "rankScore": 1,
             "durationSeconds": 500, "storyboard": board}
    helper = judge_tests.RunTests()
    with tempfile.TemporaryDirectory() as tmp:
        ctx = helper._write(Path(tmp), shots, {"s000": [video]}, {"s000": [judge_tests.opt("yt:a", 0.40, start=10, end=12)]}, hook=100)

        def over(ctx):
            raise budget.BudgetReached("Límite diario de gasto alcanzado")

        with patch.object(budget, "guard", side_effect=over), \
                patch.object(J, "contact_sheet", return_value=np.zeros((10, 10, 3), "uint8")):
            with pytest.raises(budget.BudgetReached):
                J.run(ctx)
        assert not (ctx.work_dir / "selection.json").exists()
