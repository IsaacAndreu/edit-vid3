"""«Que el clip sea…» 6: the judge never sees three copies of one thumbnail; its sheets can be judged again with
another model to compare the verdicts."""

from __future__ import annotations

import json

import cv2
import numpy as np

from pipeline import judge, rejuzgar
from pipeline.schemas import Candidate, Option


def _board(tmp_path):
    sheet = np.zeros((90, 160 * 10, 3), np.uint8)
    for i in range(10):
        sheet[:, i * 160:(i + 1) * 160] = (i * 25, 100, 200 - i * 20)    # every thumbnail its own colour
    cv2.imwrite(str(tmp_path / "sb.jpg"), sheet)
    return {"sheets": ["sb.jpg"], "columns": 10, "rows": 1, "tileWidth": 160, "tileHeight": 90, "interval": 10.0,
            "frames": 10}


def test_a_coarse_option_shows_three_different_thumbnails(tmp_path):
    c = Candidate.model_validate({"id": "yt:x", "source": "youtube", "kind": "video", "url": "u", "title": "t",
                                  "channel": "c", "license": "l", "credit": "Fuente: c", "attribution": "a", "query": "q",
                                  "rankScore": 0.1, "durationSeconds": 100, "storyboard": _board(tmp_path)})
    o = Option.model_validate({"candidateId": "yt:x", "source": "youtube", "kind": "video", "pass": "coarse",
                               "start": 41.0, "end": 44.0, "scores": {"clip": 0.3}, "total": 0.3})
    frames = judge._video_frames(o, c, tmp_path)
    means = [tuple(int(v) for v in f.mean(axis=(0, 1))) for f in frames]
    assert len(frames) == 3 and len(set(means)) == 3            # before: one 10 s thumbnail, three times
    sheet = judge.contact_sheet([o], {"yt:x": c}, tmp_path, frames=4, tile_width=400)
    assert sheet.shape[1] == 70 + 4 * 400


def test_rejudging_compares_first_choices():
    assert rejuzgar.compare({"ranking": ["A", "B"]}, {"ranking": ["A"]})["sameFirst"]
    assert rejuzgar.compare({"ranking": []}, {"ranking": ["B"]})["onlyNewAccepts"]
    text = rejuzgar.markdown({"slug": "v", "model": "m", "usd": 0.1, "rows": [
        {"sheet": "s001", "old": {"ranking": ["A"]}, "new": {"ranking": ["A"]}, **rejuzgar.compare({"ranking": ["A"]}, {"ranking": ["A"]})}]})
    assert "Misma primera elección: 100 %" in text


def test_the_sheet_context_is_saved(tmp_path):
    from pipeline.schemas import Shot

    shot = Shot.model_validate({"id": "s001", "type": "broll", "startWord": 0, "endWord": 1, "start": 0, "end": 2,
                                "text": "t", "chapter": 0, "broll": {"visualIntent": "a view", "queries": ["a", "b", "c"],
                                                                     "queriesLocal": ["d"]}})
    o = Option.model_validate({"candidateId": "yt:x", "source": "youtube", "kind": "video", "pass": "fine",
                               "start": 1.0, "end": 3.0, "scores": {"clip": 0.3}, "total": 0.3})
    judge._save_sheet_context(tmp_path / "s001.json", shot, [o], "A: youtube", "topic", "", True, {"ranking": ["A"]})
    saved = json.loads((tmp_path / "s001.json").read_text())
    assert saved["letters"] == "A" and saved["verdict"]["ranking"] == ["A"] and saved["hook"]
