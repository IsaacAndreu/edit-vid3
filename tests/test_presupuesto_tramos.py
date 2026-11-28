"""The hourly budget can charge less to a range that reuses an extraction (only media bytes, no page or player):
`reused_download_units`, off (3, as every download)."""

from __future__ import annotations

from tests.test_hls_local import _source


def test_a_range_reusing_its_extraction_costs_what_is_set(tmp_path):
    yt = _source(tmp_path, reused_download_units=1)
    yt._local.info_reused = True
    assert yt._units("download (HLS)") == 1 and yt._units("download (rango)") == 1
    assert yt._units("download (completo)") == 8                       # a whole file is no small range
    yt._local.info_reused = False                                      # a fresh extraction: the full price
    assert yt._units("download (HLS)") == 3
    assert yt._units("metadata") == 4


def test_off_by_default_every_download_costs_3(tmp_path):
    yt = _source(tmp_path)
    yt._local.info_reused = True
    assert yt._units("download (HLS)") == 3
    broken = _source(tmp_path, reused_download_units="mucho")
    broken._local.info_reused = True
    assert broken._units("download (HLS)") == 3                        # a wrong setting never breaks a download
