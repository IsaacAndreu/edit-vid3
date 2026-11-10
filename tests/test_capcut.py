import json
import shutil
import subprocess
import zipfile

import pytest

from pipeline import capcut
from pipeline.context import RunContext

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@needs_ffmpeg
def test_a_finished_video_becomes_clean_pieces_and_loose_tracks_for_capcut(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    ctx = RunContext.create("v", root=tmp_path, config={"video": {"fps": 30}})
    work, out = ctx.work_dir, ctx.out_dir
    (work / "media").mkdir(parents=True)
    (work / "audio").mkdir()
    out.mkdir(parents=True)
    _ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4", str(work / "media" / "s001.mp4"))
    _ff("-f", "lavfi", "-i", "color=c=red:size=800x600", "-frames:v", "1", str(work / "media" / "s002.jpg"))
    _ff("-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=10", "-f", "lavfi", "-i", "sine=f=300:duration=10",
        "-shortest", str(out / "video-final.mp4"))
    for name, f in (("voz.mp3", 200), ("cancion1.mp3", 400), ("cancion2.mp3", 500), ("whoosh.mp3", 900)):
        _ff("-f", "lavfi", "-i", f"sine=f={f}:duration=10", str(work / "audio" / name))
    timeline = {
        "fps": 30, "durationInFrames": 300, "width": 1920, "height": 1080,
        "shots": [
            {"id": "s000", "type": "chapter", "from": 0, "durationInFrames": 30, "text": "", "chapterTitle": "Uno"},
            {"id": "s001", "type": "broll", "from": 30, "durationInFrames": 90, "text": "Ella salta.",
             "media": {"src": "media/s001.mp4", "kind": "video", "source": "youtube"}},
            {"id": "s002", "type": "broll", "from": 120, "durationInFrames": 60, "text": "Su foto.",
             "media": {"src": "media/s002.jpg", "kind": "image", "source": "wikimedia"}},
            {"id": "s003", "type": "broll", "from": 180, "durationInFrames": 60, "text": "Los números.", "groupId": "g1"},
            {"id": "s004", "type": "broll", "from": 240, "durationInFrames": 60, "text": "Más números.", "groupId": "g1"}],
        "groups": [{"id": "g1", "kind": "stat", "from": 180, "durationInFrames": 120}],
        "labels": [{"kind": "name", "text": "SIMONE BILES", "from": 40, "durationInFrames": 60}],
        "audio": {"voice": "audio/voz.mp3", "voiceFrom": 0, "clips": [], "music": "audio/cancion1.mp3",
                  "musicParts": [{"src": "audio/cancion1.mp3", "from": 0, "durationInFrames": 150},
                                 {"src": "audio/cancion2.mp3", "from": 150, "durationInFrames": 150}],
                  "musicVolume": 0.2, "duckedVolume": 0.05, "speech": [[30, 200]],
                  "sfx": [{"src": "audio/whoosh.mp3", "from": 120, "volume": 0.3}], "voiceGaps": []}}
    (work / "timeline.json").write_text(json.dumps(timeline))
    archive = capcut.export(ctx)
    folder = out / "capcut"
    names = sorted(p.name for p in (folder / "1_video").iterdir())
    assert names == ["001_capitulo.mp4", "002_clip.mp4", "003_foto.mp4", "004_grafico.mp4"]   # the two shots of g1: one piece
    assert sorted(p.name for p in (folder / "2_audio").iterdir())[0] == "0_mezcla_final.wav"
    assert {"1_voz.wav", "2_musica.wav", "3_efectos.wav"} <= {p.name for p in (folder / "2_audio").iterdir()}
    assert sorted(p.name for p in (folder / "3_musica_original").iterdir()) == ["00m00s000_01_cancion1.mp3", "00m05s000_02_cancion2.mp3"]
    assert [p.name for p in (folder / "4_efectos_sueltos").iterdir()] == ["00m04s000_whoosh.mp3"]
    assert "SIMONE BILES" in (folder / "rotulos.srt").read_text() and "00:00:01,333 --> 00:00:03,333" in (folder / "rotulos.srt").read_text()
    seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(folder / "1_video" / "004_grafico.mp4")], capture_output=True, text=True).stdout)
    assert abs(seconds - 4.0) < 0.1                                                    # its stretch, exactly
    assert zipfile.ZipFile(archive).namelist()                                        # and the download
