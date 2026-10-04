"""Footage that has nothing to do with the script: cartoons and broken video."""

import numpy as np

from pipeline.content_check import ABOUT_ANIMATION, ContentCheck
from pipeline.context import RunContext


class FakeClip:
    def __init__(self, rows):
        self.rows = np.array(rows, dtype=np.float32)

    def embed_images(self, frames):
        return self.rows[: len(frames)]


def checker(tmp_path, rows):
    check = ContentCheck(RunContext.create("t", root=tmp_path, config={}))
    check._clip = FakeClip(rows)
    # axes: 0 cartoon, 1 real, 2 broken, 3 clear
    check._vectors = {name: np.eye(4, dtype=np.float32)[i] for i, name in enumerate(("cartoon", "real", "broken", "clear"))}
    return check


def test_one_broken_frame_rejects_the_clip_and_cartoons_need_two(tmp_path):
    frame = np.zeros((10, 10, 3), np.uint8)
    normal = [0.1, 0.3, 0.1, 0.3]
    assert checker(tmp_path, [normal] * 5).judge([frame] * 5) is None
    assert "dañado" in checker(tmp_path, [normal, [0, 0, 0.4, 0.2], normal]).judge([frame] * 3)
    assert checker(tmp_path, [[0.4, 0.3, 0, 0.3], normal, normal]).judge([frame] * 3) is None   # one doubtful frame
    assert "dibujo" in checker(tmp_path, [[0.4, 0.3, 0, 0.3]] * 3).judge([frame] * 3)
    assert checker(tmp_path, [[0.4, 0.3, 0, 0.3]] * 3).judge([frame] * 3, allow_cartoon=True) is None
    assert ABOUT_ANIMATION.search("Disney estrenó su primera película de animación")
