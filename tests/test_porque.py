"""«Por qué funcionó» (pipeline/porque.py): the views of each uploaded video at fixed ages, against the channel's
other videos at the same age, and the lessons that go into the next scripts."""

from __future__ import annotations

import json

from pipeline import porque

HOUR = 3600


class FakeAPI:
    def __init__(self, views, published):
        self.views, self.published, self.calls = views, published, 0

    def videos(self, ids):
        self.calls += 1
        return [{"id": i, "views": self.views[i], "published": self.published, "title": f"t-{i}", "duration": 600} for i in ids]


def test_the_curve_is_recorded_at_each_checkpoint_once(tmp_path, monkeypatch):
    from pipeline import agenda

    monkeypatch.setattr(agenda, "videos", lambda root: [{"slug": "v1", "channel": "c", "status": "subido",
                                                         "url": "https://youtu.be/AAAAAAAAAAA"}])
    published = "2026-10-01T10:00:00Z"
    start = porque._ts(published)
    api = FakeAPI({"AAAAAAAAAAA": 100}, published)
    assert porque.snapshot(tmp_path, start + 2 * HOUR, api) == []
    api.views["AAAAAAAAAAA"] = 900
    assert porque.snapshot(tmp_path, start + 50 * HOUR, api) == ["v1"]          # passed 48 h: analyse it
    calls = api.calls
    assert porque.snapshot(tmp_path, start + 51 * HOUR, api) == [] and api.calls == calls   # nothing due: no API call
    curves = json.loads((tmp_path / porque.CURVES).read_text())
    assert curves["v1"]["points"] == [[2.0, 100], [50.0, 900]] and 48 in curves["v1"]["done"]


def test_a_video_against_its_channels_normal_at_the_same_age():
    curves = {"a": {"channel": "c", "points": [[24, 1000], [48, 2000]]},
              "b": {"channel": "c", "points": [[24, 3000], [48, 4000]]},
              "z": {"channel": "other", "points": [[48, 99999]]},
              "new": {"channel": "c", "points": [[48, 6000]]}}
    c = porque.compare(curves, "new")
    assert c["usual"] == 3000 and c["ratio"] == 2.0
    assert [b["hours"] for b in c["normal"]] == [1, 3, 6, 12, 24, 48]
    assert porque.views_at([[24, 1000], [48, 2000]], 36) == 1500


def test_only_clear_results_teach_and_they_reach_the_next_script(tmp_path):
    folder = tmp_path / porque.FOLDER
    folder.mkdir(parents=True)
    for slug, verdict, ratio, lesson in (("hit", "funcionó", 2.7, "repite el desierto"), ("meh", "normal", 1.0, "nada"),
                                         ("flop", "no funcionó", 0.4, "evita títulos de 12 palabras")):
        (folder / f"{slug}.json").write_text(json.dumps({"slug": slug, "channel": "c", "verdict": verdict, "ratio": ratio,
                                                          "lesson": lesson, "at": "2026-10-20"}))
    assert porque.lessons(tmp_path, "c") == ["✓ «hit» (2.7x): repite el desierto", "✗ «flop» (0.4x): evita títulos de 12 palabras"]
