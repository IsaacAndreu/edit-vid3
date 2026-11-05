"""The PO Token stays on through a residential proxy (only a home proxy's IP needs none)."""

import importlib.util

from pipeline.sourcing import youtube as yt_module
from pipeline.sourcing.youtube import YouTubeSource

RESI = "http://user:pass@resi-bridge-eu.rainproxy.io:1111"
HOME = "http://100.64.0.2:8899"


class Ok:
    ok = True


def test_po_token_is_used_through_a_residential_proxy_and_not_through_home(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr("requests.Session.get", lambda self, url, timeout=3: Ok())
    resi = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"po_token": "auto", "proxy": RESI})
    assert resi.pot and resi.base_options["extractor_args"]["youtubepot-bgutilhttp"] == {"base_url": ["http://127.0.0.1:4416"]}
    home = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"po_token": "auto", "proxy": HOME})
    assert home.pot is False and "youtubepot-bgutilhttp" not in (home.base_options.get("extractor_args") or {})
    off = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"po_token": "off", "proxy": RESI})
    assert off.pot is False


def test_a_silent_provider_is_reported_once_and_the_run_goes_on(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    def down(self, url, timeout=3):
        raise __import__("requests").RequestException("connection refused")

    monkeypatch.setattr("requests.Session.get", down)
    monkeypatch.setattr(yt_module, "_POT_WARNED", False)
    first = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"po_token": "auto", "proxy": RESI})
    second = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"po_token": "auto", "proxy": RESI})
    out = capsys.readouterr().out
    assert first.pot is False and second.pot is False
    assert out.count("AVISO PO Token") == 1 and "no responde" in out and "sigo sin PO Token" in out
    assert "pass" not in out                                   # never a credential on screen
