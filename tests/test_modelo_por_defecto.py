"""27-11 [A4]: atlas_guion had no model and fell back to deepseek-flash: without DeepSeek balance every Atlas video
put the whole queue on hold; and LLM_API_KEY stayed required with everything on Claude."""

from pipeline import llm
from pipeline.context import RunContext


def test_a_text_section_without_a_model_follows_the_planner():
    config = {"planner": {"model": "claude-haiku-5-5", "effort": "none", "batch_size": 24},
              "atlas_guion": {"max_tokens": 9000}, "factcheck": {"model": "claude-sonnet-5-5"}}
    atlas = llm.text_section(config, "atlas_guion")
    assert atlas["model"] == "claude-haiku-5-5" and atlas["effort"] == "none" and atlas["max_tokens"] == 9000
    assert "batch_size" not in atlas                                    # only the provider settings
    assert llm.text_section(config, "factcheck")["model"] == "claude-sonnet-5-5"   # its own stays
    assert llm.text_section({}, "atlas_guion") == {}                     # nothing anywhere: DeepSeek, as before


def test_the_keys_asked_are_the_ones_used():
    on_claude = {"planner": {"model": "claude-haiku-5-5"}, "factcheck": {"model": "claude-haiku-5-5"},
                 "guion": {"model": "claude-sonnet-5-5"}}
    assert llm.keys_needed(on_claude) == {"ANTHROPIC_API_KEY"}
    mixed = {**on_claude, "atlas_guion": {"model": "deepseek-flash"}}
    assert llm.keys_needed(mixed) == {"ANTHROPIC_API_KEY", "LLM_API_KEY"}


def test_an_atlas_request_goes_to_claude(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("planner: {model: claude-haiku-5-5, effort: none}\n")
    ctx = RunContext.create("_t", root=tmp_path)
    asked = {}
    from pipeline import claude

    monkeypatch.setattr(claude, "ask", lambda ctx, **kw: (asked.update(kw), ('{"ok": 1}', 0.0))[1])
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: (_ for _ in ()).throw(AssertionError("DeepSeek asked")))
    assert llm.complete_json(ctx, stage="atlas", system="s", user="u", section="atlas_guion", use_cache=False) == {"ok": 1}
    assert asked["cfg"]["model"] == "claude-haiku-5-5"
