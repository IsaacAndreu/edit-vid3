"""Local ffmpeg/ffprobe and the storyboard CDN never go through the residential proxy."""

import json
import subprocess

import requests

from pipeline.sourcing.youtube import YouTubeSource, local_env

RESI = "http://user:pass@resi-bridge-eu.rainproxy.io:1111"
HOME = "http://100.64.0.2:8899"


def _source(tmp_path, **cfg):
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", **cfg})


def test_local_env_drops_every_proxy_variable(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://u:p@proxy.example:1")
    monkeypatch.setenv("http_proxy", "http://x")
    monkeypatch.setenv("ALL_PROXY", "socks5://y")
    monkeypatch.setenv("NO_PROXY", "localhost")
    env = local_env()
    assert not {"HTTPS_PROXY", "http_proxy", "ALL_PROXY"} & set(env) and env["NO_PROXY"] == "localhost" and "PATH" in env


def test_cutting_and_probing_run_without_proxy_variables(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://u:p@proxy.example:1")
    yt = _source(tmp_path, proxy=RESI)
    seen = []

    def run(command, **kwargs):
        seen.append((command[0], kwargs.get("env")))
        return subprocess.CompletedProcess(command, 0, json.dumps({"streams": [{"start_time": "10.0"}], "format": {"duration": "5"}}), "")

    monkeypatch.setattr(subprocess, "run", run)
    whole = tmp_path / "videos" / "vid00000000" / "full_hd.mp4"
    whole.parent.mkdir(parents=True)
    whole.write_bytes(b"x")
    yt._cut(whole, "vid00000000", 10, 15, "hd", audio=False)
    assert seen and seen[0][0] == "ffmpeg" and "HTTPS_PROXY" not in seen[0][1]


def test_storyboard_thumbnails_go_direct_through_a_residential_way_and_fall_back_to_it(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    hits = {"direct": 0, "proxy": 0}

    class Response:
        def __init__(self, status):
            self.status_code = status
            self.content = b"jpg"

        def raise_for_status(self): ...

    def direct(url, timeout):
        hits["direct"] += 1
        if "M1" in url:
            raise requests.ConnectionError("cdn unreachable")
        return Response(200)

    def proxied(url, timeout, proxies=None):
        hits["proxy"] += 1
        assert proxies and "session-" in proxies["https"]
        return Response(200)

    monkeypatch.setattr(yt._direct, "get", direct)
    monkeypatch.setattr(yt._sessions[0], "get", proxied)
    assert yt._get("https://i.ytimg.com/sb/a/M0.jpg").status_code == 200 and hits == {"direct": 1, "proxy": 0}
    assert yt._get("https://i.ytimg.com/sb/a/M1.jpg").status_code == 200 and hits == {"direct": 2, "proxy": 1}
    yt._get("https://www.youtube.com/api/timedtext?x=1")                 # YouTube itself: the proxy, as it must
    assert hits == {"direct": 2, "proxy": 2}
    assert yt._direct.trust_env is False


def test_a_home_proxy_still_carries_the_thumbnails(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=HOME)
    hits = []
    monkeypatch.setattr(yt._direct, "get", lambda url, timeout: hits.append("direct"))

    class Response:
        status_code = 200

    monkeypatch.setattr(yt._sessions[0], "get", lambda url, timeout: hits.append("home") or Response())
    yt._get("https://i.ytimg.com/sb/a/M0.jpg")
    assert hits == ["home"]
