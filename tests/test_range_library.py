"""Ranges capped at 720p/30fps and taken from the shared per-video library by (video, range, resolution)."""

import json

from pipeline.sourcing.youtube import YouTubeSource, cap_fps, cap_height, hls_format, requested_height, whole_format

VIDEO = "vid00000000"


def _source(tmp_path, **cfg):
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", **cfg})


def test_fps_cap_keeps_resolution_first_and_leaves_audio_alone():
    fmt = "bv*[height<=720][vcodec^=avc1]+ba/bv*[height<=720]/b[height<=720]"
    assert cap_fps(fmt, 30) == ("bv*[height<=720][vcodec^=avc1][fps<=30]+ba/bv*[height<=720][vcodec^=avc1]+ba/"
                                "bv*[height<=720][fps<=30]/bv*[height<=720]/b[height<=720][fps<=30]/b[height<=720]")
    assert cap_fps("ba[ext=m4a]/ba", 30) == "ba[ext=m4a]/ba"
    assert cap_fps(fmt, None) == fmt and cap_fps("bv*[fps<=60]", 30) == "bv*[fps<=60]"
    assert cap_height("bv*[height<=1080]+ba/b[height<=480]", 720) == "bv*[height<=720]+ba/b[height<=480]"
    assert requested_height("bv*[height<=720]/b[height<=480]") == 720 and requested_height("bv*") is None
    capped = cap_fps(cap_height("bv*[height<=1080]/b[height<=1080]", 720), 30)
    assert hls_format(capped).startswith("bv*[height<=720][fps<=30][protocol^=m3u8]/bv*[height<=720][protocol^=m3u8]")
    assert "[protocol=https]" in whole_format(capped)


def test_downloads_ask_for_720p30_and_the_sidecar_remembers_the_height(tmp_path, monkeypatch):
    yt = _source(tmp_path, whole_fallback=False)
    path = yt._full_info_path(VIDEO)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"formats": [{"protocol": "https", "vcodec": "avc1",
                                             "url": "https://x/videoplayback?expire=9999999999"}],
                                "_edit_vid3_clients": yt._clients(), "_edit_vid3_via": "", "_edit_vid3_session": None}))
    asked = []

    def fetch(video_id, start, end, fmt, prefix, audio, audio_only, info_path, *, exact):
        asked.append(fmt)
        target = tmp_path / "videos" / VIDEO / f"{prefix}_{start:.3f}_{end:.3f}.mp4"
        target.write_bytes(b"clip")
        yt._write_range_sidecar(target, height=720, cap=720)
        return target

    monkeypatch.setattr(yt, "_fetch_range", fetch)
    yt.download_range(VIDEO, 10, 15, fmt="bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/b[height<=1080]", prefix="hd")
    assert asked == ["bv*[height<=720][vcodec^=avc1][fps<=30]/bv*[height<=720][vcodec^=avc1]/bv*[height<=720][fps<=30]/"
                     "bv*[height<=720]/b[height<=720][fps<=30]/b[height<=720]"]
    assert yt._range_sidecar(tmp_path / "videos" / VIDEO / "hd_10.000_15.000.mp4") == {"height": 720, "cap": 720}
    yt.download_range(VIDEO, 11, 14, fmt="bv*[height<=1080]", prefix="hd")           # covered: nothing asked
    assert len(asked) == 1
    yt.download_range(VIDEO, 10, 15, fmt="bv*[height<=1080]", prefix="hd", audio_only=True)
    assert len(asked) == 2 and "fps" not in asked[1] and "height<=1080" in asked[1]   # audio: untouched


def test_the_library_serves_lower_requests_from_richer_ranges_but_never_a_short_one(tmp_path):
    yt = _source(tmp_path)
    folder = tmp_path / "videos" / VIDEO
    folder.mkdir(parents=True)
    hd = folder / "hd_10.000_15.000.mp4"
    hd.write_bytes(b"hd")
    yt._write_range_sidecar(hd, height=720, cap=720)
    assert yt._library_range(folder, "a360", ".mp4", 11, 14, 360) == hd           # analysis window from the HD range
    assert yt._library_range(folder, "hd", ".mp4", 11, 14, 720) == hd
    assert yt._library_range(folder, "hd", ".mp4", 11, 16, 720) is None            # not covered
    assert yt._library_range(folder, "hdav", ".mp4", 11, 14, 720) is None          # sound needed: a silent clip is no use
    low = folder / "hd_20.000_25.000.mp4"
    low.write_bytes(b"480")
    yt._write_range_sidecar(low, height=480, cap=480)
    assert yt._library_range(folder, "hd", ".mp4", 21, 24, 720) is None            # too short for a 720p request
    yt._write_range_sidecar(low, height=480, cap=720)
    assert yt._library_range(folder, "hd", ".mp4", 21, 24, 720) == low             # 480 is all that video has at a 720 cap
    legacy = folder / "hd_30.000_35.000.mp4"
    legacy.write_bytes(b"old")
    assert yt._library_range(folder, "hd", ".mp4", 31, 34, 720) == legacy          # no sidecar: as before
    hdav = folder / "hdav_40.000_45.000.mp4"
    hdav.write_bytes(b"av")
    yt._write_range_sidecar(hdav, height=1080, cap=1080)
    assert yt._library_range(folder, "hd", ".mp4", 41, 44, 720) == hdav            # a clip with sound serves a silent one
    assert yt._library_range(folder, "a360", ".mp4", 41, 44, 360) == hdav
