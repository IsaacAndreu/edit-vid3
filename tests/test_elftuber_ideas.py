"""Title prefilter for reactions/podcasts, the viral score, the «explota» alerts and the hook's key word."""

from pathlib import Path

from pipeline import radar, shorts
from pipeline.sourcing.common import blocked_by_title


def test_reactions_and_podcasts_are_dropped_by_title_but_not_the_athletes_own_reaction():
    assert blocked_by_title("Coach REACTS TO Simone Biles vault", "x")
    assert blocked_by_title("Episode 12", "GymCastic: The Gymnastics Podcast")
    assert blocked_by_title("Rebeca Andrade: reagindo à nota", "x")
    assert not blocked_by_title("Simone Biles reaction after her vault", "Olympics")


def test_viral_score():
    assert radar.viral_score({"ratio": 1}) == 0
    assert radar.viral_score({"ratio": 10, "ageDays": 20}) == 50
    assert radar.viral_score({"ratio": 10, "ageDays": 2}) == 60
    assert radar.viral_score({"ratio": 765, "ageDays": 3}) == 100


def test_explosions_at_most_two_a_day_and_never_twice(tmp_path: Path):
    top = [{"id": f"v{i}", "ratio": 50, "ageDays": 1, "title": "t", "channel": "c", "views": 10} for i in range(4)]
    top.append({"id": "old", "ratio": 500, "ageDays": 20})
    report = {"channels": {"gimnasia": {"top": top}}}
    cfg = {"alerts_per_day": 2, "alert_score": 60, "alert_days": 3}
    first = radar.explosions(tmp_path, report, cfg, today="2026-11-03")
    assert len(first) == 2 and "old" not in {v["id"] for v in first}
    assert radar.explosions(tmp_path, report, cfg, today="2026-11-03") == []          # the day's two are spent
    nxt = radar.explosions(tmp_path, report, cfg, today="2026-11-04")
    assert {v["id"] for v in nxt}.isdisjoint({v["id"] for v in first})              # never the same twice


def test_key_word_of_the_hook():
    assert shorts.key_word("¿Por qué tu cola es la más *lenta*?".split()) == 7
    assert shorts.key_word("Ocho Juegos en 30 años".split()) == 3
    assert shorts.key_word("Un juez muy estricto".split()) == 3
    ass = shorts.hook_ass("Un juez muy *estricto*")
    assert "*" not in ass and "DM Serif Display" in ass and ass.startswith("UN JUEZ MUY")
