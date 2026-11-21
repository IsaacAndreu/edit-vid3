"""fallback.repeat_frames: newgym3-ideas2 had 8 «Repetido» with nearly identical frames that the middle-frame check let
through (s088/s090, s174/s175…). Two frames per clip, compared like the revisor does."""

import inspect

import cv2
import numpy as np

from pipeline import fallback, revisor
from pipeline.analysis import detectors as det


def _clip(path, frames):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    for frame in frames:
        writer.write(frame)
    writer.release()


def _pattern(seed):
    rng = np.random.default_rng(seed)
    return cv2.resize(rng.integers(0, 255, (6, 8, 3), dtype=np.uint8), (64, 48), interpolation=cv2.INTER_NEAREST)


def test_two_clips_sharing_a_late_frame_are_a_repeat_though_their_middles_differ(tmp_path):
    a, b, c = _pattern(1), _pattern(2), _pattern(3)
    _clip(tmp_path / "x.mp4", [a] * 5 + [b] * 5)          # 30 %: a, 70 %: b
    _clip(tmp_path / "y.mp4", [c] * 6 + [b] * 4)          # 30 %: c, 70 %: b
    x, y = det.clip_dhashes(tmp_path / "x.mp4", "video"), det.clip_dhashes(tmp_path / "y.mp4", "video")
    assert len(x) == 2 and len(y) == 2
    assert det.near_frames(x, y)
    assert not det.near_frames(x[:1], y[:1])               # a then c: different
    _clip(tmp_path / "z.mp4", [_pattern(4)] * 10)
    assert not det.near_frames(x, det.clip_dhashes(tmp_path / "z.mp4", "video"))


def test_the_revisor_and_the_fallback_use_the_same_measure():
    assert revisor.dhash is det.dhash
    source = inspect.getsource(fallback)
    assert 'cfg.get("repeat_frames", False)' in source       # off: what it sends back is searched again
    assert source.count("frames_on_screen.extend(") == 3     # kept, claimed, and Pexels/generated items
