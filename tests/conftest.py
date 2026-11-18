"""Shared fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def fake_media_ok(monkeypatch):
    """For tests whose ffmpeg is a double writing a few bytes: the ffprobe check of a finished clip
    (pipeline/fileio.py) passes. The check itself is tested with real files in tests/test_fileio.py."""

    from pipeline import fileio
    from pipeline.sourcing import youtube

    monkeypatch.setattr(fileio, "media_problem", lambda *a, **k: None)
    monkeypatch.setattr(youtube, "media_problem", lambda *a, **k: None)
