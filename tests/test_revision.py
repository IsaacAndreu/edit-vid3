"""pipeline/revision.py and pipeline/informe_planos.py: the final look at every shot and the per-shot report."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from pipeline import informe_planos, revision
from pipeline.context import RunContext


def rows():
    frame = np.full((360, 640, 3), 90, np.uint8)
    return [
        {"shotId": "s000", "start": 0.0, "end": 2.0, "text": "Rita Isbell se lanzó", "media": "a.mp4", "source": "youtube",
         "decidedBy": "judge", "judge": {"score": 0.8, "confidence": 0.9, "reason": "the hearing"}, "master": True,
         "url": "https://www.youtube.com/watch?v=x", "sourceStart": 12.5, "title": "Hearing", "channel": "MLive", "_frame": frame},
        {"shotId": "s001", "start": 2.0, "end": 4.0, "text": "La jueza habló", "media": "b.mp4", "source": "youtube",
         "decidedBy": "score", "score": 0.4, "_frame": frame},
        {"shotId": "s002", "start": 4.0, "end": 6.0, "text": "Su foto", "media": "p.png", "decidedBy": "people", "_frame": frame},
    ]


def test_flagged_shots_come_back_with_their_reason_and_the_report_shows_them():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = RunContext.create("t", root=Path(tmp), config={"qa": {"review_batch": 9}})
        data = rows()
        seen = {}

        def fake(ctx, prompt, images):
            seen["prompt"], seen["images"] = prompt, [label for label, _ in images]
            return {"problems": [{"n": 2, "kind": "persona", "reason": "a man, not the judge"}, {"n": 7, "kind": "tema", "reason": "x"}]}

        with patch.object(revision, "ask", side_effect=fake), patch.object(ctx, "env", return_value="key"):
            problems = revision.review(ctx, data)
        assert problems == [{"shotId": "s001", "start": 2.0, "kind": "persona", "reason": "a man, not the judge"}]
        assert "1. «Rita Isbell se lanzó»" in seen["prompt"] and "Su foto" not in seen["prompt"]   # person cards: not reviewed
        (ctx.out_dir / "qa").mkdir(parents=True)
        page = informe_planos.write(ctx.out_dir / "qa" / "planos.html", "t", data).read_text()
        assert "vídeo maestro" in page and "t=12" in page and "Otra persona" in page and "1 a revisar" in page
        assert "Otra persona" in revision.write(ctx, problems, 3).read_text()


def test_without_a_key_nothing_is_asked():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = RunContext.create("t", root=Path(tmp), config={})
        with patch.object(ctx, "env", return_value=""), patch.object(revision, "ask") as ask:
            assert revision.review(ctx, rows()) == []
        ask.assert_not_called()
