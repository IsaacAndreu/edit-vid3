"""A single 502 or a connection cut halfway never loses a clip: the HLS playlist, its init segment and the byte
ranges are asked again in the same session (only the bytes still missing), a refused link (403) never is."""

from __future__ import annotations

import subprocess

import pytest
import requests

from tests.test_hls_local import PLAYLIST, VIDEO, FakeYdl, Got, _info, _source

pytestmark = pytest.mark.usefixtures("fake_media_ok")


def _ffmpeg_writes(monkeypatch):
    def run(command, **kwargs):
        if command[0] == "ffmpeg":
            open(command[-1], "wb").write(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("time.sleep", lambda s: None)


def test_a_502_on_the_playlist_and_a_cut_on_the_init_segment_are_asked_again(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, whole_fallback=False)
    _info(yt)
    monkeypatch.setattr(yt, "_ydl", lambda extra=None: FakeYdl(extra or {}))
    seen = {"index.m3u8": 0, "init.mp4": 0}

    def get(url, headers=None, timeout=None, proxies=None, stream=False):
        name = url.rsplit("/", 1)[-1]
        if name in seen:
            seen[name] += 1
            if name == "index.m3u8" and seen[name] == 1:
                return Got(b"", status=502)                         # the proxy's tunnel, once
            if name == "init.mp4" and seen[name] == 1:
                raise requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead")
            return Got(PLAYLIST.encode() if name == "index.m3u8" else b"init")
        return Got(b"x" * 1000)

    monkeypatch.setattr(yt._sessions[0], "get", get)
    _ffmpeg_writes(monkeypatch)
    result = yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")
    assert result.read_bytes() == b"mp4" and seen == {"index.m3u8": 2, "init.mp4": 2}


def test_a_refused_playlist_is_not_asked_again_in_the_same_session(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, whole_fallback=False)
    _info(yt)
    monkeypatch.setattr(yt, "_ydl", lambda extra=None: FakeYdl(extra or {}))
    asked = []

    def get(url, headers=None, timeout=None, proxies=None, stream=False):
        asked.append(url)
        return Got(b"", status=403)

    monkeypatch.setattr(yt._sessions[0], "get", get)
    monkeypatch.setattr(yt, "_fresh_full_info", lambda video_id: _info(yt))
    _ffmpeg_writes(monkeypatch)
    with pytest.raises(Exception):
        yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")
    playlists = [u for u in asked if u.endswith("index.m3u8")]
    assert len(playlists) <= 2                                     # once, and once with fresh links: never retried


class Cut:
    """A 206 that sends part of its bytes and then the connection breaks."""

    def __init__(self, data, fail_after=None, status=206):
        self.data, self.fail_after, self.status_code = data, fail_after, status
        self.headers, self.reason = {"Content-Type": "video/mp4"}, "Partial Content"

    def iter_content(self, size):
        if self.fail_after is None:
            yield self.data
            return
        yield self.data[: self.fail_after]
        raise requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead")

    def close(self):
        pass


def test_a_range_cut_halfway_asks_only_for_the_missing_bytes(tmp_path, monkeypatch):
    yt = _source(tmp_path)
    monkeypatch.setattr("time.sleep", lambda s: None)
    data = bytes(range(256)) * 40                                   # 10 240 bytes
    asked = []

    def get(url, headers=None, timeout=None, proxies=None, stream=False):
        first, last = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        asked.append((first, last))
        if len(asked) == 1:
            return Cut(data[first:last + 1], fail_after=3000)
        if len(asked) == 2:
            return Cut(b"", status=502)
        return Cut(data[first:last + 1])

    monkeypatch.setattr(yt._sessions[0], "get", get)
    body, status, kind = yt._range_get(0, None, "https://x/videoplayback", {}, 1000, 10239)
    assert body == data[1000:10240] and status == 206
    assert asked == [(1000, 10239), (4000, 10239), (4000, 10239)]      # only what was missing, never from 1000 again


def test_a_range_that_keeps_failing_gives_up_after_its_retries(tmp_path, monkeypatch):
    yt = _source(tmp_path)
    monkeypatch.setattr("time.sleep", lambda s: None)
    asked = []

    def get(url, headers=None, timeout=None, proxies=None, stream=False):
        asked.append(headers["Range"])
        raise requests.exceptions.ConnectionError("tunnel down")

    monkeypatch.setattr(yt._sessions[0], "get", get)
    with pytest.raises(Exception):
        yt._range_get(0, None, "https://x/videoplayback", {}, 0, 99)
    assert len(asked) == 3                                           # the first try and two more
