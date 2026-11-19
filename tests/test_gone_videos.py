"""«Lo que dicen estos datos» 8: a video YouTube says is gone is not asked for again, in this stage or the next."""

from __future__ import annotations

import pytest

from pipeline.sourcing.youtube import Refused, YouTubeSource, unreachable_videos

VIDEO = "dQw4w9WgXcQ"


def test_a_removed_video_is_refused_everywhere(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    yt.metrics_path = tmp_path / "m.jsonl"
    yt._local.video_id = VIDEO

    def gone():
        raise RuntimeError("ERROR: [youtube] dQw4w9WgXcQ: Video unavailable. This video has been removed by the uploader")

    with pytest.raises(Refused):
        yt._call("download (HLS)", gone)
    assert yt.refused_why(VIDEO) == "no-disponible"
    with pytest.raises(Refused):                                   # the next stage: nothing asked
        yt.download_range(VIDEO, 1.0, 2.0, fmt="bv*[height<=720]", prefix="hd")
    with pytest.raises(Refused):
        yt.info(VIDEO)
    assert VIDEO in unreachable_videos(tmp_path)                   # the judge leaves it out too
    yt.close()


def test_a_format_that_is_not_there_is_not_the_video_being_gone(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    yt._local.video_id = VIDEO
    with pytest.raises(RuntimeError) as caught:
        yt._call("download (HLS)", lambda: (_ for _ in ()).throw(RuntimeError("Requested format is not available")))
    assert not isinstance(caught.value, Refused) and yt.refused_why(VIDEO) is None
    yt.close()
