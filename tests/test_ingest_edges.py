"""Burned-in text on the edges: kept by the analysis, cut off at ingest."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from pipeline import ingest
from pipeline.analysis import detectors as det


def box(y0, y1, w=1920, h=1080):
    return [[100, y0 * h], [800, y0 * h], [800, y1 * h], [100, y1 * h]]


def test_edges_only_when_all_text_is_on_the_edges():
    d = det.Detectors(cache_dir=Path(tempfile.mkdtemp()))
    frame = np.zeros((1080, 1920, 3), np.uint8)
    with patch.object(d, "text_boxes", return_value=[box(0.85, 0.93), box(0.03, 0.08)]):
        assert d.text_edges([frame]) == (0.095, 0.165)
    with patch.object(d, "text_boxes", return_value=[box(0.85, 0.93), box(0.45, 0.5)]):
        assert d.text_edges([frame]) is None                   # text over the middle: cropping cannot save it
    with patch.object(d, "text_boxes", return_value=[]):
        assert d.text_edges([frame]) == (0.0, 0.0)


def test_the_crop_filter_zooms_in_centred_and_still_gives_1080p():
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "a.mp4", Path(tmp) / "b.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "1",
                        "-pix_fmt", "yuv420p", str(src)], check=True)
        vf = ingest._frame_filter(src, 1920, 1080, 0.0, (0.05, 0.15))
        assert "crop=trunc(iw*0.8000/2)*2" in vf
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-frames:v", "1", str(out)], check=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                                "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
        assert probe == "1920,1080"
