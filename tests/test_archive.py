"""Public-domain historical footage (pipeline/sourcing/archive.py): only for old stretches, only free collections,
a local preview that becomes the storyboard and the 360p windows, the final clip cut from the original."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.schemas import Shot
from pipeline.sourcing import archive

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")


def _shot(text: str, queries: list[str], entities: list[str], preferred: str = "medium") -> Shot:
    return Shot.model_validate({
        "id": "s010", "type": "broll", "startWord": 0, "endWord": 3, "start": 0.0, "end": 3.0, "text": text,
        "chapter": 0, "broll": {"visualIntent": "archive footage", "queriesEn": [*queries, "old film", "newsreel"][:3], "queriesEs": ["patinaje"],
                                "entities": entities, "mustContain": [], "avoid": [], "preferredShot": preferred}})


def test_only_old_stretches_ask_for_archive_footage():
    assert archive.historical(_shot("Sonja Henie ganó en 1936.", ["Sonja Henie 1936 Olympics"], ["Sonja Henie"]))
    assert archive.historical(_shot("Ganó otra vez.", ["figure skating"], [], preferred="archive"))
    assert not archive.historical(_shot("Malinin cayó en 2026.", ["Malinin fall 2026"], ["Ilia Malinin"]))


class _Response:
    def __init__(self, payload=None, content=b"", headers=None):
        self.payload, self.content, self.headers, self.status_code = payload, content, headers or {}, 200

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_newsreel_becomes_a_candidate_with_storyboard_and_windows(tmp_path):
    film = tmp_path / "film.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=20:size=640x480:rate=25", str(film)], check=True)
    docs = [{"identifier": "henie1936", "title": "Sonja Henie wins 1936", "collection": ["universal_newsreels"]},
            {"identifier": "tvnews1", "title": "Sonja Henie remembered", "collection": ["tvarchive"]},
            {"identifier": "other", "title": "Ice hockey 1936", "collection": ["prelinger"]}]
    meta = {"files": [{"name": "henie_512kb.mp4", "size": "1000", "length": "20.0"},
                      {"name": "henie.mp4", "size": "9000", "length": "20.0"}]}

    class Session:
        headers: dict = {}

        def get(self, url, params=None, stream=False, **_):
            if "advancedsearch" in url:
                return _Response({"response": {"docs": docs}})
            if "/metadata/" in url:
                return _Response(meta)
            if "commons" in url:
                return _Response({"query": {"pages": {}}})
            return _Response(content=film.read_bytes())

        def head(self, url, **_):
            return _Response(headers={"Content-Length": str(film.stat().st_size)})

    source = archive.ArchiveSource(root=tmp_path, cache_dir=tmp_path / "cache", config={"commons_min_interval": 0,
                                   "archive_min_interval": 0}, session=Session())
    source.pacers = {k: type("P", (), {"wait": lambda self: None})() for k in source.pacers}
    shot = _shot("Sonja Henie ganó en 1936.", ["Sonja Henie 1936 Olympics"], ["Sonja Henie"])
    notes: list[str] = []
    queries, found = source.search(shot.broll, notes)
    assert [c.id for c in found] == ["ar:henie1936"] and not notes        # no TV recording, no one else's newsreel
    c = found[0]
    assert c.source == "archive" and c.kind == "video" and c.license == "public domain" and c.credit == "Fuente: Internet Archive"
    assert c.mediaUrl.endswith("/henie.mp4") and (tmp_path / c.previewPath).is_file()
    assert c.storyboard.frames >= 9 and all((tmp_path / s).is_file() for s in c.storyboard.sheets)
    window = archive.cut(tmp_path / c.previewPath, 4.0, 9.0, tmp_path / "w" / "a360_4.00_9.00.mp4", height=360)
    seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(window)],
                                   capture_output=True, text=True).stdout)
    assert abs(seconds - 5.0) < 0.3
