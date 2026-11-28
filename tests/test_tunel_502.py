"""A 502 of the proxy's tunnel is asked again once in the same session before rotating; and when several sessions
fail the tunnel one after another, the proxy itself is down: no more rotations are spent on it."""

from __future__ import annotations

import pytest

from pipeline.budget import ProxyDown
from tests.test_hls_local import VIDEO, _source

TUNNEL = "yt-dlp download (HLS): Unable to connect to proxy: Tunnel connection failed: 502 Bad Gateway"


@pytest.fixture
def yt(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)
    source = _source(tmp_path)
    source._local.video_id = VIDEO
    return source


def test_one_502_is_asked_again_in_the_same_session(yt):
    tries = []

    def fn():
        tries.append(yt.sessions.session_id(yt._session_key()))
        if len(tries) == 1:
            raise RuntimeError(TUNNEL)
        return "ok"

    assert yt._call("download (HLS)", fn) == "ok"
    assert len(tries) == 2 and tries[0] == tries[1] and yt.sessions.rotated == 0


def test_a_502_again_in_that_session_rotates(yt):
    tries = []

    def fn():
        tries.append(yt.sessions.session_id(yt._session_key()))
        if len(tries) <= 2:
            raise RuntimeError(TUNNEL)
        return "ok"

    assert yt._call("download (HLS)", fn) == "ok"
    assert tries[0] == tries[1] != tries[2] and yt.sessions.rotated == 1


def test_when_every_session_fails_the_tunnel_the_proxy_is_down(yt):
    def fn():
        raise RuntimeError(TUNNEL)

    with pytest.raises(ProxyDown):
        yt._call("download (HLS)", fn)
    assert yt.sessions.rotated <= 2                       # not every rotation spent on a proxy that is down
