"""A channel about a video game is not left without footage by the global blocklist (19-11: gtaviprueba)."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline import canal_juego
from pipeline.context import RunContext

ROOT = Path(__file__).resolve().parents[1]


def _ctx(tmp_path, profile: dict, name: str = "gtaviprueba") -> RunContext:
    (tmp_path / "config.yaml").write_text((ROOT / "config.yaml").read_text("utf-8"), encoding="utf-8")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / f"{name}.yaml").write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    (tmp_path / "materiales" / "v" / "config.yaml").write_text(f"canal: {name}\n", encoding="utf-8")
    return RunContext.create("v", root=tmp_path)


def test_a_game_channel_created_from_the_studio_gets_its_footage(tmp_path):
    ctx = _ctx(tmp_path, {"ideas": {"about": "un canal de YouTube en español de videos sobre el videojuego gta vi"},
                          "format": "datos"})
    content = ctx.section("content")
    assert "gta" not in content["title_blocklist"] and "gameplay" not in content["title_blocklist"]
    assert "minecraft" in content["title_blocklist"] and "excel" in content["title_blocklist"]
    assert content["official_channels"] == ["Rockstar Games"]
    assert "video game" in ctx.section("judge")["note"]
    from pipeline.sourcing.common import blocked_by_title

    assert blocked_by_title("GTA 6 Trailer 2 gameplay breakdown", "Some Fan", content["title_blocklist"],
                            content["official_channels"]) is None


def test_a_channel_with_its_own_lists_keeps_them(tmp_path):
    own = {"ideas": {"about": "GTA 6 y Florida"}, "content": {"title_blocklist": ["gta"]},
           "judge": {"note": "mine"}}
    ctx = _ctx(tmp_path, own)
    assert ctx.section("content")["title_blocklist"] == ["gta"] and ctx.section("judge")["note"] == "mine"


def test_other_channels_are_untouched(tmp_path):
    ctx = _ctx(tmp_path, {"ideas": {"about": "los Juegos Olímpicos y la gimnasia"}}, name="gimnasia2")
    assert "gta" in ctx.section("content")["title_blocklist"] and not ctx.section("judge").get("note")
    assert not canal_juego.is_game_channel({"canal": "megaproyectos", "ideas": {"about": "obras gigantes"}})
