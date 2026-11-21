"""Claude as a second provider: script drafts (guion.model) and the revisor (revisor.model). No real request here: a
fake client stands in for the Anthropic SDK and records what it was asked."""

import json
from types import SimpleNamespace

import pytest

from pipeline import claude


class FakeStream:
    def __init__(self, reply):
        self.reply = reply

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.reply


class FakeClient:
    def __init__(self, text, stop="end_turn", model="claude-opus-5-5"):
        self.calls = []
        usage = SimpleNamespace(input_tokens=1000, output_tokens=2000, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        self.reply = SimpleNamespace(model=model, usage=usage, stop_reason=stop, stop_details=None,
                                     content=[SimpleNamespace(type="thinking", thinking=""),
                                              SimpleNamespace(type="text", text=text)])
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.reply)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(claude, "record_cost", lambda ctx, **kw: recorded.append(kw))
    return SimpleNamespace(recorded=recorded, env=lambda name, required=True: "x")


def test_one_request_streamed_with_fallbacks_and_its_cost(ctx):
    fake = FakeClient('{"title": "T", "script": "s"}')
    text, usd = claude.ask(ctx, stage="guiones", system="rules", content="brief", cfg={"model": "claude-opus-5-5"},
                           client=fake)
    assert json.loads(text)["title"] == "T"
    assert usd == pytest.approx((1000 * 4 + 2000 * 20) / 1e6)
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert claude.FALLBACK_BETA in call["betas"]
    assert call["output_config"] == {"effort": "high"}
    assert ctx.recorded[0]["provider"] == "anthropic"


def test_a_schema_asks_for_structured_json_and_a_cut_reply_raises(ctx):
    fake = FakeClient('{"shots": []}')
    claude.ask(ctx, stage="revisor", system="r", content=[claude.image_block(b"\xff\xd8")], cfg={"effort": "medium"},
               schema={"type": "object"}, client=fake)
    assert fake.calls[0]["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert fake.calls[0]["output_config"]["effort"] == "medium"
    with pytest.raises(claude.ClaudeError):
        claude.ask(ctx, stage="x", system="r", content="b", cfg={}, client=FakeClient("{", stop="max_tokens"))
    with pytest.raises(claude.ClaudeError):
        claude.ask(ctx, stage="x", system="r", content="b", cfg={}, client=FakeClient("", stop="refusal"))


def test_only_claude_models_go_to_claude():
    assert claude.is_claude("claude-opus-5-5") and not claude.is_claude("gpt-5-mini") and not claude.is_claude(None)


def test_drafts_and_revisor_switch_by_their_model(monkeypatch, tmp_path):
    """guion.model: claude-… → the «Nuevo vídeo» drafts; revisor.model: claude-… → the review sheets."""

    import inspect

    from pipeline import llm, organizar, revisor

    assert 'section = "guion" if ctx.section("guion").get("model") else "planner"' in inspect.getsource(organizar)
    assert "claude.is_claude(model)" in inspect.getsource(llm.complete_json)
    assert "claude.is_claude(model)" in inspect.getsource(revisor.ask)

    asked = []

    def fake_ask(ctx, **kw):
        asked.append(kw)
        return '{"title": "Título", "script": "texto"}', 0.01

    monkeypatch.setattr(claude, "ask", fake_ask)
    section = {"model": "claude-opus-5-5"}
    fake_ctx = SimpleNamespace(section=lambda name: section, cache_dir=tmp_path)
    parsed = llm.complete_json(fake_ctx, stage="guiones", system="S", user="U", section="guion", use_cache=False)
    assert parsed == {"title": "Título", "script": "texto"}
    assert asked[0]["content"] == "U" and "JSON" in asked[0]["system"]


def test_the_revisor_sends_the_sheet_to_claude(monkeypatch, tmp_path):
    import numpy as np

    from pipeline import revisor

    asked = []

    def fake_ask(ctx, **kw):
        asked.append(kw)
        return json.dumps({"shots": [{"n": 1, "verdict": "wrong", "problem": "unrelated", "evidence": "e",
                                      "confidence": 0.9}]}), 0.02

    monkeypatch.setattr(claude, "ask", fake_ask)
    fake_ctx = SimpleNamespace(cache_dir=tmp_path, section=lambda name: {})
    entry = {"n": 1, "id": "s001", "text": "frase", "images": [np.zeros((90, 160, 3), np.uint8)] * 2}
    shots, usd = revisor.ask(fake_ctx, {"model": "claude-opus-5-5"}, [entry], "Simone Biles", None)
    assert shots[0]["problem"] == "unrelated" and usd == 0.02
    kw = asked[0]
    assert kw["schema"] is revisor.SCHEMA and kw["cfg"]["effort"] == "medium"
    assert kw["content"][0]["type"] == "image" and "frase" in kw["content"][1]["text"]
