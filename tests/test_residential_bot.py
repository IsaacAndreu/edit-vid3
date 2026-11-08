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


def test_a_502_on_the_proxy_tunnel_rotates_the_session_instead_of_pausing_the_proxy(tmp_path, monkeypatch):
    from pipeline.sourcing.youtube import tunnel_failure

    assert tunnel_failure("unable to connect to proxy', oserror('tunnel connection failed: 502 bad gateway')") == "502"
    assert tunnel_failure("tunnel connection failed: 407 proxy authentication required") is None
    assert tunnel_failure("http error 403") is None
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._local.video_id = VIDEO
    seen = []

    def dead_node():
        seen.append(yt._ydl().params["proxy"])
        if len(seen) < 3:
            raise RuntimeError("[youtube] x: Unable to download API page: ('Unable to connect to proxy', "
                               "OSError('Tunnel connection failed: 502 Bad Gateway'))")
        return "ok"

    assert yt._call("metadata", dead_node) == "ok"
    assert len(set(seen)) == 3 and yt.sessions.rotated == 2 and yt._resting[0] == 0.0   # new sessions, the proxy never rests
    calls = []
    yt._local.video_id = "abcdefghijk"
    with pytest.raises(RuntimeError, match="túnel \\(502\\)"):
        yt._call("metadata", lambda: calls.append(1) or (_ for _ in ()).throw(RuntimeError("Tunnel connection failed: 502 Bad Gateway")))
    assert len(calls) == 3 and not yt._in_quarantine(0)                                 # bounded, then this request only


def test_a_home_proxy_tunnel_failure_still_means_the_proxy_is_down(tmp_path, monkeypatch):
    from pipeline.budget import ProxyDown

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, HOME)
    monkeypatch.setattr("pipeline.sourcing.youtube.proxy_reachable", lambda proxy, timeout=5.0: True)
    with pytest.raises(ProxyDown):
        yt._call("metadata", lambda: (_ for _ in ()).throw(RuntimeError("Unable to connect to proxy: Tunnel connection failed: 502 Bad Gateway")))


def test_a_refused_video_comes_back_after_hours_through_a_residential_proxy_not_days(tmp_path, monkeypatch):
    import json

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._refuse(VIDEO)
    assert yt.refused(VIDEO)
    data = json.loads(yt._refused_path().read_text())
    data[VIDEO] -= 4 * 3600                                       # four hours ago: another session may try it
    yt._refused_path().write_text(json.dumps(data))
    yt._refused_cache = None
    assert not yt.refused(VIDEO)
    home = _source(tmp_path / "h", HOME)
    home._refuse(VIDEO)
    data = json.loads(home._refused_path().read_text())
    data[VIDEO] -= 4 * 3600
    home._refused_path().write_text(json.dumps(data))
    home._refused_cache = None
    assert home.refused(VIDEO)                                    # at home the week stays


def test_a_timeout_rotates_the_session_once_through_a_residential_proxy(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr("pipeline.sourcing.youtube.proxy_reachable", lambda proxy, timeout=5.0: True)   # the proxy is up
    yt = _source(tmp_path, RESI)
    yt._local.video_id = VIDEO
    seen = []

    def slow_ip():
        seen.append(yt._ydl().params["proxy"])
        if len(seen) == 1:
            raise RuntimeError("ERROR: [youtube] x: Unable to download API page: HTTPSConnectionPool(host='www.youtube.com', "
                               "port=443): Read timed out. (read timeout=20)")
        return "ok"

    assert yt._call("metadata", slow_ip) == "ok"
    assert len(seen) == 2 and len(set(seen)) == 2                       # the second try leaves from another IP
    assert yt.sessions.rotated == 1 and not yt.refused(VIDEO)
    calls = []

    def always_slow():
        calls.append(1)
        raise RuntimeError("Read timed out. (read timeout=20)")

    with pytest.raises(RuntimeError, match="timed out"):                 # one rotation, not a loop of them
        yt._call("metadata", always_slow)
    assert len(calls) == 2
    yt.close()


def test_a_video_youtube_refuses_to_proxies_is_dropped_at_the_first_answer(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._local.video_id = VIDEO
    calls = []

    def vpn():
        calls.append(1)
        raise RuntimeError("ERROR: [youtube] x: Unavailable with a VPN or proxy. This channel doesn't make "
                           "regionally-restricted content")

    with pytest.raises(RuntimeError, match="IP de un proxy"):
        yt._call("metadata", vpn)
    assert len(calls) == 1 and yt.refused_why(VIDEO) == "vpn" and yt.sessions.rotated == 0
    with pytest.raises(RuntimeError, match="no se vuelve a pedir"):      # the next shot does not ask again
        yt.info(VIDEO)
    assert len(calls) == 1
    yt.close()


def test_refusals_with_a_reason_keep_the_week_and_old_entries_still_read(tmp_path, monkeypatch):
    import json

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._refuse(VIDEO, "sin-hls")
    yt._refuse("abcdefghijk")
    data = json.loads(yt._refused_path().read_text())
    data[VIDEO]["at"] -= 4 * 3600                                 # four hours: the bot refusal lapses, this one holds
    data["abcdefghijk"] -= 4 * 3600
    data["zzzzzzzzzzz"] = data["abcdefghijk"] + 4 * 3600          # a legacy float entry, fresh
    yt._refused_path().write_text(json.dumps(data))
    yt._refused_cache = None
    assert yt.refused_why(VIDEO) == "sin-hls" and yt.refused_why("abcdefghijk") is None and yt.refused_why("zzzzzzzzzzz") == "bot"


def test_a_response_yt_dlp_cannot_parse_is_asked_once_more_from_another_ip(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._local.video_id = VIDEO
    seen = []

    def broken_then_fine():
        seen.append(yt._ydl().params["proxy"])
        if len(seen) == 1:
            raise TypeError("sequence item 52: expected str instance, NoneType found")
        return "ok"

    assert yt._call("metadata", broken_then_fine) == "ok"
    assert len(seen) == 2 and len(set(seen)) == 2 and yt.sessions.rotated == 1

    def always_broken():
        seen.append(1)
        raise KeyError("formats")

    with pytest.raises(RuntimeError, match="formats"):                  # one more try, not a loop
        yt._call("metadata", always_broken)
    assert len(seen) == 4
    yt.close()


def test_a_geo_blocked_video_is_dropped_at_the_first_answer(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, RESI)
    yt._local.video_id = VIDEO
    calls = []

    def geo():
        calls.append(1)
        raise RuntimeError("ERROR: [youtube] x: The uploader has not made this video available in your country. "
                           "This video is available in Andorra, United Arab Emirates")

    with pytest.raises(RuntimeError, match="país del proxy"):
        yt._call("metadata", geo)
    assert len(calls) == 1 and yt.refused_why(VIDEO) == "geo" and yt.sessions.rotated == 0
    with pytest.raises(RuntimeError, match="no se vuelve a pedir"):
        yt.info(VIDEO)
    yt.close()


def test_candidates_that_could_never_be_downloaded_are_dropped_at_the_search(tmp_path, monkeypatch):
    from pipeline.schemas import Storyboard
    from pipeline.sourcing.youtube import whole_estimate_mb
    from tests.test_sourcing import BROLL

    board = Storyboard(sheets=["cache/sb/000.jpg"], columns=3, rows=3, tileWidth=320, tileHeight=180, interval=5.0, frames=9)
    base = {"title": "t", "channel": "c", "uploader": None, "license": "youtube-standard", "width": 1920, "height": 1080,
            "maxHeight": 1080, "storyboard": {"fps": 0.2, "width": 320}}
    infos = {"AAAAAAAAAAA": {**base, "id": "AAAAAAAAAAA", "duration": 900, "hls": False, "wholeMb": 60.0},   # too long
             "BBBBBBBBBBB": {**base, "id": "BBBBBBBBBBB", "duration": 300, "hls": False, "wholeMb": 147.0},  # too heavy
             "CCCCCCCCCCC": {**base, "id": "CCCCCCCCCCC", "duration": 300, "hls": False, "wholeMb": 40.0},   # small: whole is fine
             "DDDDDDDDDDD": {**base, "id": "DDDDDDDDDDD", "duration": 3000, "hls": True},                    # HLS: ranges
             "EEEEEEEEEEE": {**base, "id": "EEEEEEEEEEE", "duration": 3000}}                                 # old cache: unknown
    entries = [{"id": v, "title": "t", "channel": "c", "duration": 300, "url": ""} for v in infos]
    for proxy, expected in ((RESI, ["yt:CCCCCCCCCCC", "yt:DDDDDDDDDDD", "yt:EEEEEEEEEEE"]), (HOME, [f"yt:{v}" for v in infos])):
        monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
        yt = _source(tmp_path / proxy[-4:], proxy, videos_per_shot=9)
        monkeypatch.setattr(yt, "search", lambda query: entries)
        monkeypatch.setattr(yt, "info", lambda v: infos[v])
        monkeypatch.setattr(yt, "storyboard", lambda info: board)
        notes = []
        found = yt.candidates(BROLL, notes)
        assert [c.id for c in found] == expected
        if proxy == RESI:
            assert yt.refused_why("AAAAAAAAAAA") == "sin-hls" and yt.refused_why("BBBBBBBBBBB") == "sin-hls"
            assert any("dura 15 min" in n for n in notes) and any("pesa 147 MB" in n for n in notes)
        yt.close()
    formats = [{"format_id": "137", "vcodec": "avc1", "acodec": "none", "height": 1080, "filesize": 300e6},
               {"format_id": "136", "vcodec": "avc1", "acodec": "none", "height": 720, "filesize_approx": 120e6},
               {"format_id": "18", "vcodec": "avc1", "acodec": "mp4a", "height": 360, "filesize": 50e6},
               {"format_id": "140", "vcodec": "none", "acodec": "mp4a", "filesize": 9e6},
               {"format_id": "sb0", "vcodec": "none", "acodec": "none", "height": 90, "filesize": 1e6}]
    assert whole_estimate_mb(formats) == 50.0                          # the progressive 360p carries its own audio
    assert whole_estimate_mb(formats[:2] + formats[3:]) == 129.0        # 720p video + the smallest audio
    assert whole_estimate_mb([{"format_id": "x", "vcodec": "avc1", "height": 720}]) is None
