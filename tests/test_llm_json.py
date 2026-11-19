"""The planner died on 17-11 with «JSON inválido» in every attempt: the replies models get slightly wrong are
repaired, and the outline's loop takes an invalid reply as one more failed attempt instead of dying."""

from __future__ import annotations

import json

import pytest

from pipeline.llm import parse_json_reply


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Aquí tienes el plan:\n{"a": 1}\nEspero que sirva.',
    '{"a": 1,}',
    '{"a": [1, 2,]}',
])
def test_repairable_replies(text):
    assert parse_json_reply(text)["a"] in (1, [1, 2])


def test_raw_line_breaks_inside_strings():
    assert parse_json_reply('{"text": "una\nlínea"}') == {"text": "una\nlínea"}


def test_hopeless_reply_still_fails():
    with pytest.raises(json.JSONDecodeError):
        parse_json_reply('{"a": ')


def test_the_outline_survives_an_invalid_reply(monkeypatch, tmp_path):
    from pipeline import planner
    from pipeline.context import RunContext
    from pipeline.llm import LLMError
    from types import SimpleNamespace

    from tests.test_planner import _words

    replies = iter([LLMError("deepseek devolvió JSON inválido: x"), {"chapters": [{"title": "uno", "sentence": 20}, {"title": "dos", "sentence": 60}]}])
    asked = []

    def fake(ctx, **kwargs):
        asked.append(kwargs["user"])
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(planner, "complete_json", fake)
    words = _words(700)
    words_file = SimpleNamespace(title="t", words=words, durationSeconds=words[-1].end, chapters=[])
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={})
    chapters, _, _ = planner.plan_chapters(ctx, words_file)
    assert len(asked) == 2 and "no era válida" in asked[1]        # the second attempt is told why
    assert chapters
