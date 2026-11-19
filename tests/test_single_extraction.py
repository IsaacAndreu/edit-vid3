"""Through a residential proxy a video is extracted once per sticky session: its info dict feeds every range."""

import json
import time

from pipeline.sourcing.youtube import YouTubeSource

RESI = "http://user:pass@resi-bridge-eu.rainproxy.io:1111"
META = "http://meta:w@gate.example:7000"
VIDEO = "dQw4w9WgXcQ"


def _source(tmp_path, **cfg):
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", **cfg})


def _data(expire_in=6 * 3600):
    return {"title": "t", "channel": "c", "formats": [
        {"format_id": "18", "vcodec": "avc1", "height": 720, "url": f"https://x/videoplayback?expire={int(time.time() + expire_in)}"}]}


def test_one_extraction_by_the_videos_session_serves_metadata_and_downloads(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.delenv("YOUTUBE_METADATA_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI, metadata_proxy=META)
    seen = []
    monkeypatch.setattr(yt, "_extract", lambda url, extra: seen.append(yt._ydl(extra).params["proxy"]) or _data())
    yt.info(VIDEO)
    sid = yt.sessions.session_id(VIDEO)
    assert seen == [f"http://user-time-30-session-{sid}:pass@resi-bridge-eu.rainproxy.io:1111"]   # not the metadata proxy
    full = json.loads(yt._full_info_path(VIDEO).read_text())
    assert full["_edit_vid3_via"] == "" and full["_edit_vid3_session"] == sid
    assert yt._fresh_full_info(VIDEO) == yt._full_info_path(VIDEO)
    assert len(seen) == 1 and yt._local.info_reused is True                 # the download reuses it: no extraction
    yt.close()


def test_a_dead_session_or_urls_near_expiry_mean_one_new_extraction(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    seen = []
    monkeypatch.setattr(yt, "_extract", lambda url, extra: seen.append(1) or _data())
    yt.info(VIDEO)
    path = tmp_path / "videos" / VIDEO / ".sesion.json"
    saved = json.loads(path.read_text())
    saved["started"] = time.time() - 29 * 60                 # the 30 min are over: another IP now
    path.write_text(json.dumps(saved))
    assert yt._fresh_full_info(VIDEO) and len(seen) == 2 and yt._local.info_reused is False
    full = json.loads(yt._full_info_path(VIDEO).read_text())
    assert full["_edit_vid3_session"] == yt.sessions.session_id(VIDEO)      # stamped with the new session
    assert yt._fresh_full_info(VIDEO) and len(seen) == 2                    # and reused from then on

    monkeypatch.setattr(yt, "_extract", lambda url, extra: seen.append(1) or _data(expire_in=10 * 60))
    yt._full_info_path(VIDEO).unlink()
    yt._fresh_full_info(VIDEO)                                              # 3: URLs expiring in 10 min (< 15 margin)
    yt._fresh_full_info(VIDEO)                                              # 4: never reused that close to expiry
    assert len(seen) == 4
    yt.close()


def test_a_home_proxy_keeps_reusing_its_fixed_ip_info_as_before(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy="http://100.64.0.2:8899")
    seen = []
    monkeypatch.setattr(yt, "_extract", lambda url, extra: seen.append(1) or _data())
    yt.info(VIDEO)
    assert json.loads(yt._full_info_path(VIDEO).read_text())["_edit_vid3_session"] is None
    assert yt._fresh_full_info(VIDEO) and len(seen) == 1 and not yt.residential
    yt.close()


def test_a_home_way_with_a_residential_metadata_proxy_still_extracts_twice(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.delenv("YOUTUBE_METADATA_PROXY", raising=False)
    yt = _source(tmp_path, proxy="http://100.64.0.2:8899", metadata_proxy=META)
    seen = []
    monkeypatch.setattr(yt, "_extract", lambda url, extra: seen.append(yt._ydl(extra).params["proxy"]) or _data())
    yt.info(VIDEO)
    assert "gate.example" in seen[0]                                        # metadata by the metadata proxy, as before
    yt._fresh_full_info(VIDEO)
    assert seen[1] == "http://100.64.0.2:8899" and len(seen) == 2           # the download's URLs: from home
    yt.close()


def test_expired_links_keep_the_metadata_until_the_new_extraction_replaces_it(tmp_path, monkeypatch):
    """Fase 3.2: only the stream links expired, so info.json (title, storyboard, HLS flag…) is not deleted first: a
    failed re-extraction leaves it, and a shot that waited for the video's lock while another re-extracted reuses
    those fresh links instead of extracting again."""

    import pytest

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    seen = []
    monkeypatch.setattr(yt, "_extract", lambda url, extra: seen.append(1) or _data(expire_in=10 * 60))
    yt.info(VIDEO)
    meta = yt._info_path(VIDEO)
    before = json.loads(meta.read_text())

    def refused(url, extra):
        raise RuntimeError("ERROR: [youtube] x: Sign in to confirm you're not a bot")

    monkeypatch.setattr(yt, "_extract", refused)
    with pytest.raises(Exception):
        yt._fresh_full_info(VIDEO)                        # links 10 min from expiry: a new extraction, which fails
    assert json.loads(meta.read_text()) == before          # the metadata is still there
    assert yt._local.refresh_links is False

    monkeypatch.setattr(yt, "_extract", lambda url, extra: seen.append(1) or _data())
    yt._fresh_full_info(VIDEO)
    after = json.loads(meta.read_text())
    assert len(seen) == 2 and after["title"] == "t" and after["fetchedAt"] >= before["fetchedAt"]
    yt._local.refresh_links = True                        # as a second shot that waited for the lock would arrive
    try:
        yt.info(VIDEO)
    finally:
        yt._local.refresh_links = False
    assert len(seen) == 2                                 # the links are fresh now: no third extraction
    yt.close()
