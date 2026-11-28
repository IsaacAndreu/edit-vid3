"""Claude's path with the real Anthropic SDK (only its HTTP is faked): what we send is what the SDK accepts, and the
streamed reply is read. The end-to-end test runs on deepseek-flash, so without this the Claude path was never run."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

anthropic = pytest.importorskip("anthropic")
pytest.importorskip("httpx2")                      # the SDK's own HTTP library (anthropic 2.x)

from pipeline import claude  # noqa: E402


def _sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def test_the_real_sdk_takes_our_request_and_reads_the_stream(monkeypatch):
    import httpx2

    seen = {}

    def handler(request):
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        events = [
            {"type": "message_start", "message": {"id": "m1", "type": "message", "role": "assistant",
                                                  "model": "claude-haiku-5-5", "content": [], "stop_reason": None,
                                                  "stop_sequence": None,
                                                  "usage": {"input_tokens": 1000, "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": '{"ok": 1}'}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
             "usage": {"output_tokens": 2000}},
            {"type": "message_stop"},
        ]
        return httpx2.Response(200, content=_sse(events), headers={"content-type": "text/event-stream"})

    client = anthropic.Anthropic(api_key="x", max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    recorded = []
    monkeypatch.setattr(claude, "record_cost", lambda ctx, **kw: recorded.append(kw))
    ctx = SimpleNamespace(env=lambda name, required=True: "x")
    text, usd = claude.ask(ctx, stage="planner", system="reglas", content="frases",
                           cfg={"model": "claude-haiku-5-5", "effort": "none"}, schema={"type": "object"},
                           client=client)
    assert json.loads(text) == {"ok": 1}
    assert usd == pytest.approx((1000 * 0.1 + 2000 * 0.5) / 1e6)
    assert claude.FALLBACK_BETA in seen["headers"].get("anthropic-beta", "")
    assert seen["body"]["model"] == "claude-haiku-5-5" and seen["body"]["fallbacks"] == "default"
    assert seen["body"]["output_config"]["format"]["type"] == "json_schema"
    assert "effort" not in seen["body"]["output_config"]
    assert recorded and recorded[0]["provider"] == "anthropic"
