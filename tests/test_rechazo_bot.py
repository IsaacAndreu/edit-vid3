"""A video that answered «are you a bot» through the paid proxy is not paid again by every shot that picked it: for
its refusal's hours (refused_hours_residential) the shots go to their next candidate without asking YouTube."""

from __future__ import annotations

import pytest

from pipeline.sourcing.youtube import Refused
from tests.test_hls_local import VIDEO, _source


def test_a_bot_refusal_through_the_paid_proxy_is_not_asked_again_by_the_next_shots(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path)
    asked = []
    monkeypatch.setattr(yt, "_fresh_full_info", lambda video_id: asked.append(video_id) or tmp_path / "info.json")
    yt._refuse(VIDEO, "bot")
    for start in (10.0, 30.0, 50.0):                       # three shots that picked the same video
        with pytest.raises(Refused):
            yt.download_range(VIDEO, start, start + 4, fmt="bv*[height<=1080]", prefix="hd")
    assert asked == []                                     # no extraction paid, no download tried


def test_after_its_hours_the_video_can_be_asked_again(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, refused_hours_residential=0)
    yt._refuse(VIDEO, "bot")
    assert yt.refused_why(VIDEO) is None
