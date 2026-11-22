"""The local HLS cut (sourcing.youtube._fetch_hls_locally): YouTube's segments keep the source's timestamps (832 s…)
and carry one keyframe each. Through a local m3u8 ffmpeg's HLS demuxer seeked wrong — clips came out with no picture
or 1.3 s of 3.7 (escapadapolicial: 242 such failures). Joined into one file and cut with an input seek, they don't."""

import shutil
import subprocess

import pytest

from pipeline.fileio import media_problem
from pipeline.sourcing.youtube import join_segments, local_cut_command

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")


def _segments(folder, offset, gop_seconds=6.0, total=12.0):
    """Two ~6 s MPEG-TS segments of a 30 fps test picture whose timestamps start at `offset` s, one keyframe each."""

    source = folder / "src.ts"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc=s=320x180:r=30:d={total}", "-c:v", "libx264", "-g", str(int(gop_seconds * 30)),
                    "-keyint_min", str(int(gop_seconds * 30)), "-sc_threshold", "0", "-output_ts_offset", str(offset),
                    "-f", "mpegts", str(source)], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-copyts", "-i", str(source), "-c", "copy",
                    "-f", "segment", "-segment_time", str(gop_seconds), "-segment_format", "mpegts",
                    str(folder / "seg_%d.ts")], check=True)
    return sorted(folder.glob("seg_*.ts"))


def _start(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=start_time", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True).stdout)


@pytest.mark.parametrize("offset,into,length", [(832.165, 4.575, 3.43), (125.259, 1.81, 3.68), (125.259, 0.2, 9.0)])
def test_a_range_across_segments_that_keep_the_source_timestamps_comes_out_whole(tmp_path, offset, into, length):
    paths = _segments(tmp_path, offset)
    first = _start(paths[0])                      # where the playlist says the first segment begins
    joined = join_segments(paths, None, tmp_path / "joined.ts")
    part = tmp_path / "cut.mp4"
    subprocess.run(local_cut_command([(first, joined)], first + into, first + into + length, "hd", False, False, part),
                   check=True)
    assert media_problem(part, video=True, seconds=length, tolerance=0.2) is None
    assert _start(part) < 0.1                     # the picture from the first frame, not from the next keyframe


def test_the_sound_track_is_lined_up_by_its_own_start():
    command = local_cut_command([(100.0, "v.ts"), (99.5, "a.ts")], 103.0, 106.0, "hdav", True, False, "out.mp4")
    assert command[command.index("v.ts") + 1:command.index("v.ts") + 3] == ["-itsoffset", "-0.500"]
    assert command[command.index("-ss") + 1] == "3.000" and command.index("-ss") > command.index("a.ts")
