"""After a session rotation (another exit IP) the byte ranges and the whole downloads take the new session's links,
never the old ones (a paid 403 for sure), and a 403 of old links never switches the whole downloads off."""

from __future__ import annotations

import pytest

from tests.test_hls_local import VIDEO, _info, _source


@pytest.fixture
def yt(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    return _source(tmp_path, byte_ranges=True)


def test_the_byte_range_after_a_failed_hls_takes_the_new_sessions_links(yt, monkeypatch):
    _info(yt)
    asked = []

    def fresh(video_id):
        asked.append(yt.sessions.session_id(yt._session_key()))
        return _info(yt)                                     # extracted for the live session

    monkeypatch.setattr(yt, "_fresh_full_info", fresh)

    def hls(*args, **kwargs):
        yt.sessions.rotate(yt._session_key())                # a bot answer moved this video to another IP…
        raise RuntimeError("yt-dlp download (HLS): el corte local falló")

    monkeypatch.setattr(yt, "_fetch_hls_locally", hls)
    used = []

    def byte_range(video_id, start, end, fmt, prefix, audio, audio_only, info_path):
        import json

        used.append(json.loads(info_path.read_text())["_edit_vid3_session"])
        target = yt.cache_dir / "videos" / video_id / f"{prefix}_{start:.3f}_{end:.3f}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp4")
        return target

    monkeypatch.setattr(yt, "_fetch_byte_range", byte_range)
    yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")
    assert len(asked) == 2 and asked[0] != asked[1]           # asked again after the rotation
    assert used == [asked[1]]                                 # …and the range read the new session's links


def test_a_403_of_old_links_does_not_switch_whole_downloads_off(yt, monkeypatch):
    path = _info(yt)
    monkeypatch.setattr(yt, "_fresh_full_info", lambda video_id: path)
    yt.cfg["byte_ranges"] = False
    yt.cfg["whole_fallback"] = True

    def hls(*args, **kwargs):
        raise RuntimeError("yt-dlp download (HLS): empty media playlist")

    def whole(video_id, fmt, prefix, info_path):
        yt.sessions.rotate(yt._session_key())                # the links went stale meanwhile
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(yt, "_fetch_hls_locally", hls)
    monkeypatch.setattr(yt, "_fetch_whole", whole)
    for _ in range(3):
        with pytest.raises(Exception):
            yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")
    assert getattr(yt, "_whole_403", 0) == 0
