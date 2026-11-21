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


def test_the_diagnosis_never_tests_formats_over_the_network(tmp_path, monkeypatch):
    """yt-dlp tests the HLS formats of videos uploaded ≤ 2 days before extraction (`__needs_testing`) by downloading a
    piece: on the server the diagnosis did that straight from its IP (403s). It must stay offline, and count them."""

    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("the diagnosis touched the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    folder = tmp_path / "cache" / "videos" / VIDEO
    folder.mkdir(parents=True)
    fresh = {**_hls("95", 720), "__needs_testing": True}
    (folder / "ytdlp-info.json").write_text(json.dumps({
        "id": VIDEO, "title": "t", "extractor": "youtube", "extractor_key": "Youtube",
        "webpage_url": f"https://www.youtube.com/watch?v={VIDEO}", "formats": [fresh, _https("136", 720)]}))
    ext = diag_hls.extractions(tmp_path)
    assert ext["untested"] == 1 and ext["selectionFails"]["clip HD"] == 0


def test_the_format_test_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    captured = {}

    class Ydl:
        def __init__(self, options):
            captured.update(options)

    monkeypatch.setattr("yt_dlp.YoutubeDL", Ydl)
    on = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"cookies": "never"})
    on._ydl({"simulate": True})
    assert "check_formats" not in captured                       # default: as before
    off = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"cookies": "never", "hls_format_test": False})
    off._ydl({"simulate": True})
    assert captured["check_formats"] is False


def test_analysis_windows_are_not_cut_at_the_final_clips_quality():
    from pipeline.sourcing.youtube import cut_codec

    assert cut_codec("a360")[cut_codec("a360").index("-crf") + 1] == "26"
    assert cut_codec("hd")[cut_codec("hd").index("-crf") + 1] == "16"       # the clips in the video: as before


def test_the_diagnosis_says_which_videos_found_no_fitting_hls(tmp_path):
    """«Ningún formato HLS encaja» rows grouped by video, each checked against its extraction: are they the videos
    whose HLS formats yt-dlp tests over the network before choosing?"""

    import time

    folder = tmp_path / "cache" / "videos" / VIDEO
    folder.mkdir(parents=True)
    (folder / "ytdlp-info.json").write_text(json.dumps({
        "id": VIDEO, "title": "t", "extractor": "youtube", "extractor_key": "Youtube",
        "webpage_url": f"https://www.youtube.com/watch?v={VIDEO}",
        "formats": [{**_hls("230", 360), "acodec": "none", "__needs_testing": True}]}))
    log = tmp_path / "work" / "v" / "youtube_downloads.jsonl"
    log.parent.mkdir(parents=True)
    row = {"ts": time.time(), "action": "download (completo)", "video": VIDEO,
           "notHls": "ningún formato HLS encaja con «bv*[height<=360]»"}
    log.write_text("\n".join(json.dumps(r) for r in (row, row, {**row, "video": "bbbbbbbbbbb"})) + "\n")
    text = diag_hls.main(tmp_path, 7)
    assert "3 filas de 2 vídeos distintos (sin su extracción en disco: 1)" in text
    assert "Con HLS «por probar»: 1 vídeos, 2 filas" in text
    assert "La selección sin red sí encuentra HLS en 1 de ellos" in text


def test_untested_hls_is_tried_again_without_the_test_only_when_asked(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    untested = {**_hls("95", 720), "__needs_testing": True}
    seen = []

    def run(on):
        yt = _source(tmp_path, [untested, _https("136", 720)])
        yt.cfg["hls_retry_untested"] = on
        yt.cfg["whole_fallback"] = False

        def fetch_range(video_id, start, end, fmt, prefix, *rest, exact=False):
            seen.append((exact, bool(getattr(yt._local, "skip_format_test", False))))
            if exact and not getattr(yt._local, "skip_format_test", False):
                raise RuntimeError("Requested format is not available")
            target = tmp_path / f"{prefix}-{len(seen)}.mp4"
            target.write_bytes(b"x")
            return target

        monkeypatch.setattr(yt, "_fetch_range", fetch_range)
        yt.download_range(VIDEO, 1.0, 3.0, fmt="bv*[height<=720]", prefix="hd")
        rows = [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]
        yt.close()
        return rows[-1]

    last = run(False)
    assert "por probar" in last.get("notHls", "") and seen == [(True, False), (False, False)]    # off: as before
    seen.clear()
    yt_rows_path = tmp_path / "work" / "v" / "youtube_downloads.jsonl"
    yt_rows_path.unlink()
    last = run(True)
    assert seen == [(True, False), (True, True)] and last["route"] == "hls-ffmpeg-sin-prueba"


def test_youtube_stats_break_down_the_hls_misses():
    from pipeline.ytstats import hls_miss_lines, hls_misses

    rows = [{"video": "a", "notHls": "ningún formato HLS encaja con «bv*[height<=360]…» (HLS por probar)"},
            {"video": "a", "notHls": "ningún formato HLS encaja con «bv*[height<=720]…»"},
            {"video": "b", "notHls": "la extracción no trae m3u8"}, {"video": "c", "route": "hls-local-sin-prueba"}]
    m = hls_misses(rows)
    assert (m["rows"], m["untested"], m["videos"], m["retried"]) == (2, 1, 1, 1)
    assert m["byPrefix"] == {"análisis 360p": 1, "clip HD": 1}
    assert "Salvados al repetir" in "\n".join(hls_miss_lines(m))
