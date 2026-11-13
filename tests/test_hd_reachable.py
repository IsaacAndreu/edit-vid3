"""Clips of videos that cannot come in HD through the residential proxy are neither analysed nor chosen."""

import json
import time

from pipeline import judge
from pipeline.context import RunContext
from pipeline.sourcing.youtube import YouTubeSource, unreachable_videos


def _source(tmp_path, residential=True):
    src = YouTubeSource.__new__(YouTubeSource)
    src.cfg = {"max_height": 720, "max_fps": 30}
    src.residential = residential
    src.cache_dir = tmp_path

    def ydl(extra=None):
        import yt_dlp

        return yt_dlp.YoutubeDL({"quiet": True, **(extra or {})})

    src._ydl = ydl
    return src


def _info(tmp_path, *, duration, size, hls=False):
    formats = [{"format_id": "136", "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none", "height": 720, "fps": 30,
                "protocol": "https", "url": "https://x/v", "filesize": size}]
    if hls:
        formats.append({"format_id": "95", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 720,
                        "protocol": "m3u8_native", "url": "https://x/m3u8"})
    path = tmp_path / "info.json"
    path.write_text(json.dumps({"id": "abc", "title": "t", "extractor": "youtube", "duration": duration, "formats": formats,
                                "webpage_url": "https://www.youtube.com/watch?v=abc"}))
    return path


def test_a_video_too_big_for_the_proxy_in_hd_is_known_before_its_360p_analysis(tmp_path):
    src = _source(tmp_path)
    assert "dura 24 min" in src.hd_unreachable("abc", _info(tmp_path, duration=24 * 60, size=50e6))
    assert "pesa 258 MB" in src.hd_unreachable("abc", _info(tmp_path, duration=300, size=258e6))
    assert src.hd_unreachable("abc", _info(tmp_path, duration=300, size=40e6)) is None              # small: fine
    assert src.hd_unreachable("abc", _info(tmp_path, duration=24 * 60, size=258e6, hls=True)) is None  # HLS: by range
    assert _source(tmp_path, residential=False).hd_unreachable("abc", _info(tmp_path, duration=3600, size=1e9)) is None


def test_the_judge_leaves_out_refused_videos_and_chooses_again(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    ctx = RunContext.create("pazos", root=tmp_path)
    refused = ctx.cache_dir / "videos" / ".rechazados.json"
    refused.parent.mkdir(parents=True, exist_ok=True)
    refused.write_text(json.dumps({"DBSxSwtQiU0": {"at": time.time(), "why": "sin-hls"},
                                   "old": {"at": time.time() - 30 * 86400, "why": "sin-hls"},
                                   "bot": time.time()}))
    assert unreachable_videos(ctx.cache_dir) == {"DBSxSwtQiU0"}        # a «bot» refusal is the IP, not the video
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    pick = {"shotId": "s040", "status": "selected", "decidedBy": "judge", "candidateId": "yt:DBSxSwtQiU0", "source": "youtube",
            "kind": "video", "credit": "Fuente: X", "url": "https://www.youtube.com/watch?v=DBSxSwtQiU0", "start": 1.0, "end": 4.0}
    ctx.write_json(judge.OUTPUT, {"slug": "pazos", "selections": [pick]})
    assert judge.validate(ctx) is False                                 # the judge runs again on the retry
    ctx.write_json(judge.OUTPUT, {"slug": "pazos", "selections": [{**pick, "candidateId": "yt:other"}]})
    assert judge.validate(ctx) is True
