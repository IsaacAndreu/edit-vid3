"""The screen measures tell the truth: the end screen is not part of the video, a card or a panel over a clip is
text (not a picture), a cold open with footage does not hide 30 s of boards after it, and every edited video is
measured on «Puntería», not only those the reviewer looked at."""

from __future__ import annotations

import json

from pipeline.revisor import screen_measures


def _shot(i, start, frames, media=None, cold=False):
    return {"id": f"s{i:03d}", "type": "broll", "from": start, "durationInFrames": frames, "text": "x",
            **({"media": {"src": media, "kind": "video", "source": "youtube"}} if media else {}),
            **({"coldOpen": True} if cold else {})}


def test_the_end_screen_is_not_in_the_total():
    timeline = {"fps": 30, "durationInFrames": 3000 + 600, "endscreenFrames": 600,
                "shots": [_shot(0, 0, 2700, "a.mp4"), _shot(1, 2700, 300)], "groups": []}
    assert screen_measures(timeline)["textShare"] == 10.0              # 300 of 3000, not of 3600


def test_a_card_over_a_clip_is_text_and_a_map_is_a_graphic():
    timeline = {"fps": 30, "durationInFrames": 3000,
                "shots": [_shot(0, 0, 3000, "a.mp4")],
                "groups": [{"id": "d", "kind": "datacard", "from": 0, "durationInFrames": 600},
                           {"id": "g", "kind": "graphic", "from": 600, "durationInFrames": 300,
                            "graphic": {"type": "map"}},
                           {"id": "punch-9", "kind": "graphic", "from": 900, "durationInFrames": 60,
                            "graphic": {"type": "kinetic", "lines": ["x"]}}]}
    got = screen_measures(timeline)
    assert got["textShare"] == 20.0 and got["graphicShare"] == 10.0   # the punch words over footage: a picture


def test_a_cold_open_does_not_hide_the_boards_after_it():
    timeline = {"fps": 30, "durationInFrames": 3600,
                "shots": [_shot(0, 0, 450, "open.mp4", cold=True), _shot(1, 450, 900), _shot(2, 1350, 2250, "a.mp4")],
                "groups": []}
    got = screen_measures(timeline)
    assert got["firstImage"] == 45.0                                   # after the 15 s open: 30 s of boards first
    assert got["textFirstMinute"] == 50.0                              # 30 of the first 60 s after the open


def test_a_broken_timeline_never_breaks_the_page():
    assert screen_measures({})["textShare"] == 0.0
    assert screen_measures({"shots": [{"id": "x"}], "groups": [None, {"kind": "datacard"}]})["textShare"] == 0.0


def test_every_edited_video_is_on_the_punteria_page(tmp_path):
    from pipeline import web
    from tests.test_web import SCRIPT, _project

    _project(tmp_path)
    web.create_video(tmp_path, {"name": "v1", "channel": "aviacion", "script": SCRIPT})
    (tmp_path / "work" / "v1").mkdir(parents=True)
    (tmp_path / "work" / "v1" / "timeline.json").write_text(json.dumps(
        {"fps": 30, "durationInFrames": 3000, "shots": [_shot(0, 0, 1500, "a.mp4"), _shot(1, 1500, 1500)], "groups": []}))
    page = web.punteria(tmp_path)
    videos = [v for c in page["channels"] for v in c["videos"]]
    assert [v["slug"] for v in videos] == ["v1"] and videos[0]["textShare"] == 50.0 and videos[0]["per100"] is None
