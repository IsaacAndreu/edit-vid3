"""«Lo que dicen estos datos» 3: each range says which way it came and why it was not HLS; and an offline look at
the server's extractions says whether yt-dlp's selection misses HLS streams that are there."""

from __future__ import annotations

import json
import subprocess

import pytest

from pipeline import diag_hls
from pipeline.sourcing.youtube import YouTubeSource

pytestmark = pytest.mark.usefixtures("fake_media_ok")

VIDEO = "dQw4w9WgXcQ"


def _hls(fid, h, fps=30):
    return {"format_id": fid, "protocol": "m3u8_native", "ext": "mp4", "vcodec": "avc1.4D401F", "acodec": "mp4a.40.2",
            "height": h, "width": h * 16 // 9, "fps": fps,
            "url": f"https://manifest.googlevideo.com/api/manifest/hls_playlist/expire/9999999999/itag/{fid}/index.m3u8"}


def _https(fid, h):
    return {"format_id": fid, "protocol": "https", "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none", "height": h,
            "fps": 30, "filesize": 5_000_000, "url": "https://rr1.googlevideo.com/videoplayback?expire=9999999999"}


def _source(tmp_path, formats):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    yt.metrics_path = tmp_path / "work" / "v" / "youtube_downloads.jsonl"
    path = yt._full_info_path(VIDEO)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": VIDEO, "duration": 60, "formats": formats, "_edit_vid3_clients": yt._clients(),
                                "_edit_vid3_via": "", "_edit_vid3_session": None}))
    return yt


def test_a_whole_download_says_why_it_was_not_hls(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, [_https("136", 720)])

    def whole(video_id, fmt, prefix, info_path):
        yt._metric("download (completo)", ok=True, seconds=1.0)
        target = tmp_path / "videos" / VIDEO / f"full_{prefix}.mp4"
        target.write_bytes(b"x")
        return target

    monkeypatch.setattr(yt, "_fetch_whole", whole)
    monkeypatch.setattr(subprocess, "run", lambda c, **k: (open(c[-1], "wb").write(b"m") if c[0] == "ffmpeg" else None,
                                                           subprocess.CompletedProcess(c, 0, "{}", ""))[1])
    yt.download_range(VIDEO, 1.0, 3.0, fmt="bv*[height<=720]", prefix="hd")
    rows = [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]
    whole_row = next(r for r in rows if r["action"] == "download (completo)")
    assert "no trae m3u8" in whole_row["notHls"] and "https" in whole_row["notHls"]
    assert rows[-1]["action"] == "archivo hd" and rows[-1]["route"] == "entero"
    yt.close()


def test_the_offline_diagnosis_finds_hls_the_selection_misses(tmp_path):
    folder = tmp_path / "cache" / "videos" / VIDEO
    folder.mkdir(parents=True)
    (folder / "ytdlp-info.json").write_text(json.dumps({
        "id": VIDEO, "title": "t", "extractor": "youtube", "extractor_key": "Youtube",
        "webpage_url": f"https://www.youtube.com/watch?v={VIDEO}",
        "formats": [_hls("93", 360), _hls("95", 720), _https("136", 720)]}))
    other = tmp_path / "cache" / "videos" / "aaaaaaaaaaa"
    other.mkdir(parents=True)
    weird = _hls("95", 720)
    weird["vcodec"] = "vp9"                     # an HLS stream the avc1-first request still accepts via its fallback
    (other / "ytdlp-info.json").write_text(json.dumps({
        "id": "aaaaaaaaaaa", "title": "t", "extractor": "youtube", "extractor_key": "Youtube",
        "webpage_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "formats": [weird]}))
    text = diag_hls.main(tmp_path, 7)
    assert "Con formatos m3u8: 2 de 2" in text
    ext = diag_hls.extractions(tmp_path)
    assert ext["selectionFails"]["clip HD"] == 0          # what the pipeline asks finds the HLS streams
