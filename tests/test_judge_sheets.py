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


def test_rejudging_only_some_shots(tmp_path, monkeypatch):
    """Bloque 0.4: `rejuzgar <vídeo> <modelo> s065,s127` re-asks only those shots' sheets and says which have none."""

    from pipeline.context import RunContext
    from pipeline.schemas import Shot

    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path)
    shots = [Shot.model_validate({"id": f"s{n:03d}", "type": "broll", "startWord": 2 * i, "endWord": 2 * i + 1,
                                  "start": 2.0 * i, "end": 2.0 * i + 2, "text": "t", "chapter": 0,
                                  "broll": {"visualIntent": "a view", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}})
             for i, n in enumerate((65, 66, 127))]
    ctx.write_json("shots.json", {"slug": "v", "title": "t", "durationSeconds": 6, "chapters": [],
                                  "shots": [s.model_dump(exclude_none=True) for s in shots]})
    folder = ctx.work_dir / "judge"
    folder.mkdir(parents=True)
    for sid in ("s065", "s066", "s127"):
        cv2.imwrite(str(folder / f"{sid}.jpg"), np.zeros((20, 20, 3), np.uint8))
        (folder / f"{sid}.json").write_text(json.dumps({"shotId": sid, "letters": "A", "verdict": {"ranking": ["A"]}}))
    asked = []
    monkeypatch.setattr(judge, "call_judge", lambda ctx, shot, *a, **k: asked.append(shot.id) or {"ranking": [], "reason": "otra gimnasta"})
    result = rejuzgar.run(tmp_path, "v", "gpt-5-mini", only={"s065", "s127", "s074"})
    assert asked == ["s065", "s127"] and result["missing"] == ["s074"]
    text = rejuzgar.markdown(result)
    assert "otra gimnasta" in text and "s074" in text
