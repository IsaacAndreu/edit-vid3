"""«Que el clip sea…» 3: with the API, the event's search and the shot's most concrete one (the moment's first), more
results per search at the same quota, and a ranking that asks for an entity's full name, the event and the year."""

from __future__ import annotations

from pipeline.schemas import BrollSpec
from pipeline.sourcing.youtube import YouTubeSource, most_concrete, relevance_bonus


def _broll(**kw) -> BrollSpec:
    base = {"visualIntent": "gymnast falls on the beam", "event": "Simone Biles Tokyo 2020 Olympics",
            "queriesEn": ["Simone Biles Tokyo 2020 Olympics", "gymnastics beam", "Simone Biles beam fall Tokyo 2020",
                          "olympic gymnastics arena"],
            "queriesEs": ["Simone Biles caída barra Tokio"], "entities": ["Simone Biles"]}
    return BrollSpec.model_validate({**base, **kw})


def _source(tmp_path, monkeypatch, **cfg):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", **cfg})
    yt.api = object()                     # «there are keys»
    return yt


def test_the_api_searches_the_event_and_the_most_concrete_query(tmp_path, monkeypatch):
    yt = _source(tmp_path, monkeypatch)
    assert yt.queries_for(_broll()) == ["Simone Biles Tokyo 2020 Olympics", "Simone Biles beam fall Tokyo 2020"]
    moment = _broll(moment="Simone Biles falls off the beam")
    assert yt.queries_for(moment) == ["Simone Biles beam fall Tokyo 2020", "Simone Biles Tokyo 2020 Olympics"]
    local = _source(tmp_path, monkeypatch, api_local_query=True)
    assert local.queries_for(_broll())[-1] == "Simone Biles caída barra Tokio"
    yt.close()
    local.close()


def test_most_concrete_prefers_moment_name_and_year():
    broll = _broll(moment="falls off the beam")
    assert most_concrete(["gymnastics beam", "Simone Biles beam fall Tokyo 2020"], broll) == \
        "Simone Biles beam fall Tokyo 2020"


def test_one_loose_word_no_longer_gives_the_bonus():
    broll = _broll()
    full = relevance_bonus({"title": "Simone Biles Tokyo 2020 Olympics beam final", "channel": "Olympics"}, broll)
    loose = relevance_bonus({"title": "Simone Johnson floor routine", "channel": "x"}, broll)
    described = relevance_bonus({"title": "Beam final", "channel": "x",
                                 "description": "Simone Biles at the Tokyo 2020 Olympic Games"}, broll)
    other_year = relevance_bonus({"title": "Simone Biles 2016 Rio", "channel": "x"}, broll)
    assert full > described > loose and loose <= 0.0
    assert other_year < relevance_bonus({"title": "Simone Biles", "channel": "x"}, broll) + 0.01


def test_api_searches_ask_for_more_results_at_the_same_quota(tmp_path, monkeypatch):
    yt = _source(tmp_path, monkeypatch)
    asked = []
    monkeypatch.setattr(yt, "_api_search", lambda query, limit, days=0: asked.append(limit) or [])
    yt.search("anything")
    assert asked == [30]
    yt.close()
