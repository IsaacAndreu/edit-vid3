"""Fase 1.8: images keep a pace per host (Wikimedia's robot policy only there), downloads retry passing errors, and
the YouTube Data API retries a network error giving the quota back."""

from __future__ import annotations

import json

import pytest
import requests

from pipeline.sourcing import common
from pipeline.sourcing.common import HostPacers, download_file
from tests.test_lab import FakeYouTube, _api


def test_one_pace_per_host():
    pacers = HostPacers(default=0.25, slow=1.0)
    wiki = pacers.for_url("https://upload.wikimedia.org/a.jpg")
    other = pacers.for_url("https://images.pexels.com/b.jpg")
    assert wiki is not other and wiki._min_interval == 1.0 and other._min_interval == 0.25
    assert pacers.for_url("https://upload.wikimedia.org/c.jpg") is wiki


class Reply:
    def __init__(self, status, body=b"img"):
        self.status_code, self._body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, size):
        yield self._body


def test_download_file_retries_a_5xx_and_not_a_404(tmp_path, monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    replies = iter([Reply(503), Reply(200)])

    class Session:
        def get(self, url, **kw):
            return next(replies)

    assert download_file(Session(), "https://x/a.jpg", tmp_path / "a.jpg").read_bytes() == b"img"

    class Missing:
        calls = 0

        def get(self, url, **kw):
            Missing.calls += 1
            return Reply(404)

    with pytest.raises(requests.HTTPError):
        download_file(Missing(), "https://x/b.jpg", tmp_path / "b.jpg")
    assert Missing.calls == 1


def test_the_api_gives_the_quota_back_when_google_never_answered(tmp_path, monkeypatch):
    from pipeline import ytapi

    monkeypatch.setattr(ytapi.time, "sleep", lambda s: None)
    fake = FakeYouTube()
    fails = {"n": 2}
    real_get = fake.get

    def flaky(url, params, timeout=0):
        if fails["n"]:
            fails["n"] -= 1
            raise requests.ConnectionError("reset")
        return real_get(url, params, timeout)

    fake.get = flaky
    api = _api(tmp_path, fake, keys="k1")
    assert api.search("q", max_results=3)
    ledger = json.loads((api.dir / "quota.json").read_text())
    assert sum(ledger["used"].values()) == 100 and sum(ledger["searches"].values()) == 1   # paid once, not three times
