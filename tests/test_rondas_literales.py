"""judge.rounds_literal (off): a literal idea outside the hook may get a second sheet of options before the fallback;
off it gets as many as any other shot there (rounds_rest)."""

from __future__ import annotations

from types import SimpleNamespace as NS

from pipeline.judge import rounds_for

LITERAL, AMBIENT = NS(idea=NS(kind="literal")), NS(idea=NS(kind="ambiente"))


def test_off_a_literal_idea_gets_what_any_shot_gets():
    cfg = {"rounds": 2, "rounds_rest": 1}
    assert rounds_for(LITERAL, cfg, in_hook=False) == 1 and rounds_for(AMBIENT, cfg, in_hook=False) == 1
    assert rounds_for(LITERAL, cfg, in_hook=True) == 2


def test_with_the_option_a_literal_idea_gets_a_second_sheet():
    cfg = {"rounds": 2, "rounds_rest": 1, "rounds_literal": 2}
    assert rounds_for(LITERAL, cfg, in_hook=False) == 2 and rounds_for(AMBIENT, cfg, in_hook=False) == 1
    assert rounds_for(NS(idea=None), cfg, in_hook=False) == 1 and rounds_for(NS(), {}, in_hook=False) == 2
