"""Ranges come over HLS (small segment requests, exact cut); the throttled HTTPS path is the fallback."""

import json
import time

from pipeline.sourcing.youtube import YouTubeSource, _has_hls, hls_format


def _source(tmp_path, **cfg):
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, **cfg})


def _info(tmp_path, source, formats, clients=None):
    path = source._full_info_path("vid00000000")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"formats": formats, "_edit_vid3_clients": clients if clients is not None else source._clients()}))
    return path


LATER = int(time.time()) + 6 * 3600
HLS = {"protocol": "m3u8_native", "vcodec": "avc1", "url": f"https://manifest.googlevideo.com/api/manifest/hls_playlist/expire/{LATER}/ei/x"}
HTTPS = {"protocol": "https", "vcodec": "avc1", "url": f"https://rr1.googlevideo.com/videoplayback?expire={LATER}&id=x"}


def test_hls_first_then_https_when_there_is_none(tmp_path, monkeypatch):
    source = _source(tmp_path, player_client=["default", "web_safari"])
    _info(tmp_path, source, [HLS, HTTPS])
    calls = []

    def fetch(video_id, start, end, fmt, prefix, audio, audio_only, info_path, *, exact):
        calls.append((fmt, exact))
        if exact:
            raise RuntimeError("yt-dlp download: ERROR: [youtube] x: Requested format is not available")
        return tmp_path / "ok.mp4"

    monkeypatch.setattr(source, "_fetch_range", fetch)
    assert source.download_range("vid00000000", 10, 15, fmt="bv*[height<=1080]", prefix="hd").name == "ok.mp4"
    assert calls == [("bv*[height<=1080][protocol^=m3u8]", True), ("bv*[height<=1080]", False)]


def test_no_hls_in_the_info_goes_straight_to_https(tmp_path, monkeypatch):
    source = _source(tmp_path)
    _info(tmp_path, source, [HTTPS])
    seen = []
    monkeypatch.setattr(source, "_fetch_range", lambda *a, exact: seen.append(exact) or tmp_path / "x.mp4")
    source.download_range("vid00000000", 10, 15, fmt="bv*", prefix="hd")
    assert seen == [False] and not _has_hls(source._full_info_path("vid00000000"))


def test_hls_manifests_do_not_look_expired(tmp_path, monkeypatch):
    source = _source(tmp_path, player_client=["default", "web_safari"])
    path = _info(tmp_path, source, [HLS])
    monkeypatch.setattr(source, "info", lambda vid: (_ for _ in ()).throw(AssertionError("re-extracted")))
    assert source._fresh_full_info("vid00000000") == path


def test_info_from_other_clients_is_extracted_again(tmp_path, monkeypatch):
    source = _source(tmp_path, player_client=["default", "web_safari"])
    _info(tmp_path, source, [HTTPS], clients=[])
    extracted = []
    monkeypatch.setattr(source, "info", lambda vid: extracted.append(vid))
    source._fresh_full_info("vid00000000")
    assert extracted == ["vid00000000"]


def test_hls_format_strings():
    assert hls_format("bv*[height<=1080]+ba/b[height<=1080]", audio=True).startswith("b[height<=1080][protocol^=m3u8][acodec!=none]")
    assert hls_format("ba", audio_only=True) == "worst[protocol^=m3u8][acodec!=none]"
