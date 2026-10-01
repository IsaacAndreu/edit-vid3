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
    source = _source(tmp_path, player_client=["default", "web_safari"], whole_fallback=False)
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
    source = _source(tmp_path, whole_fallback=False)
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


class _FakeYdl:
    downloads = 0

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def process_ie_result(self, data, download=False):
        return {**data["formats"][0], "requested_formats": None}

    def download_with_info_file(self, info_file):
        import subprocess

        _FakeYdl.downloads += 1
        out = self.options["outtmpl"].replace("%(ext)s", "mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=20",
                        "-pix_fmt", "yuv420p", out], check=True)


def test_without_hls_the_whole_video_comes_in_pieces_once_and_is_cut(tmp_path, monkeypatch):
    import subprocess

    source = _source(tmp_path)
    path = _info(tmp_path, source, [{**HTTPS, "filesize": 5_000_000}])
    data = json.loads(path.read_text())
    path.write_text(json.dumps({**data, "duration": 20}))
    monkeypatch.setattr(source, "_ydl", lambda extra=None: _FakeYdl(extra or {}))
    monkeypatch.setattr(source, "_fetch_range", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ranged")))
    first = source.download_range("vid00000000", 5, 8, fmt="bv*", prefix="hd")
    second = source.download_range("vid00000000", 12, 14, fmt="bv*", prefix="hd")
    assert _FakeYdl.downloads == 1 and first.name == "hd_5.000_8.000.mp4" and second.name == "hd_12.000_14.000.mp4"
    length = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(first)],
                            capture_output=True, text=True).stdout
    assert abs(float(length) - 3) < 0.1
    assert source.stats["download (completo)"][0] == 1


def test_long_videos_keep_the_ranged_download(tmp_path, monkeypatch):
    source = _source(tmp_path, whole_max_minutes=10)
    path = _info(tmp_path, source, [HTTPS])
    path.write_text(json.dumps({**json.loads(path.read_text()), "duration": 3600}))
    seen = []
    monkeypatch.setattr(source, "_fetch_range", lambda *a, exact: seen.append(exact) or tmp_path / "x.mp4")
    source.download_range("vid00000000", 10, 15, fmt="bv*", prefix="hd")
    assert seen == [False]
