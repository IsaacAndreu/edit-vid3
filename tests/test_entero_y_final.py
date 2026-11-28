"""A silent range («hd») is cut from the whole file already downloaded with sound («hdav») instead of downloading
the same video whole again; and a range that runs past the end of the video keeps the seconds it has."""

from __future__ import annotations

import json

from tests.test_hls_local import VIDEO, _source


def test_a_silent_range_reuses_the_whole_file_with_sound(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path)
    folder = yt.cache_dir / "videos" / VIDEO
    folder.mkdir(parents=True)
    (folder / "full_hdav.mp4").write_bytes(b"whole with sound")
    monkeypatch.setattr(yt, "_fresh_full_info", lambda video_id: (_ for _ in ()).throw(AssertionError("asked YouTube")))
    cut = []
    monkeypatch.setattr(yt, "_cut", lambda whole, video_id, start, end, prefix, audio: cut.append((whole.name, prefix, audio))
                        or folder / f"{prefix}_{start:.3f}_{end:.3f}.mp4")
    yt.download_range(VIDEO, 10.0, 14.0, fmt="bv*[height<=1080]", prefix="hd")
    assert cut == [("full_hdav.mp4", "hd", False)]


def test_a_range_past_the_end_keeps_the_seconds_the_video_has(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, whole_fallback=False)
    info = yt._full_info_path(VIDEO)
    info.parent.mkdir(parents=True, exist_ok=True)
    info.write_text(json.dumps({"id": VIDEO, "duration": 20.0, "formats": [
        {"format_id": "232", "protocol": "m3u8_native", "vcodec": "avc1", "height": 720, "url": "https://x/i.m3u8"}]}))
    monkeypatch.setattr(yt, "_fresh_full_info", lambda video_id: info)
    asked = []

    def hls(video_id, start, end, *rest):
        asked.append((start, end))
        target = yt.cache_dir / "videos" / video_id / f"hd_{start:.3f}_{end:.3f}.mp4"
        target.write_bytes(b"mp4")
        return target

    monkeypatch.setattr(yt, "_fetch_hls_locally", hls)
    got = yt.download_range(VIDEO, 17.5, 22.5, fmt="bv*[height<=1080]", prefix="hd")
    assert asked == [(17.5, 20.0)] and got.name == "hd_17.500_20.000.mp4"     # the 2.5 s there are, not refused
