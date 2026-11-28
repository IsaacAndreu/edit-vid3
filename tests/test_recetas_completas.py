"""A recipe turns on what its settings need (the ideas, for literal_ambient, ambient_photo_first, max_text_share by
person and cobertura) or fails saying so; and the grouping prompt no longer tells the model that a literal idea
without its clip stays text."""

from __future__ import annotations

import pytest

from pipeline import recetas
from pipeline.config import ConfigError
from pipeline.context import RunContext


def _ctx(tmp_path, channel_yaml):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "c.yaml").write_text(channel_yaml)
    return RunContext.create("v1", root=tmp_path, channel="c")


@pytest.mark.parametrize("recipe", ["persona", "suceso"])
def test_a_recipe_turns_on_the_ideas_it_needs(tmp_path, recipe):
    ctx = _ctx(tmp_path, f"montaje: {{receta: {recipe}}}\n")
    assert ctx.section("planner").get("ideas") is True
    assert ctx.section("fallback").get("literal_ambient") is True


def test_a_channel_that_switches_the_ideas_off_under_a_recipe_that_needs_them_fails_saying_so(tmp_path):
    with pytest.raises(ConfigError, match="ideas"):
        _ctx(tmp_path, "montaje: {receta: suceso}\nplanner: {ideas: false}\n")


def test_without_a_recipe_nothing_changes(tmp_path):
    ctx = _ctx(tmp_path, "planner: {ideas: false}\n")
    assert ctx.section("planner").get("ideas") is False
    assert recetas.preset({}) == {}


def test_the_grouping_prompt_no_longer_promises_text():
    from pipeline import agrupar

    assert "se queda en texto" not in agrupar.SYSTEM
