"""When HLS fails for anything but a refusal (403, bot, login, 429) or a video gone, the range still comes: by byte
ranges, then whole. A refusal still goes up as before (the session's rotation handles it)."""

from __future__ import annotations

import pytest

from pipeline.sourcing.youtube import SourceUnavailable
from tests.test_hls_local import VIDEO, _info, _source


@pytest.fixture
def yt(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    source = _source(tmp_path, byte_ranges=True, whole_fallback=False)
    _info(source)
    monkeypatch.setattr(source, "_fresh_full_info", lambda video_id: source._full_info_path(video_id))
    return source


def _hls_fails(yt, monkeypatch, error):
    def hls(*args, **kwargs):
        raise error

    monkeypatch.setattr(yt, "_fetch_hls_locally", hls)
    ranged = []

    def byte_range(video_id, start, end, fmt, prefix, audio, audio_only, info_path):
        ranged.append(prefix)
        target = yt.cache_dir / "videos" / video_id / f"{prefix}_{start:.3f}_{end:.3f}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp4")
        return target

    monkeypatch.setattr(yt, "_fetch_byte_range", byte_range)
    return ranged


@pytest.mark.parametrize("error", [
    RuntimeError("yt-dlp download (HLS): el corte local falló: ffmpeg código 1"),
    RuntimeError("yt-dlp download (HLS): empty media playlist"),
    RuntimeError("yt-dlp download (HLS): HTTP Error 502: Bad Gateway"),
    RuntimeError("yt-dlp download (HLS): Read timed out"),
])
def test_an_hls_failure_that_is_not_a_refusal_falls_back_to_byte_ranges(yt, monkeypatch, error):
    ranged = _hls_fails(yt, monkeypatch, error)
    got = yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")
    assert got.read_bytes() == b"mp4" and ranged == ["hd"]
    assert "HLS falló" in str(yt._local.not_hls)


@pytest.mark.parametrize("error", [
    RuntimeError("yt-dlp download (HLS): HTTP Error 403: Forbidden"),
    RuntimeError("Sign in to confirm you're not a bot"),
    RuntimeError("yt-dlp download (HLS): HTTP Error 429: Too Many Requests"),
    SourceUnavailable("Video unavailable. This video has been removed"),
])
def test_a_refusal_or_a_video_gone_still_goes_up(yt, monkeypatch, error):
    ranged = _hls_fails(yt, monkeypatch, error)
    with pytest.raises(type(error)):
        yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")
    assert ranged == []
