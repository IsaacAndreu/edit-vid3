"""«Que el clip sea…» 2: measure before touching — who picked each shot's clip, and where each shot came from."""

from __future__ import annotations

import json

from pipeline import origen


def _write(tmp_path, manifest, selections, items):
    work, out = tmp_path / "work" / "v", tmp_path / "out" / "v"
    work.mkdir(parents=True)
    out.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({"shots": manifest}))
    (work / "selection.json").write_text(json.dumps({"selections": selections}))
    (work / "fallback.json").write_text(json.dumps({"items": items}))
    return work, out


def test_the_origin_of_every_shot(tmp_path):
    manifest = [
        {"shotId": "s1", "media": "m/1.mp4", "decidedBy": "judge"},
        {"shotId": "s2", "media": "m/2.mp4", "decidedBy": "judge"},
        {"shotId": "s3", "media": "m/3.mp4", "decidedBy": "score"},
        {"shotId": "s4", "media": "m/4.mp4", "decidedBy": "fallback:next-option"},
        {"shotId": "s5", "media": "m/5.mp4", "decidedBy": "fallback:pexels-video"},
        {"shotId": "s6", "media": "m/6.jpg", "decidedBy": "fallback:protagonist-photo"},
        {"shotId": "s7"},
        {"shotId": "s8", "media": "m/1.mp4", "decidedBy": "heredado:s1"},
    ]
    selections = [
        {"shotId": "s1", "status": "selected", "judgeRank": 1, "pickedBy": "juez", "judge": {}},
        {"shotId": "s2", "status": "selected", "judgeRank": 2, "pickedBy": "variedad", "judge": {}, "thumbnailsOnly": True},
        {"shotId": "s3", "status": "selected", "pickedBy": "puntuación-por-error-del-juez"},
    ]
    items = [{"shotId": "s4", "judged": True}, {"shotId": "s5", "judged": False}, {"shotId": "s6", "judged": False}]
    work, out = _write(tmp_path, manifest, selections, items)
    data = origen.video(work, out)
    assert data["origin"] == {"primera elección del juez": 1, "otra opción juzgada": 1, "por puntuación (sin juez)": 1,
                              "relleno juzgado": 1, "relleno sin juzgar": 1, "foto": 1, "rótulo": 1, "heredado": 1}
    assert data["thumbnailsOnly"] == 1 and data["pickedBy"]["puntuación-por-error-del-juez"] == 1
    text = "\n".join(origen.lines(data))
    assert "De dónde salió cada plano" in text and "1 de 2 juzgados" in text
    table = "\n".join(origen.by_channel([{**data, "channel": "crimen"}]))
    assert "| crimen |" in table


def test_judge_records_rank_and_who_picked(monkeypatch):
    from pipeline.schemas import Selection

    s = Selection(shotId="s1", status="selected", decidedBy="judge", candidateId="yt:x", source="youtube", kind="video",
                  start=1.0, end=3.0, credit="Fuente: c", url="u", judgeRank=2, pickedBy="variedad")
    dumped = s.model_dump(exclude_none=True)
    assert dumped["judgeRank"] == 2 and dumped["pickedBy"] == "variedad"
    plain = Selection(shotId="s1", status="fallback", decidedBy="fallback").model_dump(exclude_none=True)
    assert "thumbnailsOnly" not in plain and "judgeRank" not in plain        # old hashes stay the same
