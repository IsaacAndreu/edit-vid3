"""content.official_channels: the publisher's own uploads pass the video-game and «official trailer» filters."""

from pipeline.sourcing.common import blocked_by_title


def test_video_game_trailer_blocked_by_default():
    assert blocked_by_title("GTA 6 Official Trailer", "Rockstar Games")


def test_official_channel_passes_whatever_the_title():
    official = ["Rockstar Games"]
    assert blocked_by_title("GTA 6 Official Trailer", "Rockstar Games", None, official) is None
    assert blocked_by_title("GTA 6 Official Trailer", " rockstar games ", None, official) is None


def test_lookalike_channel_is_still_blocked():
    official = ["Rockstar Games"]
    assert blocked_by_title("GTA 6 Official Trailer", "Rockstar Games Fan", None, official)
    assert blocked_by_title("GTA 6 gameplay", "JULEX", None, official) == "gta"
