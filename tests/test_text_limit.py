"""prompts/ideas-pantallas-de-texto.md (23-11): newideas, half of an 11-min video in text and the first 36 s without a
picture. The timeline caps the text: none in the hook, never two boards in a row, ≤ 3 s each, ≤ share of the video;
a chapter title read aloud keeps its title; past the cap a shot borrows a clip (its idea's first, else the nearest)."""

from types import SimpleNamespace

from pipeline.schemas import TimelineMedia, TimelineShot
from pipeline.timeline import board_words, limit_text

FPS = 30


def _shot(n, start, seconds, media=True):
    m = TimelineMedia(src=f"media/s{n:03d}.mp4", kind="video", source="youtube", credit="Fuente: c") if media else None
    return TimelineShot.model_validate({"id": f"s{n:03d}", "type": "broll", "from": start * FPS,
                                        "durationInFrames": seconds * FPS, "text": f"frase {n}", "media": m})


def _idea(kind, idea_id="i001", line=None, facts=()):
    return SimpleNamespace(kind=kind, id=idea_id, screenLine=line, facts=list(facts))


def test_no_text_in_the_hook_the_judges_best_clip_goes_there():
    shots = [_shot(1, 0, 3, media=False), _shot(2, 3, 3, media=False), _shot(3, 40, 3), _shot(4, 50, 3)]
    counts = limit_text(shots, [], FPS, {}, {"s004": 0.9, "s003": 0.4}, share=0.10, hook_seconds=30)
    assert counts["gancho"] == 2 and all(s.media is not None for s in shots)
    assert shots[0].media.src == "media/s004.mp4"                      # the best judged clip, not the nearest


def test_never_two_boards_in_a_row_and_never_longer_than_three_seconds():
    shots = [_shot(1, 0, 3)] + [_shot(n, 30 + 3 * (n - 2), 3, media=False) for n in range(2, 6)] + [_shot(6, 60, 3)]
    limit_text(shots, [], FPS, {}, {}, share=1.0, hook_seconds=0)
    texts = [s.media is None for s in shots]
    assert texts == [False, True, False, True, False, False]
    long_ = [_shot(1, 0, 3), _shot(2, 40, 5, media=False)]
    limit_text(long_, [], FPS, {}, {}, share=1.0, hook_seconds=0)
    assert long_[1].media is not None                                  # 5 s of text: a clip instead


def test_the_share_caps_the_text_and_titles_stay_text():
    shots = [_shot(1, 0, 3)] + [_shot(n, 10 * n, 3, media=False) for n in range(2, 10)] + [_shot(10, 200, 3)]
    ideas = {"s005": _idea("rotulo", "i005")}
    counts = limit_text(shots, [], FPS, ideas, {}, share=0.05, hook_seconds=0)   # 5 % of ~203 s ≈ 10 s: 3 boards
    text = [s.id for s in shots if s.media is None]
    assert "s005" in text and counts["texto"] <= 4 and counts["prestados"] >= 4


def test_a_borrowed_clip_comes_from_the_same_idea_first():
    ideas = {"s002": _idea("ambiente", "i002"), "s009": _idea("ambiente", "i002"), "s003": _idea("ambiente", "i003")}
    shots = [_shot(2, 0, 3, media=False), _shot(3, 3, 3), _shot(9, 120, 3)]
    limit_text(shots, [], FPS, ideas, {}, share=0.0, hook_seconds=0)
    assert shots[0].media.src == "media/s009.mp4"                      # its idea's clip, though s003 is nearer


def test_a_board_says_what_the_voice_does_not_and_titles_are_never_blank():
    assert board_words("tiene seis títulos mundiales en suelo", _idea("ambiente", line="*6* títulos mundiales")) \
        == "6 títulos mundiales"
    assert board_words("en Río ganó", _idea("ambiente", facts=["Río 2016"])) == "Río 2016"
    assert board_words("SECRETO 2:", _idea("rotulo")) == "SECRETO 2"
    assert board_words("y", None) == "Y"


def test_qa_finds_a_blank_screen_longer_than_a_second():
    from types import SimpleNamespace as NS

    from pipeline.qa import empty_spans

    def group(start, seconds):
        return NS(from_=start * FPS, durationInFrames=seconds * FPS)

    shots = [_shot(1, 0, 3), _shot(2, 3, 3, media=False), _shot(3, 6, 4, media=False)]
    timeline = NS(fps=FPS, shots=shots, groups=[group(3, 3), group(6, 2)])     # s003: its last 2 s show nothing
    assert empty_spans(timeline) == [("s003", 2.0)]
