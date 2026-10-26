"""The finished video as a Premiere / DaVinci project (pipeline/export.py): one clip per render segment on V1, the
voice, music and effects on their own tracks, a marker per chapter, and a zip to download."""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")


def _make(path, args):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, str(path)], check=True)


def test_a_rendered_video_exports_with_its_cuts_and_tracks(tmp_path, monkeypatch):
    from pipeline import export, render
    from pipeline.context import RunContext

    ctx = RunContext.create("v", root=tmp_path, config={"video": {"fps": 30, "width": 320, "height": 180},
                                                        "render": {"encoder": "x264"}})
    w = ctx.work_dir
    _make(w / "media" / "a.mp4", ["-f", "lavfi", "-i", "testsrc2=duration=3:size=320x180:rate=30"])
    _make(w / "media" / "b.mp4", ["-f", "lavfi", "-i", "testsrc=duration=3:size=320x180:rate=30"])
    _make(w / "audio" / "voz.wav", ["-f", "lavfi", "-i", "sine=frequency=300:duration=4"])
    _make(w / "audio" / "music.wav", ["-f", "lavfi", "-i", "sine=frequency=200:duration=4"])
    _make(w / "audio" / "pop.wav", ["-f", "lavfi", "-i", "sine=frequency=900:duration=0.2"])
    media = lambda src: {"src": src, "kind": "video", "source": "youtube", "credit": "Fuente: X", "width": 320, "height": 180}  # noqa: E731
    timeline = {"slug": "v", "title": "v", "fps": 30, "width": 320, "height": 180, "durationInFrames": 120,
                "shots": [{"id": "s001", "type": "broll", "from": 0, "durationInFrames": 60, "text": "a", "media": media("media/a.mp4")},
                          {"id": "s002", "type": "broll", "from": 60, "durationInFrames": 60, "text": "b", "media": media("media/b.mp4")}],
                "groups": [], "labels": [],
                "audio": {"voice": "audio/voz.wav", "music": "audio/music.wav", "musicVolume": 0.25, "duckedVolume": 0.05,
                          "speech": [[0, 90]], "sfx": [{"src": "audio/pop.wav", "from": 60, "volume": 0.5}]}}
    ctx.write_json("timeline.json", timeline)
    monkeypatch.setattr(render.Renderer, "badges", lambda self, credits: {})   # drawn by Remotion: not here
    monkeypatch.setattr(render, "graphics_sheet", lambda *a: None)
    render.run(ctx)
    archive = export.export(ctx)
    folder = ctx.out_dir / "premiere"
    root = ET.parse(folder / "timeline.xml").getroot()
    clips = root.findall("./sequence/media/video/track/clipitem")
    assert [(c.findtext("start"), c.findtext("end")) for c in clips] == [("0", "60"), ("60", "120")]
    assert all((folder / c.find("file").findtext("pathurl")).is_file() for c in clips)
    tracks = [t.find("clipitem").findtext("name") for t in root.findall("./sequence/media/audio/track")]
    assert tracks == ["voz.wav", "musica.wav", "efectos.wav", "mezcla-final.wav"]
    with zipfile.ZipFile(archive) as z:
        assert "v-premiere/timeline.xml" in z.namelist() and "v-premiere/LEEME.txt" in z.namelist()
