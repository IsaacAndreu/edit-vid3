"""A residential proxy (user in its URL) gets one sticky session per video; home proxies stay as they are."""

import json
import time

import pytest

from pipeline.sourcing.proxy_sessions import (ProxySessions, is_residential, mask_proxy, new_session_id,
                                              with_sticky_session)
from pipeline.sourcing.youtube import YouTubeSource

RESI = "http://user:p%40ss@resi-bridge-eu.rainproxy.io:1111"
HOME = "http://100.64.0.2:8899"


def _source(tmp_path, **cfg):
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", **cfg})


def test_the_session_suffix_goes_on_the_user_and_the_password_is_left_alone():
    assert with_sticky_session(RESI, "abc123") == "http://user-time-30-session-abc123:p%40ss@resi-bridge-eu.rainproxy.io:1111"
    assert with_sticky_session("socks5://u:p@h:1/path", "s1") == "socks5://u-time-30-session-s1:p@h:1/path"
    assert with_sticky_session("u:p@h:1", "s1") == "http://u-time-30-session-s1:p@h:1"
    once = with_sticky_session(RESI, "aaa")
    assert with_sticky_session(once, "bbb").count("session-") == 1 and "session-bbb" in once.replace("aaa", "bbb")
    assert with_sticky_session(HOME, "abc") == HOME                     # no user: nothing to pin
    with pytest.raises(ValueError):
        with_sticky_session(RESI, "bad id")


def test_residential_means_a_user_in_the_url_and_masking_hides_it():
    assert is_residential(RESI) and not is_residential(HOME) and not is_residential("") and not is_residential(None)
    assert mask_proxy(RESI) == "http://****@resi-bridge-eu.rainproxy.io:1111"
    assert "p%40ss" not in mask_proxy(RESI) and "user" not in mask_proxy(RESI)
    assert mask_proxy("") == "directo"
    assert len(new_session_id()) == 10 and new_session_id().isalnum() and new_session_id() != new_session_id()


def test_sessions_live_per_video_on_disk_and_expire(tmp_path):
    sessions = ProxySessions(tmp_path, minutes=30, max_rotations=2)
    first = sessions.session_id("dQw4w9WgXcQ")
    assert sessions.session_id("dQw4w9WgXcQ") == first                   # the same video keeps it
    assert sessions.session_id("abcdefghijk") != first                   # another video, another IP
    other = ProxySessions(tmp_path, minutes=30)                          # another process (stage) sees the same one
    assert other.session_id("dQw4w9WgXcQ") == first
    assert sessions.matches("dQw4w9WgXcQ", first) and not sessions.matches("dQw4w9WgXcQ", "zzz")
    saved = json.loads((tmp_path / "dQw4w9WgXcQ" / ".sesion.json").read_text())
    saved["started"] = time.time() - 29 * 60                             # older than the 30 min minus the margin
    (tmp_path / "dQw4w9WgXcQ" / ".sesion.json").write_text(json.dumps(saved))
    assert not other.matches("dQw4w9WgXcQ", first)
    assert other.session_id("dQw4w9WgXcQ") != first                      # ran out: a new one
    assert sessions.session_id("search") == sessions.session_id("search")   # not a video id: memory only
    assert not (tmp_path / "search").exists()


def test_rotation_is_bounded_per_video(tmp_path):
    sessions = ProxySessions(tmp_path, minutes=30, max_rotations=2)
    first = sessions.session_id("dQw4w9WgXcQ")
    second = sessions.rotate("dQw4w9WgXcQ")
    third = sessions.rotate("dQw4w9WgXcQ")
    assert second and third and len({first, second, third}) == 3
    assert sessions.rotate("dQw4w9WgXcQ") is None                        # two rotations: now it is the video
    assert sessions.session_id("dQw4w9WgXcQ") == third and sessions.rotated == 2
    assert sessions.rotate("abcdefghijk")                                # another video has its own count


def test_yt_dlp_and_ffmpeg_leave_with_the_videos_session_through_a_residential_proxy(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    yt._local.video_id = "dQw4w9WgXcQ"
    metadata = yt._ydl({"skip_download": True}).params["proxy"]
    download = yt._ydl({"format": "bv*"}).params["proxy"]
    sid = yt.sessions.session_id("dQw4w9WgXcQ")
    assert metadata == download == f"http://user-time-30-session-{sid}:p%40ss@resi-bridge-eu.rainproxy.io:1111"
    yt._local.video_id = "abcdefghijk"
    assert yt._ydl().params["proxy"] != metadata                        # another video, another session
    assert yt.proxies == [RESI] and yt.base_options["proxy"] == RESI     # pace, budget and quarantine files: the base URL
    yt.close()


def test_a_home_proxy_is_untouched(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=HOME)
    yt._local.video_id = "dQw4w9WgXcQ"
    assert yt._ydl().params["proxy"] == HOME and yt._requests_proxies(0) is None
    assert yt._session_in_use() is None
    yt.close()


def test_the_metadata_proxy_and_plain_gets_use_the_same_session(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.delenv("YOUTUBE_METADATA_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI, metadata_proxy="http://meta:w@gate.example:7000")
    yt._local.video_id = "dQw4w9WgXcQ"
    sid = yt.sessions.session_id("dQw4w9WgXcQ")
    yt._local.via_metadata_proxy = True
    assert yt._ydl().params["proxy"] == f"http://meta-time-30-session-{sid}:w@gate.example:7000"
    assert yt._session_in_use() == sid
    yt._local.via_metadata_proxy = False
    seen = {}

    def get(url, timeout, proxies=None):
        seen["proxies"] = proxies

        class Response:
            status_code = 200
            content = b""

            def raise_for_status(self): ...

        return Response()

    monkeypatch.setattr(yt._sessions[0], "get", get)
    yt._get("https://www.youtube.com/api/timedtext?x=1")
    assert seen["proxies"] == {"http": with_sticky_session(RESI, sid), "https": with_sticky_session(RESI, sid)}
    yt.close()


def test_searches_use_the_shared_session_and_the_metrics_record_it(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI, api_search=False)
    yt.metrics_path = tmp_path / "youtube_downloads.jsonl"
    yt._local.video_id = "dQw4w9WgXcQ"
    seen = []
    monkeypatch.setattr(yt, "_extract", lambda target, extra: seen.append(yt._ydl(extra).params["proxy"]) or {"entries": []})
    yt.search("gymnastics vault")
    assert seen and f"session-{yt.sessions.session_id('search')}:" in seen[0]
    row = json.loads(yt.metrics_path.read_text().splitlines()[-1])
    assert row["action"] == "search" and row["session"] == yt.sessions.session_id("search") and row["video"] is None
    yt.close()


def test_the_ffmpeg_that_fetches_a_range_gets_the_proxy_as_an_option_not_only_the_environment(tmp_path, monkeypatch):
    # ffmpeg ignores the http_proxy environment variable for https:// (libavformat/http.c); only -http_proxy reaches TLS
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    yt._local.video_id = "dQw4w9WgXcQ"
    yt._local.way = 0
    args = yt._ffmpeg_args(exact=True)
    sid = yt.sessions.session_id("dQw4w9WgXcQ")
    assert args["ffmpeg_i"] == ["-loglevel", "error", "-nostats", "-rw_timeout", "60000000", "-http_proxy",
                                f"http://user-time-30-session-{sid}:p%40ss@resi-bridge-eu.rainproxy.io:1111"]
    assert "ffmpeg_o" not in args and yt._ffmpeg_args(exact=False)["ffmpeg_o"] == ["-copyts"]
    home = _source(tmp_path / "h", proxy=HOME)
    home._local.way = 0
    assert home._ffmpeg_args(exact=True)["ffmpeg_i"][-2:] == ["-http_proxy", HOME]      # a home proxy too: same bug
    direct = _source(tmp_path / "d")
    assert "-http_proxy" not in direct._ffmpeg_args(exact=True)["ffmpeg_i"]
    yt.close()


def test_range_downloads_build_their_ffmpeg_arguments_when_they_run(tmp_path, monkeypatch):
    # a home proxy: through a residential one the segments come in-process (test_hls_local) and ffmpeg stays local
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=HOME)
    yt._local.video_id = "dQw4w9WgXcQ"
    info = yt._full_info_path("dQw4w9WgXcQ")
    info.parent.mkdir(parents=True)
    info.write_text(json.dumps({"formats": [{"vcodec": "avc1", "protocol": "m3u8_native", "url": "https://x/expire/9999999999/"}],
                                "_edit_vid3_clients": yt._clients(), "_edit_vid3_via": "", "_edit_vid3_session": None}))
    seen = {}

    class FakeYdl:
        def __init__(self, options):
            seen.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def download_with_info_file(self, path):
            raw = tmp_path / "videos" / "dQw4w9WgXcQ" / "dl_hd_10.00_15.00.mp4"
            raw.write_bytes(b"x")

    monkeypatch.setattr(yt, "_ydl", lambda extra=None: FakeYdl(extra))
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: type("P", (), {"returncode": 0, "stdout": json.dumps(
        {"streams": [{"start_time": "10.0", "height": 720}], "format": {"duration": "5"}})})())
    yt.download_range("dQw4w9WgXcQ", 10, 15, fmt="bv*[height<=720]", prefix="hd")
    ffmpeg_i = seen["external_downloader_args"]["ffmpeg_i"]
    assert ffmpeg_i[ffmpeg_i.index("-http_proxy") + 1] == HOME
    yt.close()


def test_an_ffmpeg_exit_code_is_explained_with_ffmpegs_own_words(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    yt._local.video_id = "dQw4w9WgXcQ"
    yt._local.way = 0
    info = yt._full_info_path("dQw4w9WgXcQ")
    info.parent.mkdir(parents=True)
    info.write_text(json.dumps({"id": "dQw4w9WgXcQ", "formats": [
        {"format_id": "232", "vcodec": "avc1", "protocol": "m3u8_native", "height": 720,
         "url": "https://manifest.googlevideo.com/api/manifest/hls_playlist/expire/9999999999/x",
         "http_headers": {"User-Agent": "UA"}}], "_edit_vid3_clients": yt._clients(), "_edit_vid3_via": "",
        "_edit_vid3_session": yt.sessions.session_id("dQw4w9WgXcQ")}))

    class FakeYdl:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def process_ie_result(self, data, download):
            return {**data, **data["formats"][0]}

    monkeypatch.setattr(yt, "_ydl", lambda extra=None: FakeYdl(extra))
    seen = {}

    def run(command, **kwargs):
        seen["command"], seen["env"] = command, kwargs["env"]
        return subprocess.CompletedProcess(command, 1, "", "[https @ 0x1a] HTTP error 403 Forbidden\n[hls @ 0x2b] Error opening "
                                           "input https://rr1.googlevideo.com/videoplayback/x" + "a" * 500 + "\n")

    monkeypatch.setattr(subprocess, "run", run)
    text = yt._ffmpeg_diagnosis(str(info), "bv*[height<=720][protocol^=m3u8]")
    assert text == "HTTP error 403 Forbidden Error opening input <url>"          # the error, not the signature
    command = seen["command"]
    sticky = with_sticky_session(RESI, yt.sessions.session_id("dQw4w9WgXcQ"))
    assert command[command.index("-http_proxy") + 1] == sticky and seen["env"]["http_proxy"] == sticky
    assert command[command.index("-headers") + 1] == "User-Agent: UA\r\n" and command[-4:] == ["-t", "0.5", "-f", "null", "-"][-4:]
    assert command[command.index("-loglevel") + 1] == "error" and "-nostats" in command

    # a range that dies with an exit code carries the diagnosis in its error
    monkeypatch.setattr(yt, "_call", lambda action, fn, **kw: (_ for _ in ()).throw(RuntimeError("yt-dlp download (HLS): ERROR: ffmpeg exited with code 8")))
    import pytest

    with pytest.raises(RuntimeError, match="code 8 — ffmpeg dice: .*403 Forbidden"):
        yt._fetch_range("dQw4w9WgXcQ", 10, 15, "bv*[height<=720][protocol^=m3u8]", "hd", False, False, info, exact=True)
    yt.close()
