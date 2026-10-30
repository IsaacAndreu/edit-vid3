from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.youtube_probe import _download_range, _format_for_height


def test_format_for_height_reuses_existing_360_format() -> None:
    source = SimpleNamespace(SECTION_FORMAT="section-format")

    assert _format_for_height(source, 360) == ("section-format", "a360")


def test_format_for_height_limits_larger_downloads() -> None:
    source = SimpleNamespace(SECTION_FORMAT="section-format")

    fmt, prefix = _format_for_height(source, 720)

    assert "height<=720" in fmt
    assert prefix == "a720"


def test_download_range_is_capped_at_video_duration() -> None:
    assert _download_range({"duration": 7}, 0, 10) == (0, 7)


def test_download_range_rejects_start_after_duration() -> None:
    with pytest.raises(ValueError, match="queda fuera"):
        _download_range({"duration": 7}, 8, 2)
