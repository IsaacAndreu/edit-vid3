"""ingest.detect_bars: borders baked into a source are removed before the cover-crop — black ones and, since
newideas (1:16, a white strip left on screen), white or light ones too."""

import shutil
import subprocess

import pytest

from pipeline.ingest import detect_bars

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")


def _clip(path, border):
    # a 640x360 frame: a moving 360x360 picture in the middle, the rest of the frame in `border`
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c={border}:s=640x360:d=2", "-f", "lavfi", "-i", "testsrc=s=360x360:d=2",
                    "-filter_complex", "[0][1]overlay=140:0", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_black_and_white_borders_are_both_found(tmp_path):
    for border in ("black", "white"):
        box = detect_bars(_clip(tmp_path / f"{border}.mp4", border))
        assert box is not None, border
        w, h, x, y = box
        assert 330 <= w <= 380 and h >= 340 and 120 <= x <= 160, (border, box)


def test_a_full_picture_has_no_borders(tmp_path):
    path = tmp_path / "full.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=640x360:d=2",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    assert detect_bars(path) is None
