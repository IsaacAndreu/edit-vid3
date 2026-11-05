"""Through a residential proxy a bot check or a 429 rotates the video's session; home proxies keep their quarantine."""

import pytest

from pipeline.sourcing.common import SourceUnavailable
from pipeline.sourcing.youtube import RateLimited, YouTubeSource

RESI = "http://user:pass@resi-bridge-eu.rainproxy.io:1111"
HOME = "http://100.64.0.2:8899"
VIDEO = "dQw4w9WgXcQ"
BOT = "ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies"


def _source(tmp_path, proxy, **cfg):
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                    "proxy": proxy, "rate_backoff": 0, **cfg})


def test_a_bot_check_rotates_the_videos_session_instead_of_quarantining_the_proxy(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._local.video_id = VIDEO
    first = yt.sessions.session_id(VIDEO)
    seen = []

    def flaky_ip():
        seen.append(yt._ydl().params["proxy"])
        if len(seen) < 3:
            raise RuntimeError(BOT)
        return "ok"

    assert yt._call("metadata", flaky_ip) == "ok"
    assert len(seen) == 3 and len(set(seen)) == 3                       # three connections, three sessions (IPs)
    assert f"session-{first}:" in seen[0] and f"session-{yt.sessions.session_id(VIDEO)}:" in seen[2]
    assert not yt._in_quarantine(0) and yt.blocked is None and not yt.recovering() and not yt.refused(VIDEO)
    yt.close()


def test_after_the_rotations_it_is_the_video_dropped_without_quarantine(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._local.video_id = VIDEO
    calls = []

    def always_bot():
        calls.append(1)
        raise RuntimeError(BOT)

    with pytest.raises(RuntimeError, match="descarta"):
        yt._call("metadata", always_bot)
    assert len(calls) == 3 and yt.refused(VIDEO)                        # 1 + 2 rotations
    assert not yt._in_quarantine(0) and yt.blocked is None and not yt.recovering()
    yt._local.video_id = "abcdefghijk"                                  # the proxy is still in service for the rest
    assert yt._call("metadata", lambda: "ok") == "ok"
    yt.close()


def test_a_429_rotates_with_a_pause_and_then_gives_up_without_quarantine(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI, rate_backoff=7)
    yt._local.video_id = VIDEO
    naps = []
    monkeypatch.setattr("pipeline.sourcing.youtube.time.sleep", lambda s: naps.append(s))
    calls = []

    def limited():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("HTTP Error 429: Too Many Requests")
        return "ok"

    assert yt._call("download (HLS)", limited) == "ok" and naps == [7]
    calls.clear()
    with pytest.raises(RateLimited):
        yt._call("download (HLS)", lambda: calls.append(1) or (_ for _ in ()).throw(RuntimeError("HTTP Error 429: Too Many Requests")))
    assert len(calls) == 2 and not yt._in_quarantine(0) and yt.blocked is None   # one rotation left, then dropped
    assert not yt.refused(VIDEO)                                        # a 429 says nothing about the video
    yt.close()


def test_a_home_proxy_keeps_its_quarantine(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, HOME, bot_breaker_videos=1)
    yt._local.video_id = VIDEO
    with pytest.raises((RuntimeError, SourceUnavailable)):
        yt._call("metadata", lambda: (_ for _ in ()).throw(RuntimeError(BOT)))
    assert yt._in_quarantine(0) and yt.sessions.rotated == 0
    yt.close()


def test_a_residential_metadata_proxy_retries_from_another_session(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.delenv("YOUTUBE_METADATA_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                  "metadata_proxy": "http://m:w@gate.example:7000"})
    seen = []

    def extract(url, extra):
        seen.append(yt._ydl(extra).params["proxy"])
        if len(seen) == 1:
            raise RuntimeError(BOT)
        return {"title": "t", "channel": "c", "formats": []}

    monkeypatch.setattr(yt, "_extract", extract)
    yt.info(VIDEO)
    assert len(seen) == 2 and seen[0] != seen[1] and yt.sessions.rotated == 1   # the retry left from another IP
    yt.close()
