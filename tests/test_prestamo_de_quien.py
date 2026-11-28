"""A gap only borrows a clip that may stand for it: never a literal idea's clip of something else («boda 2023» on an
ambient shot), never a clip of someone the shot must not show; and a name written two ways is the same person."""

from __future__ import annotations

from pipeline.schemas import ShotIdea, TimelineShot
from pipeline.timeline import fill_empty_shots, lendable, same_people


def _shot(i, src=None, frames=90):
    return TimelineShot.model_validate({
        "id": f"s{i:03d}", "type": "broll", "from": i * 90, "durationInFrames": frames, "text": "una frase",
        "media": {"src": src, "kind": "video", "source": "youtube", "credit": "Fuente: X"} if src else None})


def _idea(n, kind, must=(), must_not=(), era=None):
    return ShotIdea.model_validate({"id": f"i{n:03d}", "kind": kind, "mustShow": list(must),
                                    "mustNotShow": list(must_not), "era": era})


def test_names_written_two_ways_are_the_same_person():
    assert same_people(["Simone"], ["Simone Biles"]) and same_people(["simone biles"], ["Simone Arianne Biles"])
    assert same_people(["Simóne Biles"], ["SIMONE BILES"])
    assert not same_people(["Simone Biles"], ["Simone Manuel"]) and not same_people([], ["Biles"])
    assert same_people(["La GOAT"], ["Simone Biles"], aliases={"simone biles": ["la goat", "biles"]})


def test_an_ambient_gap_never_shows_a_literal_clip_of_something_else():
    shots = [_shot(0, "media/boda.mp4"), _shot(1, "media/x.mp4"), _shot(2)]
    ideas = {"s000": _idea(1, "literal", ["Simone Biles"], era="boda 2023"),
             "s001": _idea(2, "ambiente", ["Jonathan Owens"]),
             "s002": _idea(3, "ambiente", ["Simone Biles"])}
    fill_empty_shots(shots, [], 30, ideas=ideas)
    assert shots[2].media is None                       # the wedding is a literal idea: not for another line


def test_a_gap_about_someone_never_borrows_a_clip_of_who_it_must_not_show():
    shots = [_shot(0, "media/rival.mp4"), _shot(1, "media/x.mp4"), _shot(2), _shot(3, "media/y.mp4"),
             _shot(4, "media/biles.mp4")]
    ideas = {"s000": _idea(1, "ambiente", ["Rebeca Andrade"]), "s001": _idea(2, "ambiente", []),
             "s002": _idea(3, "ambiente", ["Simone"], must_not=["Rebeca Andrade"]),
             "s003": _idea(4, "ambiente", []), "s004": _idea(5, "ambiente", ["Simone Biles"])}
    fill_empty_shots(shots, [], 30, ideas=ideas)
    assert shots[2].media is not None and shots[2].media.src == "media/biles.mp4"   # «Simone» is Simone Biles


def test_without_ideas_as_before():
    shots = [_shot(0, "media/a.mp4"), _shot(1, "media/b.mp4"), _shot(2)]
    fill_empty_shots(shots, [], 30)
    assert shots[2].media is not None and shots[2].media.src == "media/a.mp4"
    assert lendable(shots[0], shots[2], {}, {}) is True
