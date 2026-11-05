"""Through a residential proxy the player clients can be narrowed (player_client_residential); by default they are
the same as everywhere: web_safari alone made every extraction fail «Requested format is not available»."""

import json

from pipeline.sourcing.youtube import YouTubeSource

RESI = "http://user:pass@resi-bridge-eu.rainproxy.io:1111"
HOME = "http://100.64.0.2:8899"
BOTH = ["default", "web_safari"]


def _source(tmp_path, **cfg):
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", "player_client": BOTH, **cfg})


def test_residential_clients_default_to_the_usual_list_and_can_be_narrowed(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    resi = _source(tmp_path, proxy=RESI)
    assert resi.base_options["extractor_args"]["youtube"]["player_client"] == BOTH
    assert resi.clients == BOTH and resi._clients() == BOTH
    custom = _source(tmp_path, proxy=RESI, player_client_residential=["web_safari"])
    assert custom.clients == ["web_safari"] and custom._clients() == ["web_safari"]
    assert _source(tmp_path, proxy=HOME, player_client_residential=["web_safari"]).clients == BOTH   # home: ignored
    home = _source(tmp_path, proxy=HOME)
    direct = _source(tmp_path)
    assert home.clients == BOTH and direct.clients == BOTH and home._clients() == BOTH


def test_info_from_other_clients_is_extracted_again_once(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI, player_client_residential=["web_safari"])
    path = yt._full_info_path("vid00000000")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"formats": [{"vcodec": "avc1", "url": "https://x/videoplayback?expire=9999999999"}],
                                "_edit_vid3_clients": BOTH, "_edit_vid3_via": "", "_edit_vid3_session": yt.sessions.session_id("vid00000000")}))
    extracted = []
    monkeypatch.setattr(yt, "info", lambda vid: extracted.append(vid))
    yt._fresh_full_info("vid00000000")
    assert extracted == ["vid00000000"]                      # stamped with other clients: one new extraction
