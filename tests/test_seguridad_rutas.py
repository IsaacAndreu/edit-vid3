"""Names that come from a URL never leave their folder: a partner reaches only their own videos' files."""

from __future__ import annotations

import json

import pytest

from pipeline import web
from pipeline.context import find_video, safe_name
from tests.test_socios import studio  # noqa: F401  (fixture)


def test_names_are_one_part_of_a_path():
    for good in ("pati3.24.4", "_radar", "top-5-momentos", "newgym3-ideas4", "AtlasAltiplano"):
        assert safe_name(good) == good
    for bad in ("..", ".", ".env", "../x", "a/b", "a\\b", "x\x00", "", "a\nb"):
        with pytest.raises(ValueError):
            safe_name(bad)


def test_find_video_refuses_a_name_that_leaves_materiales(tmp_path):
    with pytest.raises(ValueError):
        find_video(tmp_path, "../out")
    with pytest.raises(ValueError):
        find_video(tmp_path, "..")


def test_a_partner_reads_nothing_outside_their_videos(studio):          # noqa: F811
    root, call, login = studio
    (root / ".env").write_text("SECRETO=1\n")
    assert login("contraseña-amigo") == 200
    for path in ("/files/..%2F.env", "/files/suyo1/..%2F..%2F.env", "/files/suyo1/%2E%2E/%2E%2E/.env",
                 "/files/%2E%2E/.env", "/api/video/..%2Fmio1", "/api/video/%2E%2E%2Fatletismo%2Fsuyo1",
                 "/api/review/..%2F..%2Fout"):
        code, body, _ = call(path)
        assert code in (400, 403, 404), path
        assert b"SECRETO" not in body, path
    assert call("/files/suyo1/video-final.mp4")[0] == 200                  # their own file still opens


def test_moving_a_channel_only_touches_a_real_video(studio):            # noqa: F811
    root, call, login = studio
    login("contraseña-amigo")
    for slug in ("..%2Fmateriales", "%2E%2E", "..", "atletismo"):
        call(f"/api/video/{slug}/channel", {"channel": "atletismo"})
    assert not (root / "materiales" / "config.yaml").exists()
    assert web._channel_of(root, find_video(root, "mio1")) == "aviacion"     # the owner's video stays theirs
    with pytest.raises(FileNotFoundError):
        web.set_channel(root, "atletismo", "aviacion")                       # a channel group is not a video
