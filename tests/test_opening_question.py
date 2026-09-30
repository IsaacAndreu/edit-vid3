from pipeline.schemas import WordsFile
from pipeline.timeline import opening_question, question_groups


def words(text: str) -> WordsFile:
    items, t = [], 0.0
    for i, w in enumerate(text.split()):
        items.append({"index": i, "text": w, "start": t, "end": t + 0.3, "matched": True,
                      "sentenceEnd": w.endswith((".", "?", "!"))})
        t += 0.35
    return WordsFile.model_validate({"slug": "v", "title": "T", "language": "es", "durationSeconds": t + 1, "words": items,
                                     "chapters": [], "alignment": {"provider": "local", "model": "x", "scriptWords": len(items), "whisperWords": len(items), "matchedWords": len(items), "matchRatio": 1.0}})


def test_opening_question_without_marks_shows_from_frame_zero():
    w = words("Quieres ser dueño de un casino. Tienes el dinero. Tienes las ganas.")
    assert opening_question(w, {}) == (0, 5)
    groups = question_groups(w, [], [], 30, 300, {})
    first = groups[0]
    assert first.id == "q-open" and first.from_ == 0
    assert [x.text for x in first.words] == ["¿Quieres", "ser", "dueño", "de", "un", "casino?"]
    assert all(x.from_ == 0 for x in first.words)


def test_statements_are_not_questions_unless_forced():
    w = words("Tienes el dinero. Tienes las ganas.")
    assert opening_question(w, {}) is None
    assert opening_question(w, {"opening_question": True}) == (0, 2)
    assert opening_question(words("¿Sabes cuánto gana un casino? Mucho."), {"opening_question": "false"}) is None
