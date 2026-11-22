"""«Qué hacer ahora» (part 4) and recommendations that learn (part 5)."""

import json
from datetime import datetime, timedelta, timezone

from pipeline import aprender, huecos, recomendar


def _root(tmp_path, rpm=""):
    (tmp_path / "config.yaml").write_text(f"radar: {{idiomas: [es, pt], dejar_videos: 3{rpm}}}\n")
    (tmp_path / "canales").mkdir()
    return tmp_path


def _gap(fit=8, examples=True, lang_row=None):
    row = lang_row or {"lang": "pt", "score": 7.5, "verdict": "hueco", "demand": 60_000, "recent": 4, "gap": 6.0, "smallWins": 2}
    return {"name": "Isla de las serpientes", "query_es": "isla serpientes", "fit": fit, "score": 5, "verdict": "a vigilar",
            "idiomas": {"date": "2026-11-22", "languages": {"pt": {"query": "ilha cobras", "suggestions": 8,
                                                                    "recentChannels": 2,
                                                                    "examples": [{"id": "x"}] if examples else []}},
                        "readings": {"start": [row]}}}


def test_start_shows_its_numbers_what_it_does_not_know_and_never_invents_income(tmp_path):
    root = _root(tmp_path)
    huecos._write(root, {"items": {"isla serpientes": _gap()}})
    entry = recomendar.start(root, {}, {})[0]
    assert entry["lang"] == "pt" and entry["score"] == 7.5 and entry["suggestions"] == 8
    assert entry["income"] is None and any("radar.rpm" in u for u in entry["unknown"])
    priced = recomendar.start(root, {"rpm": {"pt": {"default": 0.8}}}, {})[0]
    assert priced["income"] == 48.0 and not any("radar.rpm" in u for u in priced["unknown"])


def test_a_niche_the_tool_cannot_make_is_not_recommended(tmp_path):
    root = _root(tmp_path)
    huecos._write(root, {"items": {"a": _gap(fit=3), "b": {**_gap(examples=False), "name": "B", "query_es": "b"}}})
    assert recomendar.start(root, {}, {}) == []          # needs a face; no footage to take


def test_leave_when_the_last_videos_are_all_under_the_median_or_the_niche_filled_up(tmp_path):
    root = _root(tmp_path)
    (root / "canales" / "viejo.yaml").write_text("lab: {queries: [curiosidades]}\n")
    (root / "materiales" / "viejo" / "v1").mkdir(parents=True)
    (root / "materiales" / "viejo" / "config.yaml").write_text("canal: viejo\n")
    (root / "materiales" / "viejo" / "v1" / "guion.txt").write_text("x")
    (root / "out" / "v1").mkdir(parents=True)
    (root / "out" / "v1" / "video-final.mp4").write_bytes(b"x")
    (root / "out" / "_canal").mkdir(parents=True)
    videos = [{"ratio": 0.4, "short": False}, {"ratio": 0.8, "short": False}, {"ratio": 0.6, "short": False}]
    (root / "out" / "_canal" / "viejo.json").write_text(json.dumps({"videos": videos, "numbers": {"medianLong": 900}}))
    huecos._write(root, {"items": {"curiosidades": {"name": "c", "query_es": "curiosidades", "verdict": "saturado",
                                                    "history": [{"score": 6.1}, {"score": 2.0}]}}})
    rows = recomendar.leave(root, {"dejar_videos": 3})
    assert rows[0]["channel"] == "viejo" and len(rows[0]["reasons"]) == 2
    assert "0.8x" in rows[0]["reasons"][0] and "de 6.1 a 2.0" in rows[0]["reasons"][1]


def test_build_records_each_recommendation_once(tmp_path):
    root = _root(tmp_path)
    huecos._write(root, {"items": {"isla serpientes": _gap()}})
    (root / "out" / "_radar").mkdir(parents=True, exist_ok=True)
    (root / "out" / "_radar" / "doblar.json").write_text(json.dumps({"rows": [
        {"channel": "mapas", "lang": "de", "score": 7, "demand": 50_000, "readyCount": 3, "cost": 1.2}]}))
    page = recomendar.build(root)
    assert page["start"][0]["topic"] == "Isla de las serpientes" and page["dub"][0]["channel"] == "mapas"
    stored = aprender._read(root)["items"]
    assert set(stored) == {"empezar:isla de las serpientes:pt", "doblar:mapas:de"}
    recomendar.build(root)
    assert len(aprender._read(root)["items"]) == 2                                   # not recorded twice
