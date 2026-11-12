"""pipeline/subtitulos.py: trozos de la voz como subtítulos y su archivo de libass."""

from pipeline import subtitulos


def words(text, step=0.3):
    return [{"text": t, "start": 0.3 + step * i, "end": 0.55 + step * i} for i, t in enumerate(text.split())]


def test_phrases_split_at_punctuation_and_long_ones_into_even_pieces():
    cues = subtitulos.cues(words("Tras ser sentenciado, los agentes lograron someter al agresor en la sala del tribunal."),
                           lambda t: round(t * 30), 30)
    assert [c["text"] for c in cues] == ["Tras ser sentenciado,", "los agentes lograron someter al agresor",
                                         "en la sala del tribunal."]
    assert all(a["from"] + a["durationInFrames"] <= b["from"] for a, b in zip(cues, cues[1:]))


def test_no_subtitles_over_a_question_panel_and_the_key_word_is_marked():
    w = words("Uno dos tres. Cuatro cinco seis.")
    cues = subtitulos.cues(w, lambda t: round(t * 30), 30, blocked=[(0, 30)])
    assert [c["text"] for c in cues] == ["Cuatro cinco seis."]
    text = subtitulos.ass([{"from": 0, "durationInFrames": 30, "text": "murieron 2.000 personas"}], 30, 1920, 1080)
    assert "{\\c&H00D4FF&}2.000{\\c&HFFFFFF&}" in text and "Style: Sub," in text
