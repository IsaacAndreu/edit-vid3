"""Real-crime channels: a shot that names someone with no photo to compare does not show a stranger's big face."""

import numpy as np

from pipeline.identity import Checker


class Ctx:
    def __init__(self, cfg):
        from pathlib import Path

        self.cfg, self.work_dir = cfg, Path("/nonexistent")

    def section(self, name):
        return self.cfg if name == "fallback" else {}


def _checker(monkeypatch, cfg, faces):
    checker = Checker(Ctx(cfg), [{"name": "Aniceto Rodríguez"}])      # named, but no portrait was found
    monkeypatch.setattr(checker, "faces", lambda frame, **k: faces)
    return checker


def test_a_big_face_that_cannot_be_checked_goes_only_where_the_channel_asks(monkeypatch):
    frames = [np.zeros((1080, 1920, 3), np.uint8)] * 5
    big = [(None, 300, True)]                                            # a large frontal face in every frame
    assert _checker(monkeypatch, {}, big).face_verdict(frames, ["Aniceto Rodríguez"]) is None            # as before
    why = _checker(monkeypatch, {"unknown_faces": "reject"}, big).face_verdict(frames, ["Aniceto Rodríguez"])
    assert why and "Aniceto" in why
    small = [(None, 40, True)]                                           # far away: a place, a crowd — kept
    assert _checker(monkeypatch, {"unknown_faces": "reject"}, small).face_verdict(frames, ["Aniceto Rodríguez"]) is None
