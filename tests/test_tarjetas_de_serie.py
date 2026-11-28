"""By default no ordinary clip goes into a small framed card (27-11: card_share 0.25 put 48 of 200 clips in cards,
with 72 jumps between card and full screen). Photos and vertical clips still go framed, as always."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.schemas import TimelineMedia
from pipeline.timeline import choose_layout


def test_the_default_is_no_cards():
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    assert float(cfg["timeline"].get("card_share", 0)) == 0
    wide = TimelineMedia.model_validate({"src": "a.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X",
                                         "width": 1920, "height": 1080})
    layouts = [choose_layout(f"s{n:03d}", "broll", wide, 0.0) for n in range(200)]
    assert layouts.count("card") == 0
