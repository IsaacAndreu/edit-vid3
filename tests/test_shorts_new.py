"""New Shorts (shorts.style: nuevo): each one a new vertical video with its own script, not a cut of the video."""

from __future__ import annotations

import yaml

from pipeline import shorts
from pipeline.context import RunContext


def _channel(tmp_path, style="simulacion"):
    import shutil

    shutil.copy("config.yaml", tmp_path / "config.yaml")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "trafico.yaml").write_text(f"visual:\n  style: {style}\n", "utf-8")
    folder = tmp_path / "materiales" / "trafico" / "hora1"
    folder.mkdir(parents=True)
    (tmp_path / "materiales" / "trafico" / "config.yaml").write_text("canal: trafico\n", "utf-8")
    (folder / "guion.txt").write_text("## INTRO\n\n" + "Los atascos aparecen sin motivo. " * 40, "utf-8")
    return RunContext.create("hora1", root=tmp_path)


def test_drawn_channels_make_new_shorts_by_default(tmp_path):
    ctx = _channel(tmp_path)
    assert shorts.style(ctx) == "nuevo"
    other = RunContext.create("x", root=tmp_path, config={"visual": {"style": "footage"}})
    assert shorts.style(other) == "native"


def test_each_short_is_a_new_vertical_video_in_the_queue(tmp_path, monkeypatch):
    ctx = _channel(tmp_path)
    good = " ".join(["palabra"] * 110)
    seen = {}

    def fake(ctx, **kwargs):
        seen.update(kwargs)
        return {"shorts": [{"script": "## TÍTULO\n" + good, "title": "Uno", "description": "d #a"},
                           {"script": "corto", "title": "Dos"},
                           {"script": good + " fin", "title": "Tres", "description": ""}]}

    monkeypatch.setattr(shorts, "complete_json", fake)
    shorts.make_new(ctx)
    assert "## " not in seen["user"] and "simulaciones" in seen["system"].lower()
    folder = tmp_path / "materiales" / "trafico" / "hora1-short1"
    assert (folder / "guion.txt").read_text("utf-8").strip() == good          # no heading, its own words
    cfg = yaml.safe_load((folder / "config.yaml").read_text("utf-8"))
    assert cfg["video"] == {"width": 1080, "height": 1920, "fps": 60} and cfg["timeline"]["endscreen_seconds"] == 0
    assert cfg["shorts"] == {"enabled": False, "of": "hora1"} and cfg["timeline"]["captions"] is True
    assert (tmp_path / "materiales" / "trafico" / "hora1-short2").is_dir()   # the too-short one was skipped
    assert not (tmp_path / "materiales" / "trafico" / "hora1-short3").exists()
    child = RunContext.create("hora1-short1", root=tmp_path)
    assert child.section("video")["height"] == 1920 and not shorts.enabled(child)
    assert (ctx.out_dir / "shorts" / "shorts.txt").is_file() and shorts.validate(ctx)
    shorts.make_new(ctx)                                                       # again: the made ones are kept
    assert (folder / "guion.txt").read_text("utf-8").strip() == good
