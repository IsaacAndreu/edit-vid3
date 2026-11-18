"""«Lo que dicen estos datos» 6: player_skip reaches yt-dlp (off by default) and its probe compares both ways."""

from __future__ import annotations

from pipeline import sonda_ytcfg
from pipeline.sourcing.youtube import YouTubeSource


def test_off_by_default_and_passed_through(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    plain = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"player_client": ["default", "web_safari"]})
    assert "player_skip" not in plain.base_options["extractor_args"]["youtube"]
    skip = YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                         config={"player_client": ["default", "web_safari"], "player_skip": ["configs"]})
    assert skip.base_options["extractor_args"]["youtube"] == {"player_client": ["default", "web_safari"],
                                                             "player_skip": ["configs"]}
    plain.close()
    skip.close()


def test_the_probe_says_whether_formats_match():
    same = [{"video": "a", "skip": "—", "formats": 30, "hls": 6, "maxHeight": 1080, "avc720": True},
            {"video": "a", "skip": "configs", "formats": 30, "hls": 6, "maxHeight": 1080, "avc720": True}]
    assert "se puede encender" in sonda_ytcfg.markdown(same)
    fewer = [same[0], {**same[1], "hls": 0}]
    assert "déjalo apagado" in sonda_ytcfg.markdown(fewer)
