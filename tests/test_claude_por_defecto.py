"""«que use claude»: DeepSeek ran out of balance and every video stopped at the planner. The planner, the fact check
and the script drafts now go to Claude (config.yaml); its key is the one checked, and its empty balance waits."""

from pathlib import Path

from pipeline.context import RunContext

ROOT = Path(__file__).resolve().parents[1]


def test_the_text_work_goes_to_claude():
    ctx = RunContext.create("_t", root=ROOT)
    for section in ("planner", "factcheck", "guion"):
        assert ctx.section(section)["model"].startswith("claude-"), section


def test_the_key_checked_is_anthropics(tmp_path, monkeypatch):
    from pipeline import preflight

    ctx = RunContext.create("_t", root=tmp_path, config={"planner": {"model": "claude-sonnet-5-5"}})
    ctx._env_loaded = True
    for key in ("ANTHROPIC_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "deepseek")
    problems = preflight.video_problems(ctx)
    assert any("ANTHROPIC_API_KEY" in p for p in problems) and not any(p == "falta LLM_API_KEY" for p in problems)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert not any("ANTHROPIC" in p for p in preflight.video_problems(ctx))


def test_an_empty_anthropic_balance_waits_instead_of_failing():
    import main

    error = RuntimeError("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
                         "'message': 'Your credit balance is too low to access the Anthropic API.'}}")
    message = main.out_of_credit(error)
    assert message and "Anthropic" in message and "console.anthropic.com" in message
