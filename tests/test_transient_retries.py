"""Fase 1.5: at home or straight from the server, a passing error is retried twice before the candidate is lost;
«are you a bot» and 429 never; the first 429 gives back the extra slots of several accounts."""

from __future__ import annotations

import pytest

from pipeline.sourcing import youtube as yt_module
from pipeline.sourcing.youtube import YouTubeSource


def _source(tmp_path, monkeypatch, **cfg):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr(yt_module.time, "sleep", lambda s: None)
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                  "requests_per_hour": 0, **cfg})


def test_a_passing_error_is_retried(tmp_path, monkeypatch):
    yt = _source(tmp_path, monkeypatch)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))")
        return "ok"

    assert yt._call("metadata", flaky) == "ok" and len(calls) == 3
    yt.close()


def test_it_gives_up_after_two_more_and_never_retries_a_bot_check(tmp_path, monkeypatch):
    yt = _source(tmp_path, monkeypatch)
    calls = []

    def always(message):
        def fn():
            calls.append(message)
            raise RuntimeError(message)
        return fn

    with pytest.raises(RuntimeError):
        yt._call("metadata", always("HTTP Error 503: Service Unavailable"))
    assert len(calls) == 3
    calls.clear()
    yt._local.video_id = "dQw4w9WgXcQ"
    with pytest.raises(RuntimeError):
        yt._call("metadata", always("Sign in to confirm you’re not a bot"))
    assert len(calls) == 1
    yt.close()


def test_the_first_429_gives_back_the_extra_slots(tmp_path, monkeypatch):
    sets = [(f"# cookies {n}", None) for n in range(3)]
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "requests_per_hour": 0},
                       cookie_sets=sets)
    calmed = []
    monkeypatch.setattr(yt, "_calm_down", lambda: calmed.append(1))
    with pytest.raises(RuntimeError):
        yt._call("search", lambda: (_ for _ in ()).throw(RuntimeError("HTTP Error 429: Too Many Requests")))
    assert calmed
    yt.close()
