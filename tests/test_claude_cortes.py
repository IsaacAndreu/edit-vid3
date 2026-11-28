"""Claude failing halfway: the planner's own retry sees it, what was billed is written down, and no call waits forever."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from pipeline import claude
from pipeline.llm import LLMError
from tests.test_claude import FakeClient


class CutStream:
    """A reply that streams part of its text and then the connection dies (or never ends)."""

    def __init__(self, snapshot, error=None, hang=0.0):
        self.current_message_snapshot = snapshot
        self.error, self.hang = error, hang

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if self.hang:
            threading.Event().wait(self.hang)            # (time.sleep is a no-op in these tests)
        raise self.error or RuntimeError("peer closed connection without sending complete message body")


class CutClient:
    def __init__(self, streams):
        self.streams = list(streams)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: self.streams.pop(0)))


@pytest.fixture
def ctx(monkeypatch):
    recorded = []
    monkeypatch.setattr(claude, "record_cost", lambda ctx, **kw: recorded.append(kw))
    monkeypatch.setattr(claude.time, "sleep", lambda s: None)
    return SimpleNamespace(recorded=recorded, env=lambda name, required=True: "x")


def test_a_refusal_or_a_cut_reply_is_a_text_failure_the_planner_retries(ctx):
    with pytest.raises(LLMError):
        claude.ask(ctx, stage="planner", system="r", content="b", cfg={}, client=FakeClient("", stop="refusal"))
    with pytest.raises(LLMError):
        claude.ask(ctx, stage="planner", system="r", content="b", cfg={}, client=FakeClient("{", stop="max_tokens"))


def test_a_reply_cut_halfway_is_written_down_as_spent(ctx):
    half = SimpleNamespace(model="claude-opus-5-5", usage=SimpleNamespace(input_tokens=10_000, output_tokens=1),
                           content=[SimpleNamespace(type="text", text="x" * 8000)])
    nothing = None                                       # died before the first byte: nothing billed
    no_usage = SimpleNamespace(model="claude-opus-5-5", usage=None, content=[])
    fine = FakeClient('{"ok": 1}').reply
    streams = [CutStream(half), CutStream(nothing), CutStream(no_usage), FakeClientStream(fine)]
    text, _ = claude.ask(ctx, stage="planner", system="r", content="b", cfg={"network_retries": 3},
                         client=CutClient(streams))
    assert text == '{"ok": 1}'
    cut = [r for r in ctx.recorded if "cortada" in r["operation"]]
    assert len(cut) == 1                                  # only the one that had started answering
    assert cut[0]["usd"] == pytest.approx((10_000 * 4 + 2000 * 20) / 1e6)     # ~4 characters a token
    assert cut[0]["details"]["estimated"] is True


def test_no_call_waits_forever(ctx):
    started = time.monotonic()
    with pytest.raises(LLMError, match="no respondió a tiempo"):
        claude.ask(ctx, stage="planner", system="r", content="b", cfg={"deadline_seconds": 0.3, "network_retries": 0},
                   client=CutClient([CutStream(None, hang=5)]))
    assert time.monotonic() - started < 3


class FakeClientStream:
    def __init__(self, reply):
        self.reply = reply

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.reply
