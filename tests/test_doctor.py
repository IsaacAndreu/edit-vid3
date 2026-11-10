"""Render doctor (pipeline/doctor.py): black and frozen frames in the finished video, only where they are a fault."""

from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from pipeline import doctor

LOG = """[blackdetect @ 0x1] black_start:0 black_end:0.4 black_duration:0.4
[blackdetect @ 0x1] black_start:12.5 black_end:13.1 black_duration:0.6
[freezedetect @ 0x2] lavfi.freezedetect.freeze_start: 20.2
[freezedetect @ 0x2] lavfi.freezedetect.freeze_duration: 1.5
[freezedetect @ 0x2] lavfi.freezedetect.freeze_end: 21.7
[freezedetect @ 0x2] lavfi.freezedetect.freeze_start: 40.0
[freezedetect @ 0x2] lavfi.freezedetect.freeze_end: 42.0
"""


def _timeline():
    return {"durationInFrames": 60 * 30, "groups": [{"from": 1190, "durationInFrames": 90}],   # a graphic at 39.7-42.7 s
            "shots": [{"id": "s1", "type": "broll", "from": 0, "durationInFrames": 1800, "media": {"kind": "video"}}]}


def test_only_faults_count_not_the_fade_in_nor_a_graphic_holding_still():
    found = doctor.problems(_timeline(), doctor.parse(LOG), 30)
    assert [(p["kind"], p["from"], p["to"]) for p in found] == [("black", 375, 393), ("frozen", 606, 651)]


def test_a_short_clip_is_slowed_down_to_fill_its_shot_not_held():
    assert doctor.stretch_factor(3.0, 120, 0, 30) == pytest.approx(120 / 90)
    assert doctor.stretch_factor(5.0, 120, 0, 30) is None                 # it fills the shot
    segments = [SimpleNamespace(start=0, frames=600), SimpleNamespace(start=600, frames=60), SimpleNamespace(start=660, frames=900)]
    assert doctor.segments_hit(segments, {"from": 606, "to": 651}) == [1]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_a_black_flash_in_a_real_video_is_found(tmp_path):
    clip = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=duration=6:size=320x180:rate=30",
                    "-vf", "drawbox=enable='between(t,3,3.6)':color=black:t=fill", str(clip)], check=True)
    found = doctor.detect(clip)
    assert any(p["kind"] == "black" and 2.9 < p["start"] < 3.1 for p in found)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_the_doctor_fills_a_short_clip_with_slow_motion_instead_of_a_freeze(tmp_path):
    from pipeline.context import RunContext
    from pipeline.render import Renderer, Segment

    ctx = RunContext.create("t", root=tmp_path, config={"video": {"fps": 30, "width": 320, "height": 180}})
    (ctx.work_dir / "media").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=duration=1:size=320x180:rate=30",
                    str(ctx.work_dir / "media" / "a.mp4")], check=True)
    shot = {"id": "s001", "type": "broll", "from": 0, "durationInFrames": 60,
            "media": {"src": "media/a.mp4", "kind": "video", "width": 320, "height": 180}}
    segment = Segment("ffmpeg", 0, 60, [shot])
    held = Renderer(ctx).fast_segment(segment, None)
    assert any(p["kind"] == "frozen" for p in doctor.detect(held, {"freeze_seconds": 0.5}))
    slowed = Renderer(ctx).fast_segment(segment, None, stretch=2.0)
    assert not any(p["kind"] == "frozen" for p in doctor.detect(slowed, {"freeze_seconds": 0.5}))
