"""Through a residential proxy the HLS segments of a range are fetched in-process (the proxy authenticates, the
sticky session keeps the IP) and ffmpeg only cuts local files: it cannot authenticate against the proxy itself."""

import json
import subprocess

import pytest

from pipeline.sourcing.youtube import YouTubeSource, parse_media_playlist

RESI = "http://user:pass@resi-bridge-eu.rainproxy.io:1111"
VIDEO = "dQw4w9WgXcQ"
PLAYLIST = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-MAP:URI="init.mp4"
#EXTINF:5.005,
https://rr1.googlevideo.com/videoplayback/sq/0/file/seg.ts
#EXTINF:5.005,
https://rr1.googlevideo.com/videoplayback/sq/1/file/seg.ts
#EXTINF:5.005,
https://rr1.googlevideo.com/videoplayback/sq/2/file/seg.ts
#EXTINF:5.005,
https://rr1.googlevideo.com/videoplayback/sq/3/file/seg.ts
#EXT-X-ENDLIST
"""


def test_media_playlists_are_parsed_with_times_and_init_segment():
    segments, init = parse_media_playlist(PLAYLIST, "https://manifest.googlevideo.com/api/manifest/hls_playlist/x/index.m3u8")
    assert init == "https://manifest.googlevideo.com/api/manifest/hls_playlist/x/init.mp4"
    assert [(a, round(b, 3), round(c, 3)) for a, b, c in segments][:2] == [
        ("https://rr1.googlevideo.com/videoplayback/sq/0/file/seg.ts", 0.0, 5.005),
        ("https://rr1.googlevideo.com/videoplayback/sq/1/file/seg.ts", 5.005, 10.01)]
    assert parse_media_playlist("#EXTM3U\n#EXT-X-ENDLIST\n") == ([], None)


def _source(tmp_path, **cfg):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", "proxy": RESI, **cfg})
    yt.metrics_path = tmp_path / "work" / "v" / "youtube_downloads.jsonl"
    return yt


def _info(yt):
    path = yt._full_info_path(VIDEO)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": VIDEO, "duration": 20, "formats": [
        {"format_id": "232", "protocol": "m3u8_native", "vcodec": "avc1", "height": 720, "fps": 30,
         "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/expire/9999999999/x/index.m3u8",
         "http_headers": {"User-Agent": "UA"}}],
        "_edit_vid3_clients": yt._clients(), "_edit_vid3_via": "", "_edit_vid3_session": yt.sessions.session_id(VIDEO)}))
    return path


class FakeYdl:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def process_ie_result(self, data, download):
        if "m3u8" not in self.options.get("format", ""):
            raise RuntimeError("Requested format is not available")
        return {**data, **data["formats"][0]}


class Got:
    def __init__(self, content, status=200):
        self.content, self.status_code, self.reason = content, status, "OK" if status == 200 else "Forbidden"


def test_segments_come_in_process_through_the_session_and_ffmpeg_cuts_locally(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, whole_fallback=False)
    _info(yt)
    monkeypatch.setattr(yt, "_ydl", lambda extra=None: FakeYdl(extra or {}))
    fetched = []

    def get(url, headers=None, timeout=None, proxies=None):
        fetched.append((url, headers, proxies))
        if url.endswith("index.m3u8"):
            return Got(PLAYLIST.encode())
        return Got(b"x" * 1000)

    monkeypatch.setattr(yt._sessions[0], "get", get)
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if command[0] == "ffmpeg":
            target = command[-1]
            open(target, "wb").write(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    result = yt.download_range(VIDEO, 7.0, 11.0, fmt="bv*[height<=1080]", prefix="hd")

    assert result.name == "hd_7.000_11.000.mp4" and result.read_bytes() == b"mp4"
    urls = [u.rsplit("/", 3)[-3] if "/sq/" in u else u.rsplit("/", 1)[-1] for u, _, _ in fetched]
    assert urls == ["index.m3u8", "init.mp4", "1", "2"]                   # the playlist, the init, segments 5-10 and 10-15 s only
    sticky = fetched[0][2]["https"]
    assert "-time-30-session-" in sticky and all(p["https"] == sticky for _, _, p in fetched)   # one IP, the video's
    assert all(h == {"User-Agent": "UA"} for _, h, _ in fetched)
    ffmpeg, kwargs = commands[-1]
    assert ffmpeg[0] == "ffmpeg" and "-http_proxy" not in ffmpeg and "http" not in " ".join(ffmpeg)   # local files only
    assert ffmpeg[ffmpeg.index("-ss") + 1] == "1.995" and ffmpeg[ffmpeg.index("-t") + 1] == "4.000"   # 7.0 s is 1.995 s into segment 1
    assert ffmpeg[ffmpeg.index("-i") + 1].endswith("local.m3u8") and "libx264" in ffmpeg and "-an" in ffmpeg
    assert "HTTPS_PROXY" not in kwargs["env"] and "http_proxy" not in kwargs["env"]
    assert not (tmp_path / "videos" / VIDEO / "hls_hd_7.00_11.00").exists()          # temporary segments gone
    assert yt._range_sidecar(result) == {"height": 720, "cap": 720}
    rows = [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]
    download = next(r for r in rows if r["action"] == "download (HLS)")
    assert download["ok"] and download["proxy_bytes"] == len(PLAYLIST.encode()) + 3000 and download["session"]
    assert rows[-1]["action"] == "archivo hd" and rows[-1]["ok"] and rows[-1]["bytes"] == 3
    yt.close()


def test_a_403_on_a_segment_refreshes_the_links_once(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, whole_fallback=False)
    _info(yt)
    monkeypatch.setattr(yt, "_ydl", lambda extra=None: FakeYdl(extra or {}))
    calls = {"n": 0}
    refreshed = []

    def get(url, headers=None, timeout=None, proxies=None):
        calls["n"] += 1
        if url.endswith("index.m3u8"):
            return Got(PLAYLIST.encode())
        return Got(b"", 403) if not refreshed else Got(b"ok")

    monkeypatch.setattr(yt._sessions[0], "get", get)
    monkeypatch.setattr(yt, "info", lambda vid: refreshed.append(vid) or _info(yt))
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: (open(command[-1], "wb").write(b"m"), subprocess.CompletedProcess(command, 0, "", ""))[1])
    yt.download_range(VIDEO, 1.0, 3.0, fmt="bv*[height<=720]", prefix="hd")
    assert refreshed == [VIDEO]                                               # one new extraction, then it worked
    rows = [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]
    assert [r["ok"] for r in rows if r["action"] == "download (HLS)"] == [False, True]
    assert "HTTP Error 403" in rows[0]["detail"]
    yt.close()


def test_without_an_hls_stream_the_other_paths_are_tried(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, whole_fallback=False)
    _info(yt)

    class NoHls(FakeYdl):
        def process_ie_result(self, data, download):
            raise RuntimeError("ERROR: [youtube] x: Requested format is not available")

    monkeypatch.setattr(yt, "_ydl", lambda extra=None: NoHls(extra or {}))
    seen = []
    monkeypatch.setattr(yt, "_fetch_range", lambda *a, exact: seen.append(exact) or (tmp_path / "x.mp4"))
    yt.download_range(VIDEO, 1.0, 3.0, fmt="bv*[height<=720]", prefix="hd")
    assert seen == [False]                                                    # straight to the HTTPS range fallback
    yt.close()


def test_a_home_proxy_keeps_the_ffmpeg_path(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "proxy": "http://100.64.0.2:8899", "whole_fallback": False})
    _info(yt)
    seen = []
    monkeypatch.setattr(yt, "_fetch_hls_locally", lambda *a, **k: pytest.fail("home proxies keep ffmpeg's own download"))
    monkeypatch.setattr(yt, "_fetch_range", lambda *a, exact: seen.append(exact) or (tmp_path / "x.mp4"))
    yt.download_range(VIDEO, 1.0, 3.0, fmt="bv*[height<=720]", prefix="hd")
    assert seen == [True]
