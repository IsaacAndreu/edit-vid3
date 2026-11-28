"""The text cap and the boards: no board longer than board_max_seconds, no board cut in the middle of a word, a
board of a shot that is only a piece of a sentence shows the sentence's words (not «Y» or «en Spring»), and past the
cap a gap takes a neutral clip of the video before staying text."""

from __future__ import annotations

from pipeline.schemas import ShotIdea, TimelineShot
from pipeline.timeline import board_words, chalkboards, limit_text


def _shot(i, text, frames=60, src=None):
    return TimelineShot.model_validate({
        "id": f"s{i:03d}", "type": "broll", "from": i * frames, "durationInFrames": frames, "text": text,
        "media": {"src": src, "kind": "video", "source": "youtube", "credit": "Fuente: X"} if src else None})


def test_no_board_is_longer_than_board_max_seconds():
    shots = [_shot(i, "la despedida del campeonato del mundo que nadie esperaba", frames=60) for i in range(6)]
    boards = chalkboards(shots, [], 30, longest_seconds=3.0)
    assert boards and max(b.durationInFrames for b in boards) <= 90                       # 3 s at 30 fps
    assert sum(b.durationInFrames for b in boards) == 360                                 # nothing left bare


def test_a_board_never_ends_in_the_middle_of_a_word():
    idea = ShotIdea.model_validate({"id": "i001", "kind": "ambiente",
                                    "screenLine": "Gracias a todos los que me acompañaron durante estos maravillosos años"})
    line = board_words("Gracias a todos", idea)
    assert len(line) <= 60 and "Gracias a todos los que me acompañaron durante estos maravillosos años".startswith(line)
    assert line.split()[-1] in "Gracias a todos los que me acompañaron durante estos maravillosos años".split()


def test_a_piece_of_a_sentence_shows_the_sentences_words():
    shots = [_shot(0, "Ganó el oro en el mundial", src="media/a.mp4"), _shot(1, "y"),
             _shot(2, "en Spring Hill.", src="media/b.mp4"), _shot(3, "Y")]
    shots[3] = shots[3].model_copy(update={"text": "Y"})
    boards = chalkboards(shots, [], 30)
    lines = " ".join(" ".join(b.graphic["lines"]) for b in boards)
    assert "ORO" in lines.upper() or "MUNDIAL" in lines.upper()             # the sentence, not «Y» or «EN SPRING»


def test_past_the_cap_a_gap_takes_a_neutral_clip_before_staying_text():
    def idea(n, kind, who=(), not_who=()):
        return ShotIdea.model_validate({"id": f"i{n:03d}", "kind": kind, "mustShow": list(who),
                                        "mustNotShow": list(not_who)})

    shots = [_shot(0, "frase", src="media/a.mp4"), _shot(1, "más", src="media/c.mp4"), _shot(5, "y más")]
    ideas = {"s000": idea(1, "ambiente", ["Simone Biles"]), "s001": idea(2, "ambiente", ["Suni Lee"]),
             "s005": idea(3, "ambiente", ["Jordan Chiles"], ["Suni Lee"])}
    counts = limit_text(shots, [], 30, ideas, {}, share=0.0, hook_seconds=0)
    # nobody may lend (another person, or who it must not show) but the cap is spent: a neutral clip, never Suni Lee
    assert shots[2].media is not None and shots[2].media.src == "media/a.mp4"
    assert counts["fuera_de_tope"] == 0
