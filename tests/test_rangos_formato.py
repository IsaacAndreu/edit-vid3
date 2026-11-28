"""Byte ranges read only video-only DASH formats (the muxed 360p «18» has no index), and a format without an index
is remembered for that (video, format) — not for the whole video, whose HD formats still have theirs."""

from __future__ import annotations

import json

import pytest

from pipeline.sourcing.youtube import NoIndex, YouTubeSource

FORMATS = [
    {"format_id": "18", "ext": "mp4", "protocol": "https", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2",
     "height": 360, "width": 640, "fps": 30, "tbr": 500, "url": "https://x/18"},
    {"format_id": "134", "ext": "mp4", "protocol": "https", "vcodec": "avc1.4d401e", "acodec": "none",
     "height": 360, "width": 640, "fps": 30, "tbr": 300, "url": "https://x/134"},
    {"format_id": "136", "ext": "mp4", "protocol": "https", "vcodec": "avc1.4d401f", "acodec": "none",
     "height": 720, "width": 1280, "fps": 30, "tbr": 1500, "url": "https://x/136"},
    {"format_id": "140", "ext": "m4a", "protocol": "https", "vcodec": "none", "acodec": "mp4a.40.2", "tbr": 128,
     "url": "https://x/140"},
]


@pytest.fixture
def yt(tmp_path):
    source = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                      "byte_ranges": True, "whole_fallback": False})
    return source


def _info(tmp_path, formats=FORMATS):
    path = tmp_path / "info.json"
    path.write_text(json.dumps({"id": "abcdefghijk", "duration": 1200, "formats": formats,
                                "extractor": "youtube", "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk"}))
    return path


def test_the_360p_window_reads_the_video_only_format_not_the_muxed_one(yt, tmp_path):
    pieces = yt._range_formats(_info(tmp_path), yt.SECTION_FORMAT, audio=False, audio_only=False)
    assert [p["format_id"] for p in pieces] == ["134"]


def test_only_a_muxed_360p_left_is_no_index_not_a_wrong_pick(yt, tmp_path):
    only_muxed = [f for f in FORMATS if f["format_id"] in ("18", "140")]
    with pytest.raises(NoIndex):
        yt._range_formats(_info(tmp_path, only_muxed), yt.SECTION_FORMAT, audio=False, audio_only=False)


def test_a_format_without_index_does_not_close_the_ranges_of_the_others(yt, tmp_path, monkeypatch):
    tried = []

    def byte_range(video_id, start, end, fmt, prefix, audio, audio_only, info_path):
        tried.append(prefix)
        if prefix == "a360":
            raise NoIndex("sin índice")
        return tmp_path / f"{prefix}.mp4"

    monkeypatch.setattr(yt, "_fetch_byte_range", byte_range)
    assert yt._no_range_for("abcdefghijk", "a360") is False
    yt._mark_no_range("abcdefghijk", "a360")
    assert yt._no_range_for("abcdefghijk", "a360") is True
    assert yt._no_range_for("abcdefghijk", "hd") is False                   # its HD still goes by ranges
