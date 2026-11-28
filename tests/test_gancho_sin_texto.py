"""The hook never stays text while something of its subject exists: after the donors run out, a clip already used
(not next to it), then any judged clip where its subject is seen (even of a literal idea), then a photo."""

from __future__ import annotations

from pipeline.schemas import ShotIdea, TimelineShot
from pipeline.timeline import limit_text


def _shot(i, src=None, kind="video", start=None):
    return TimelineShot.model_validate({
        "id": f"s{i:03d}", "type": "broll", "from": (start if start is not None else i * 90), "durationInFrames": 90,
        "text": "una frase",
        "media": {"src": src, "kind": kind, "source": "youtube", "credit": "Fuente: X"} if src else None})


def _idea(n, kind, must=(), era=None):
    return ShotIdea.model_validate({"id": f"i{n:03d}", "kind": kind, "mustShow": list(must), "era": era})


def _run(shots, ideas, scores=None):
    return limit_text(shots, [], 30, ideas, scores or {}, share=0.0, hook_seconds=30)


def test_a_clip_already_used_in_the_hook_comes_back_rather_than_text():
    shots = [_shot(0), _shot(1, "media/x.mp4"), _shot(2, "media/y.mp4"), _shot(3), _shot(4)]
    ideas = {f"s{i:03d}": _idea(1, "ambiente", ["Simone Biles"]) for i in range(5)}
    counts = _run(shots, ideas, {"s001": 0.9, "s002": 0.5})
    assert all(s.media is not None for s in shots) and counts["sin_donante"] == 0


def test_a_judged_literal_clip_of_the_subject_beats_text_in_the_hook():
    shots = [_shot(0), _shot(1, "media/z.mp4"), _shot(2, "media/boda.mp4")]
    ideas = {"s000": _idea(1, "ambiente", ["Simone"]), "s001": _idea(2, "ambiente", ["Jordan Chiles"]),
             "s002": _idea(3, "literal", ["Simone Biles"], era="boda 2023")}
    _run(shots, ideas, {"s002": 0.8})
    assert shots[0].media is not None and shots[0].media.src == "media/boda.mp4"


def test_a_photo_of_the_subject_when_there_is_no_clip():
    shots = [_shot(0), _shot(1, "media/z.mp4"), _shot(2, "media/foto.jpg", kind="image")]
    ideas = {"s000": _idea(1, "ambiente", ["Simone Biles"]), "s001": _idea(2, "ambiente", ["Jordan Chiles"]),
             "s002": _idea(3, "ambiente", ["Simone Biles"])}
    _run(shots, ideas)
    assert shots[0].media is not None and shots[0].media.kind == "image"


def test_nothing_of_the_subject_stays_text_as_before():
    shots = [_shot(0), _shot(1, "media/z.mp4")]
    ideas = {"s000": _idea(1, "ambiente", ["Simone Biles"]), "s001": _idea(2, "literal", ["Jordan Chiles"])}
    counts = _run(shots, ideas, {"s001": 0.9})
    assert shots[0].media is None and counts["sin_donante"] == 1
