from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline import fallback as F
from pipeline.context import RunContext
from pipeline.schemas import ShotsFile

from tests.test_judge import opt

BOARD = {"sheets": ["x.jpg"], "columns": 1, "rows": 1, "tileWidth": 1, "tileHeight": 1, "interval": 5, "frames": 1}


def _candidate(cid: str, title: str) -> dict:
    return {"id": cid, "source": "youtube", "kind": "video", "url": f"https://y/{cid}", "title": title, "channel": "C",
            "license": "l", "credit": "Fuente: C", "attribution": "a", "query": "q", "rankScore": 1,
            "durationSeconds": 100, "storyboard": BOARD}


class ProtagonistPoolTests(unittest.TestCase):
    def test_pool_holds_only_fragments_from_sources_naming_the_protagonist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext.create("t", root=Path(tmp), config={"judge": {"min_accept": 0.22}})
            for sid, cands, options in (
                ("s001", [_candidate("yt:a", "Carlos Yulo floor gold Paris 2024"), _candidate("yt:b", "Figure skating podium")],
                 [opt("yt:a", 0.40, start=10, end=12), opt("yt:b", 0.45, start=5, end=7)]),
                ("s003", [_candidate("yt:e", "Eldrew Yulo wins World Cup gold")], [opt("yt:e", 0.5, start=1, end=3)]),  # brother
                ("s002", [_candidate("yt:a", "Carlos Yulo floor gold Paris 2024")],
                 [opt("yt:a", 0.30, start=50, end=52), opt("yt:a", 0.10, start=80, end=82)]),   # 0.10 < min_accept
            ):
                ctx.write_json(f"candidates/{sid}.json", {"shotId": sid, "specHash": "h", "queries": {}, "candidates": cands})
                ctx.write_json(f"scores/{sid}.json", {"shotId": sid, "inputsHash": "h", "needed": 2.0, "prompts": ["p"],
                                                      "options": [o.model_dump(by_alias=True, exclude_none=True) for o in options]})
            ctx.write_json("candidates/_sourcing.json", {"shots": 2, "warnings": []})   # stage summary: ignored
            story = ShotsFile.model_construct(subject="Carlos Yulo · artistic gymnastics", title="T")
            pool, candidates = F.protagonist_pool(ctx, story)
        self.assertEqual([(o.candidateId, o.start) for o in pool], [("yt:a", 10), ("yt:a", 50)])
        self.assertEqual(set(candidates), {"yt:a"})


if __name__ == "__main__":
    unittest.main()


def test_library_photos_only_those_still_on_disk(tmp_path, monkeypatch):
    from pipeline import fallback, library
    from pipeline.context import RunContext

    ctx = RunContext.create("x", root=tmp_path, config={})
    (tmp_path / "cache" / "images").mkdir(parents=True)
    (tmp_path / "cache" / "images" / "a.jpg").write_bytes(b"x")
    photo = {"source": "wikimedia", "kind": "image", "url": "u", "title": "Carlos Yulo", "license": "CC BY",
             "credit": "Fuente: Wikimedia", "imagePath": "cache/images/a.jpg", "mediaUrl": "m", "query": "q",
             "channel": "Wikimedia", "attribution": "a", "rankScore": 0.5}
    monkeypatch.setattr(library, "load", lambda ctx, person: {"photos": {
        "wm:1": {**photo, "id": "wm:1"}, "wm:2": {**photo, "id": "wm:2", "imagePath": "cache/images/gone.jpg"}}})
    assert list(fallback.library_photos(ctx, "Carlos Yulo")) == ["wm:1"]
