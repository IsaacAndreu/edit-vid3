"""«Lo que dicen estos datos» 5 and fase 1.7: subtitles that failed are not asked again per option and per shot, and
they have their own pace."""

from __future__ import annotations

import json

from pipeline.sourcing.youtube import YouTubeSource

VIDEO = "dQw4w9WgXcQ"


class Reply:
    def __init__(self, status, text="{}"):
        self.status_code, self.text, self.content = status, text, text.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP Error {self.status_code}")


def test_a_429_is_remembered_for_a_while(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                  "captions_min_interval": 0})
    monkeypatch.setattr(yt, "info", lambda vid: {"captions": {"en": "https://www.youtube.com/api/timedtext?v=x"}})
    asked = []
    monkeypatch.setattr(yt, "_get", lambda url, timeout=30: asked.append(url) or Reply(429))
    assert yt.captions(VIDEO) == [] and yt.captions(VIDEO) == [] and yt.captions(VIDEO) == []
    assert len(asked) == 1
    saved = json.loads((tmp_path / "videos" / VIDEO / "captions.fallo.json").read_text())
    assert "429" in saved["error"] and saved["until"] > 0
    yt.close()


def test_good_captions_are_cached_as_before(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                  "captions_min_interval": 0})
    monkeypatch.setattr(yt, "info", lambda vid: {"captions": {"en": "https://www.youtube.com/api/timedtext?v=x"}})
    body = json.dumps({"events": [{"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "hola"}]}]})
    asked = []
    monkeypatch.setattr(yt, "_get", lambda url, timeout=30: asked.append(url) or Reply(200, body))
    assert yt.captions(VIDEO) == [(1.0, 3.0, "hola")]
    assert yt.captions(VIDEO) == [(1.0, 3.0, "hola")] and len(asked) == 1
    yt.close()
