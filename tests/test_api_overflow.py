"""«Que el clip sea…» 9: with api_overflow: mixto the searches left after the quota go by yt-dlp, under their own
hourly cap, instead of the video waiting for tomorrow."""

from __future__ import annotations

from pipeline.sourcing.youtube import YouTubeSource


def test_mixed_mode_searches_by_ytdlp_under_its_own_cap(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                  "api_overflow": "mixto", "overflow_searches_per_hour": 2})
    yt.api_exhausted = True
    monkeypatch.setattr(yt, "_extract", lambda target, extra: {"entries": [{"id": "abcdefghijk", "title": "t"}]})
    yt.search("first")
    yt.search("second")
    assert yt._overflow_budget.used() == 2                 # both counted against the cap
    yt.search("first")                                      # cached: not asked, not counted
    assert yt._overflow_budget.used() == 2
    yt.close()
