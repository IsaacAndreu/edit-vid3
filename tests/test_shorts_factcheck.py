from pipeline import factcheck, shorts


def _words(text: str, start: float = 0.0, step: float = 0.5) -> list[dict]:
    out = []
    for i, token in enumerate(text.split()):
        out.append({"text": token, "start": start + i * step, "end": start + i * step + 0.4,
                    "sentenceEnd": token.endswith(".")})
    return out


def test_sentences_and_fit():
    words = _words(" ".join(["uno dos tres cuatro cinco seis siete ocho nueve diez."] * 12))
    sents = shorts.sentences(words)
    assert len(sents) == 12 and sents[1]["start"] == 5.0
    # each sentence lasts ~5 s: 25-58 s → between 5 and 11 sentences
    assert shorts.fit(sents, 0, 0, 25, 58) == (0, 5)          # too short → extended to ≥ 25 s
    assert shorts.fit(sents, 0, 11, 25, 58) == (0, 10)        # too long → trimmed
    assert shorts.fit(sents, 5, 3, 25, 58) is None


def test_ass_highlights_current_word_and_escapes():
    words = _words("hola {mundo} bonito día.")
    text = shorts.ass(words, "gancho", 0.0, 3.0)
    assert "Style: Hook" in text and "GANCHO" in text
    captions = [line for line in text.splitlines() if ",Cap," in line]
    assert len(captions) == 4                                  # one event per spoken word
    assert "{\\c&H00D4FF&}HOLA{\\c&HFFFFFF&} (MUNDO) BONITO" in captions[0]
    assert "{mundo}" not in text.lower()


def test_factcheck_report_groups_verdicts():
    result = {"articles": ["https://en.wikipedia.org/wiki/X"], "claims": [
        {"n": 1, "quote": "a", "claim": "a", "verdict": "wrong", "correction": "b", "evidence": "e", "source": "s"},
        {"n": 2, "quote": "c", "claim": "c", "verdict": "ok", "correction": None, "evidence": None, "source": None},
        {"n": 3, "quote": "d", "claim": "d", "verdict": "unverified", "correction": None, "evidence": None, "source": None}]}
    md = factcheck.report(result)
    assert "❌ 1 a corregir · ⚠️ 1 sin confirmar · ✅ 1 confirmadas" in md
    assert md.index("A corregir") < md.index("Sin confirmar") < md.index("Confirmadas")
    assert "Correcto: b" in md
