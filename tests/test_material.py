"""Material de partida (bloque 4, first part): the links, channels and own clips given to a video, taken first by
the search; your clips have no third-party cap nor credit; the studio saves them, holds the video while they upload."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import material, web
from pipeline.context import RunContext

sys.path.insert(0, str(Path(__file__).parent))
from test_web import SCRIPT, _project  # noqa: E402


def test_links_and_channels_are_read_from_whatever_is_pasted():
    pasted = ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10\nhttps://youtu.be/aaaaaaaaaaa  "
              "https://www.youtube.com/shorts/bbbbbbbbbbb, dQw4w9WgXcQ\nnot a link")
    assert material.video_ids(pasted) == ["dQw4w9WgXcQ", "aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert material.channel_refs("https://www.youtube.com/@Rockstar/videos\n@IGN\nhttps://youtube.com/channel/"
                                 "UCabcdefghijklmnopqrstuv x") == ["@Rockstar", "@IGN", "UCabcdefghijklmnopqrstuv"]
    assert material.clip_name("Mi partida (1).MP4") == "Mi-partida-1.mp4"
    with pytest.raises(ValueError):
        material.clip_name("notas.txt")


def _clip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:r=30:d=6", "-pix_fmt", "yuv420p",
                    str(path)], check=True)


def test_the_video_and_its_channel_material_together_and_your_clips_as_candidates(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    folder = tmp_path / "materiales" / "gta" / "v"
    material.save(folder, videos="https://youtu.be/aaaaaaaaaaa", channels="@mine")
    material.save(tmp_path / "materiales" / "gta", channels="@IGN")
    _clip(folder / material.CLIPS_DIR / "vice-beach.mp4")
    _clip(folder / material.CLIPS_DIR / "atraco.mp4")
    material.save(folder, clips={"vice-beach.mp4": "Vice Beach de noche persecución", "atraco.mp4": "atraco al banco"})
    ctx = RunContext.create("v", root=tmp_path)
    gathered = material.gather(ctx)
    assert gathered["videos"] == ["aaaaaaaaaaa"] and gathered["channels"] == ["@mine", "@IGN"]
    assert [p.name for p, _ in gathered["clips"]] == ["atraco.mp4", "vice-beach.mp4"]

    asked = []

    def candidate(vid, entry, score, notes):
        asked.append(vid)
        return None                                        # nothing usable from YouTube here: only your clips stay

    api = SimpleNamespace(channel=lambda ref: {"uploads": f"UU{ref}"}, uploads=lambda pl, count: [
        {"id": "ccccccccccc", "title": "GTA 6 Vice Beach night chase", "duration": 300, "live": "none", "views": 10}])
    youtube = SimpleNamespace(candidate=candidate, api=api)
    mine = material.Material(ctx, youtube)
    shot = SimpleNamespace(text="Una persecución de noche en Vice Beach", broll=None, idea=None)
    found = mine.for_shot(shot, [])
    assert [c.source for c in found] == ["propio", "propio"]
    assert found[0].title == "Vice Beach de noche persecución"             # the clip whose tags match comes first
    assert found[0].credit == "Fuente: material propio" and material.chosen_material(found[0])
    assert asked == ["aaaaaaaaaaa", "ccccccccccc"]                         # the pasted video, then the channel's match
    before = mine.signature()
    material.save(folder, clips={"atraco.mp4": "atraco al banco de Vice City"})       # new tags: the shot is searched again
    assert material.Material(RunContext.create("v", root=tmp_path), youtube).signature() != before


def test_without_material_nothing_changes(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path)
    nothing = material.Material(ctx, None)
    assert not nothing.active and nothing.youtube_search and nothing.for_shot(SimpleNamespace(text="x"), []) == []
    from pipeline.sourcing import inputs

    assert inputs(ctx) == [ctx.work_dir / "shots.json"]                     # the search's fingerprint as before


def test_the_studio_saves_the_material_holds_the_video_and_streams_your_clips(tmp_path):
    _project(tmp_path)
    web.create_video(tmp_path, {"name": "gta1", "channel": "aviacion", "script": SCRIPT, "hold": True,
                                "material": {"videos": "https://youtu.be/aaaaaaaaaaa", "channels": "@IGN",
                                             "saveChannels": True}})
    folder = tmp_path / "materiales" / "aviacion" / "gta1"
    assert (folder / web.HOLD).is_file()                                    # waits for your clips
    assert material.read(folder)["videos"] == ["aaaaaaaaaaa"]
    assert web.channel_material(tmp_path, "aviacion")["channels"] == ["@IGN"]
    data = b"\0" * 300_000
    made = web.save_clip(tmp_path, "gta1", "Mi partida.mp4", "persecución", io.BytesIO(data), len(data))
    assert made["file"] == "Mi-partida.mp4" and (folder / "material" / "Mi-partida.mp4").stat().st_size == len(data)
    assert material.read(folder)["clips"] == {"Mi-partida.mp4": "persecución"}
    with pytest.raises(ValueError, match="cortó"):
        web.save_clip(tmp_path, "gta1", "b.mp4", "", io.BytesIO(b"\0" * 10), 100)
    assert not list((folder / "material").glob("*.subiendo"))
    assert web.partner_may(tmp_path, ["aviacion"], "GET", "/api/material/aviacion")
    assert not web.partner_may(tmp_path, ["otro"], "GET", "/api/material/aviacion")
    assert web.partner_may(tmp_path, ["aviacion"], "POST", "/api/video/gta1/material/clip")


def test_your_own_clips_have_no_credit_on_screen_nor_in_the_credits():
    from pipeline.qa import credits_text

    rows = [{"shotId": "s001", "source": "propio", "start": 0.0, "credit": "Fuente: material propio"},
            {"shotId": "s002", "source": "youtube", "start": 3.0, "credit": "Fuente: IGN", "channel": "IGN",
             "title": "t", "url": "https://youtu.be/x"}]
    text = credits_text(rows)
    assert "IGN" in text and "propio" not in text
