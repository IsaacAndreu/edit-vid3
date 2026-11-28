"""A clip whose sound or picture stops early is never published as good: each stream's own length counts (the
file's is the longest one's), a clip asked with sound must have it, and a download that got fewer bytes than the
server announced is asked again."""

from __future__ import annotations

import shutil
import subprocess

import pytest
import requests

from pipeline.fileio import media_problem

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")


def clip(path, video=4.5, audio=None):
    command = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=d={video}:s=160x120:r=25"]
    if audio is not None:
        command += ["-f", "lavfi", "-i", f"sine=d={audio}"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio is not None else []) + [str(path)]
    subprocess.run(command, check=True)
    return path


@needs_ffmpeg
def test_a_sound_that_stops_early_is_a_broken_clip(tmp_path):
    cut = clip(tmp_path / "corto.mp4", video=4.5, audio=2.55)
    problem = media_problem(cut, seconds=4.5, tolerance=0.9, audio=True)
    assert problem and "audio" in problem
    assert media_problem(clip(tmp_path / "bien.mp4", video=4.5, audio=4.5), seconds=4.5, tolerance=0.9, audio=True) is None


@needs_ffmpeg
def test_a_picture_that_stops_early_is_a_broken_clip_even_with_a_long_sound(tmp_path):
    cut = clip(tmp_path / "corto.mp4", video=2.0, audio=4.5)
    problem = media_problem(cut, seconds=4.5, tolerance=0.9)
    assert problem and "vídeo" in problem


@needs_ffmpeg
def test_a_clip_asked_with_sound_must_have_it(tmp_path):
    mute = clip(tmp_path / "mudo.mp4", video=4.5)
    assert "sin pista de audio" in media_problem(mute, seconds=4.5, audio=True)
    assert media_problem(mute, seconds=4.5) is None                     # asked silent: fine


class Short:
    """A 200 that announces 1 000 bytes and closes after 600, without an error (urllib3 1.x did not say)."""

    def __init__(self, size, sent):
        self.headers, self.status_code, self.reason = {"Content-Length": str(size)}, 200, "OK"
        self.sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, size):
        yield b"x" * self.sent

    def close(self):
        pass


def test_a_segment_shorter_than_announced_is_asked_again(tmp_path, monkeypatch):
    from tests.test_hls_local import PLAYLIST, VIDEO, FakeYdl, Got, _info, _source

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr("pipeline.fileio.media_problem", lambda *a, **k: None)
    monkeypatch.setattr("pipeline.sourcing.youtube.media_problem", lambda *a, **k: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    yt = _source(tmp_path, whole_fallback=False)
    _info(yt)
    monkeypatch.setattr(yt, "_ydl", lambda extra=None: FakeYdl(extra or {}))
    segments = []

    def get(url, headers=None, timeout=None, proxies=None, stream=False):
        name = url.rsplit("/", 1)[-1]
        if name in ("index.m3u8", "init.mp4"):
            return Got(PLAYLIST.encode() if name == "index.m3u8" else b"init")
        segments.append(url)
        return Short(1000, 600 if segments.count(url) == 1 else 1000)

    monkeypatch.setattr(yt._sessions[0], "get", get)

    def run(command, **kwargs):
        if command[0] == "ffmpeg":
            open(command[-1], "wb").write(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")
    assert len(segments) == 4 and len(set(segments)) == 2              # each segment twice: short, then whole


def test_a_range_shorter_than_its_content_range_is_asked_again(tmp_path, monkeypatch):
    from tests.test_hls_local import _source

    yt = _source(tmp_path)
    monkeypatch.setattr("time.sleep", lambda s: None)
    data = bytes(range(256)) * 8
    asked = []

    class Partial:
        status_code, reason = 206, "Partial Content"

        def __init__(self, first, last, sent):
            self.headers = {"Content-Type": "video/mp4", "Content-Range": f"bytes {first}-{last}/{len(data)}"}
            self.body = data[first:first + sent]

        def iter_content(self, size):
            yield self.body

        def close(self):
            pass

    def get(url, headers=None, timeout=None, proxies=None, stream=False):
        first, last = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        asked.append(first)
        return Partial(first, last, 500 if len(asked) == 1 else last - first + 1)

    monkeypatch.setattr(yt._sessions[0], "get", get)
    body, _, _ = yt._range_get(0, None, "https://x", {}, 0, len(data) - 1)
    assert body == data and asked == [0, 500]


def test_urllib3_is_pinned_to_2():
    from pathlib import Path

    assert any(line.startswith("urllib3>=2") for line in Path("requirements.txt").read_text().splitlines())
