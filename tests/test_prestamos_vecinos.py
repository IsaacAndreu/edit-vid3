"""A shot without footage never repeats the clip right next to it, a clip is lent a bounded number of times over the
whole edit (not per pass), a longer donor lends its other seconds, and QA adds up a run of the same file."""

from __future__ import annotations

from pipeline.schemas import TimelineShot
from pipeline.timeline import fill_empty_shots


def _shot(i, src=None, frames=90):
    return TimelineShot.model_validate({
        "id": f"s{i:03d}", "type": "broll", "from": i * 90, "durationInFrames": frames, "text": "una frase cualquiera",
        "media": {"src": src, "kind": "video", "source": "youtube", "credit": "Fuente: X"} if src else None})


def _passes(shots):
    """The three passes of build_timeline: 2 uses, then 5, then 6."""
    fill_empty_shots(shots, [], 30)
    fill_empty_shots(shots, [], 30, max_uses=5, words=False)
    fill_empty_shots(shots, [], 30, max_uses=6, words=False, partial=True)


def test_one_clip_and_ten_gaps_never_shows_the_same_file_twice_in_a_row():
    shots = [_shot(0, "media/a.mp4")] + [_shot(i) for i in range(1, 11)]
    _passes(shots)
    srcs = [s.media.src if s.media else None for s in shots]
    assert all(not (a and a == b) for a, b in zip(srcs, srcs[1:])), srcs
    assert srcs.count("media/a.mp4") <= 7                      # 1 + at most 6 lent over the three passes


def test_the_uses_of_a_clip_add_up_over_the_passes():
    shots = [_shot(0, "media/a.mp4"), _shot(1, "media/b.mp4")] + [_shot(i) for i in range(2, 30)]
    _passes(shots)
    srcs = [s.media.src for s in shots if s.media]
    assert srcs.count("media/a.mp4") <= 7 and srcs.count("media/b.mp4") <= 7


def test_a_longer_donor_lends_its_other_seconds():
    # donor shows 6 s of its 6 s file … a 3 s gap two shots away gets its LAST 3 s, not the same first 3 s
    shots = [_shot(0, "media/a.mp4", frames=180), _shot(1, "media/b.mp4"), _shot(2, frames=90)]
    shots[1] = shots[1].model_copy(update={"from_": 180})
    shots[2] = shots[2].model_copy(update={"from_": 270})
    fill_empty_shots(shots, [], 30)
    lent = shots[2].media
    assert lent is not None and lent.src == "media/a.mp4" and lent.start == 3.0


def test_qa_adds_up_a_run_of_the_same_file():
    from pipeline.qa import same_file_runs

    shots = [_shot(0, "media/a.mp4", frames=360), _shot(1, "media/a.mp4", frames=270), _shot(2, "media/b.mp4")]
    shots[1] = shots[1].model_copy(update={"from_": 360})
    shots[2] = shots[2].model_copy(update={"from_": 630})
    runs = same_file_runs(shots, 30)
    assert runs == [("media/a.mp4", "s000", "s001", 21.0)]
