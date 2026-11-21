"""«Lo que dicen estos datos» 3b: a video without HLS by HTTP byte ranges (opt-in, sourcing.youtube.byte_ranges):
the mp4's sidx says which bytes hold the seconds, only those are requested, and ffmpeg cuts locally."""

from __future__ import annotations

import http.server
import json
import subprocess
import threading
from pathlib import Path

import pytest

from pipeline.sourcing import byteranges
from pipeline.sourcing.youtube import YouTubeSource

VIDEO = "dQw4w9WgXcQ"


@pytest.fixture(scope="module")
def fragmented(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("dash")
    video = folder / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=90",
                    "-c:v", "libx264", "-g", "30", "-movflags", "+frag_keyframe+empty_moov+global_sidx+dash",
                    "-f", "mp4", str(video)], check=True)
    audio = folder / "a.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=90", "-c:a", "aac",
                    "-movflags", "+frag_keyframe+empty_moov+global_sidx+dash", "-frag_duration", "1000000",
                    "-f", "mp4", str(audio)], check=True)
    return folder


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    seen: list[str] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = Path(self.directory) / self.path.split("?")[0].lstrip("/")
        data = path.read_bytes()
        wanted = self.headers.get("Range")
        RangeHandler.seen.append(wanted or "")
        if wanted:
            first, last = wanted.removeprefix("bytes=").split("-")
            first, last = int(first), min(int(last), len(data) - 1)
            body = data[first:last + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {first}-{last}/{len(data)}")
        else:
            body = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server(fragmented):
    handler = lambda *a, **k: RangeHandler(*a, directory=str(fragmented), **k)   # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    RangeHandler.seen = []
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_the_plan_takes_only_the_fragments_covering_the_seconds(fragmented):
    data = (fragmented / "v.mp4").read_bytes()
    cut = byteranges.plan(data[:64 * 1024], 10.2, 13.7)
    assert cut.start <= 10.2 and cut.end >= 13.7 and cut.end - cut.start <= 5.0
    assert cut.data[1] - cut.data[0] < len(data) / 4
    with pytest.raises(byteranges.NoIndex):
        byteranges.plan(b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00", 1, 2)
    assert byteranges.pieces(0, 25 * 1024 * 1024)[-1][1] == 25 * 1024 * 1024


def _source(tmp_path, base, **cfg):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                       config={"min_interval": 0, "cookies": "never", "byte_ranges": True, "whole_fallback": False, **cfg})
    yt.metrics_path = tmp_path / "work" / "v" / "youtube_downloads.jsonl"
    path = yt._full_info_path(VIDEO)
    path.parent.mkdir(parents=True, exist_ok=True)
    formats = [{"format_id": "136", "protocol": "https", "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none",
                "height": 180, "width": 320, "fps": 30, "url": f"{base}/v.mp4?expire=9999999999"},
               {"format_id": "140", "protocol": "https", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2",
                "url": f"{base}/a.m4a?expire=9999999999"}]
    path.write_text(json.dumps({"id": VIDEO, "title": "t", "extractor": "youtube", "extractor_key": "Youtube",
                                "webpage_url": f"https://www.youtube.com/watch?v={VIDEO}", "duration": 30,
                                "formats": formats, "_edit_vid3_clients": yt._clients(), "_edit_vid3_via": "",
                                "_edit_vid3_session": None}))
    return yt


def test_a_clip_without_hls_comes_by_byte_ranges_and_is_frame_exact(tmp_path, monkeypatch, server, fragmented):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, server)
    clip = yt.download_range(VIDEO, 10.2, 13.7, fmt="bv*[height<=720][vcodec^=avc1]/bv*[height<=720]", prefix="hd")
    assert clip.name == "hd_10.200_13.700.mp4"
    assert all(r.startswith("bytes=") for r in RangeHandler.seen)            # never the whole file
    fetched = sum(int(b) - int(a) + 1 for a, b in (r.removeprefix("bytes=").split("-") for r in RangeHandler.seen))
    assert fetched < (fragmented / "v.mp4").stat().st_size / 3
    reference = tmp_path / "ref.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "10.2", "-i", str(fragmented / "v.mp4"), "-t", "3.5",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(reference)], check=True)
    ssim = subprocess.run(["ffmpeg", "-i", str(clip), "-i", str(reference), "-lavfi", "ssim", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    value = float(ssim.split("All:")[-1].split()[0])
    assert value >= 0.99, ssim[-300:]
    rows = [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]
    assert rows[-1]["route"] == "rango-bytes" and rows[-1]["ok"]
    assert any(r["action"] == "download (rango)" for r in rows)
    yt.close()


def test_with_sound_both_tracks_come_by_byte_ranges(tmp_path, monkeypatch, server):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, server)
    clip = yt.download_range(VIDEO, 5.0, 8.0, fmt="bv*[height<=720][vcodec^=avc1]+ba/b[height<=720]", prefix="hdav",
                             audio=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json",
                                       str(clip)], capture_output=True, text=True).stdout)
    assert sorted(s["codec_type"] for s in probe["streams"]) == ["audio", "video"]
    yt.close()


def test_off_by_default(tmp_path, monkeypatch, server):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, server, byte_ranges=False)
    monkeypatch.setattr(yt, "_fetch_range", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg path")))
    with pytest.raises(RuntimeError, match="ffmpeg path"):
        yt.download_range(VIDEO, 1.0, 3.0, fmt="bv*[height<=720]", prefix="hd")
    assert RangeHandler.seen == []
    yt.close()


def test_with_byte_ranges_a_video_refused_for_no_hls_can_be_used_again(tmp_path, monkeypatch):
    """19-11: «800 opciones de vídeos que no se pueden bajar en HD» in a GTA video: refused «sin-hls» for 7 days.
    With byte_ranges on that refusal no longer applies (their ranges come by byte ranges)."""

    from pipeline.sourcing.youtube import Refused, unreachable_videos

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    resi = "http://u:p@resi.rainproxy.io:1"
    off = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", "proxy": resi})
    off._refuse(VIDEO, "sin-hls")
    with pytest.raises(Refused):
        off.download_range(VIDEO, 1.0, 2.0, fmt="bv*[height<=720]", prefix="hd")
    assert VIDEO in unreachable_videos(tmp_path)
    on = YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                       config={"min_interval": 0, "cookies": "never", "proxy": resi, "byte_ranges": True})
    assert "sin-hls" not in on._blocking_refusals()
    assert VIDEO not in unreachable_videos(tmp_path, without_hls=False)
    off.close()
    on.close()


@pytest.fixture
def odd_server(tmp_path_factory):
    """v.mp4 that is really a webm, and n.mp4 an mp4 with its moov but no sidx (descargas-rango-fallo.md)."""

    folder = tmp_path_factory.mktemp("odd")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=20",
                    "-c:v", "libvpx", "-b:v", "200k", "-f", "webm", str(folder / "v.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=20",
                    "-c:v", "libx264", "-movflags", "+faststart", "-f", "mp4", str(folder / "n.mp4")], check=True)
    handler = lambda *a, **k: RangeHandler(*a, directory=str(folder), **k)   # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    RangeHandler.seen = []
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _fails_by_range(tmp_path, monkeypatch, yt):
    monkeypatch.setattr(yt, "_fetch_range", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg path")))
    with pytest.raises(RuntimeError, match="ffmpeg path"):
        yt.download_range(VIDEO, 1.0, 3.0, fmt="bv*[height<=720][vcodec^=avc1]/bv*[height<=720]", prefix="hd")
    return [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]


def test_a_webm_answer_says_what_came_and_is_not_asked_again(tmp_path, monkeypatch, odd_server):
    """22-11: 884 of 886 ranges failed with «faltan moov o sidx» counted as «other»: the row now carries the format,
    the HTTP answer and the first bytes (1a 45 df a3 = Matroska), its own cause, and the video is not asked again."""

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, odd_server)
    rows = _fails_by_range(tmp_path, monkeypatch, yt)
    failed = [r for r in rows if r["action"] == "download (rango)" and not r["ok"]]
    assert len(failed) == 1 and failed[0]["cause"] == "rango-sin-indice"
    assert "webm (Matroska)" in failed[0]["detail"] and "1a 45 df a3" in failed[0]["detail"]
    assert "itag 136" in failed[0]["detail"] and "HTTP 206" in failed[0]["detail"]
    asked = len(RangeHandler.seen)
    _fails_by_range(tmp_path, monkeypatch, yt)                 # the next shot of the same video
    assert len(RangeHandler.seen) == asked                    # no new range request for it
    yt.close()


def test_an_mp4_without_sidx_says_so(tmp_path, monkeypatch, odd_server):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, odd_server)
    info = yt._full_info_path(VIDEO)
    data = json.loads(info.read_text())
    data["formats"][0]["url"] = f"{odd_server}/n.mp4?expire=9999999999"
    info.write_text(json.dumps(data))
    rows = _fails_by_range(tmp_path, monkeypatch, yt)
    failed = [r for r in rows if r["action"] == "download (rango)" and not r["ok"]]
    assert failed and failed[0]["cause"] == "rango-sin-indice" and "ftyp" not in failed[0]["detail"][:5]
    assert "00 00 00" in failed[0]["detail"]                     # the first bytes, in hex
    yt.close()


def test_new_causes_and_one_row_per_video():
    from pipeline.sourcing.youtube import error_cause

    assert error_cause("faltan moov o sidx (['\\x9fB\\x86\\x81'])") == "rango-sin-indice"
    assert error_cause("yt-dlp download: X no tiene HLS y entero supera el tope del proxy residencial (1000 MB)") \
        == "sin-hls-tope"


def test_the_probe_says_what_comes_back(tmp_path, monkeypatch, odd_server):
    """python -m pipeline.sonda_rango: one request of 64 KB per format and what the parser makes of it."""

    from types import SimpleNamespace

    from pipeline import sonda_rango

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, odd_server)
    info = yt._full_info_path(VIDEO)
    monkeypatch.setattr(yt, "_fresh_full_info", lambda video_id: info)
    lines = sonda_rango.probe(SimpleNamespace(), f"https://youtu.be/{VIDEO}", youtube=yt)
    assert len(lines) == 1 and "1a 45 df a3" in lines[0] and "webm (Matroska)" in lines[0]
    assert RangeHandler.seen == ["bytes=0-65535"]                 # only the first 64 KB
    assert "sidx" in sonda_rango.verdict(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 24)
    yt.close()
