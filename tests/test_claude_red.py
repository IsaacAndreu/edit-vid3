"""27-11: «peer closed connection without sending complete message body» from Claude in the planner failed three
videos in a row and the breaker paused the queue for the night. A cut connection is asked again, and never trips it."""

from types import SimpleNamespace

import pytest

from pipeline import claude
from pipeline.cortacircuitos import Breaker


class RemoteProtocolError(Exception):
    pass


class Stream:
    def __init__(self, outcome):
        self.outcome = outcome

    def __enter__(self):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.outcome


def _reply():
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(model="claude-sonnet-5-5", usage=usage, stop_reason="end_turn",
                           content=[SimpleNamespace(type="text", text='{"ok": true}')])


def _client(outcomes):
    calls = []

    def stream(**kw):
        calls.append(kw)
        return Stream(outcomes[len(calls) - 1])

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream))), calls


def _ctx(tmp_path):
    from pipeline.context import RunContext

    return RunContext.create("v", root=tmp_path, config={})


def test_a_cut_connection_is_asked_again(tmp_path, monkeypatch):
    monkeypatch.setattr(claude.time, "sleep", lambda s: None)
    cut = RemoteProtocolError("peer closed connection without sending complete message body (incomplete chunked read)")
    client, calls = _client([cut, cut, _reply()])
    text, _ = claude.ask(_ctx(tmp_path), stage="planner", system="s", content="c",
                         cfg={"model": "claude-sonnet-5-5"}, client=client)
    assert text == '{"ok": true}' and len(calls) == 3


def test_a_real_error_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(claude.time, "sleep", lambda s: None)
    client, calls = _client([ValueError("bad request: max_tokens"), _reply()])
    with pytest.raises(ValueError):
        claude.ask(_ctx(tmp_path), stage="planner", system="s", content="c", cfg={"model": "claude-sonnet-5-5"},
                   client=client)
    assert len(calls) == 1


def test_it_gives_up_after_the_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(claude.time, "sleep", lambda s: None)
    cut = RemoteProtocolError("peer closed connection")
    client, calls = _client([cut] * 4)
    with pytest.raises(RemoteProtocolError):
        claude.ask(_ctx(tmp_path), stage="planner", system="s", content="c", cfg={"model": "claude-sonnet-5-5"},
                   client=client)
    assert len(calls) == 4


def test_network_failures_never_pause_the_queue(tmp_path):
    breaker = Breaker(tmp_path, same_stage=3)
    detail = ("httpx2.RemoteProtocolError: peer closed connection without sending complete message body "
              "(incomplete chunked read)")
    for slug in ("newatleta24.3", "newatlet24.2", "patinaje1.0", "otro"):
        assert breaker.failed(slug, detail) is None
    assert breaker.failed("x", "NameError: name 'foo' is not defined") is None
    assert breaker.failed("y", "NameError: name 'foo' is not defined") is not None    # a real bug still does
