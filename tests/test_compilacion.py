"""Long compilations (pipeline/compilacion.py)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipeline import compilacion
from test_agenda import _site, _video


def _final(root: Path, slug: str, seconds: int, end_screen: int = 5) -> None:
    out = root / "out" / slug
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=duration={seconds}", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", str(out / "video-final.mp4")], check=True)
    work = root / "work" / slug
    work.mkdir(parents=True, exist_ok=True)
    (work / "timeline.json").write_text(json.dumps({"fps": 30, "endscreenFrames": end_screen * 30}))


def test_three_videos_become_one_with_cards_and_chapters(tmp_path: Path, monkeypatch):
    root = _site(tmp_path)
    for n in (1, 2, 3):
        _video(root, "negocios", f"n{n}", done=True)
        (root / "materiales" / "negocios" / f"n{n}" / "titulo.txt").write_text(f"Caso {n}", encoding="utf-8")
        _final(root, f"n{n}", 70)
    _video(root, "gimnasia", "g1", done=True)
    _final(root, "g1", 70)
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **kw: {
        "titles": ["3 CASOS SEGUIDOS"], "description": "Tres historias.", "card": "TRES CASOS"})
    slug = compilacion.build(root, "negocios", log=lambda *_: None)
    final = root / "out" / slug / "video-final.mp4"
    expected = compilacion.TITLE_SECONDS + 3 * (compilacion.CARD_SECONDS + 65)
    assert abs(compilacion._duration(final) - expected) < 1.5
    text = (root / "out" / slug / "youtube.txt").read_text("utf-8")
    assert "1. 3 CASOS SEGUIDOS" in text and "0:00 Intro" in text and "1:12 2. Caso" in text
    folder = root / "materiales" / "negocios" / slug
    assert "compilation" in (folder / "config.yaml").read_text("utf-8")
    assert compilacion.candidates(root, "negocios") == []                  # used: not twice
    from pipeline import agenda

    assert next(v for v in agenda.videos(root) if v["slug"] == slug)["status"] == "hecho"
    with pytest.raises(RuntimeError):
        compilacion.build(root, "gimnasia", log=lambda *_: None)            # one video is not a compilation
