from __future__ import annotations

import unittest

from pydantic import ValidationError

from pipeline.align import build_words_file, normalize, parse_script
from pipeline.schemas import WordsFile


def _raw(words: list[tuple[str, float, float]], duration: float) -> dict:
    return {"duration": duration, "words": [{"word": w, "start": s, "end": e} for w, s, e in words]}


def _build(script: str, raw: dict):
    return build_words_file(slug="t", title="T", script=script, raw=raw, provider="local", model="x", language="es")


class NormalizeTests(unittest.TestCase):
    def test_accents_case_and_punctuation(self) -> None:
        self.assertEqual(normalize("¿Economía,"), "economia")
        self.assertEqual(normalize("2,7%"), "27")
        self.assertEqual(normalize("—"), "")


class ParseScriptTests(unittest.TestCase):
    def test_headings_and_sentence_ends(self) -> None:
        tokens, headings = parse_script("## El negocio\nTienes razón. Pero no\n\nFin")
        self.assertEqual(headings, ["El negocio"])
        self.assertEqual([t.heading for t in tokens[:2]], [0, 0])
        self.assertTrue(tokens[3].sentence_end)       # "razón."
        self.assertTrue(tokens[5].sentence_end)       # "no" closes its line
        self.assertEqual(tokens[-1].text, "Fin")

    def test_punctuation_only_token_is_glued(self) -> None:
        tokens, _ = parse_script("Hola — mundo")
        self.assertEqual([t.text for t in tokens], ["Hola —", "mundo"])


class AlignmentTests(unittest.TestCase):
    def test_script_text_wins_and_unheard_words_are_interpolated(self) -> None:
        raw = _raw(
            [("La", 0.0, 0.2), ("ventaja", 0.2, 0.6), ("es", 0.6, 0.7), ("del", 0.7, 0.8),
             ("dos", 0.8, 1.0), ("coma", 1.0, 1.2), ("siete", 1.2, 1.4), ("por", 1.4, 1.5),
             ("ciento", 1.5, 1.8), ("hoy", 1.9, 2.1)],
            2.2,
        )
        result = _build("La ventaja es del 2,7%. Hoy", raw)
        texts = [w.text for w in result.words]
        self.assertEqual(texts, ["La", "ventaja", "es", "del", "2,7%.", "Hoy"])
        number = result.words[4]
        self.assertFalse(number.matched)
        self.assertAlmostEqual(number.start, 0.8, places=3)
        self.assertAlmostEqual(number.end, 1.8, places=3)
        self.assertTrue(number.sentenceEnd)
        self.assertEqual(result.alignment.matchedWords, 5)

    def test_spoken_heading_starts_chapter_on_its_own_words(self) -> None:
        raw = _raw([("El", 0, 0.2), ("negocio", 0.2, 0.6), ("Tienes", 1.0, 1.3), ("razón", 1.3, 1.7)], 2.0)
        result = _build("## El negocio\nTienes razón", raw)
        self.assertEqual(len(result.words), 4)
        self.assertEqual(result.chapters[0].wordIndex, 0)
        self.assertTrue(result.chapters[0].spoken)

    def test_silent_heading_is_a_marker_only(self) -> None:
        raw = _raw([("Hola", 0, 0.3), ("Tienes", 1.0, 1.3), ("razón", 1.3, 1.7)], 2.0)
        result = _build("Hola\n## Capítulo dos\nTienes razón", raw)
        self.assertEqual([w.text for w in result.words], ["Hola", "Tienes", "razón"])
        self.assertEqual(result.chapters[0].title, "Capítulo dos")
        self.assertEqual(result.chapters[0].wordIndex, 1)
        self.assertFalse(result.chapters[0].spoken)
        self.assertAlmostEqual(result.chapters[0].start, 1.0)

    def test_timings_are_monotonic(self) -> None:
        raw = _raw([("b", 0.5, 0.6), ("a", 0.1, 0.2)], 1.0)
        result = _build("a b", raw)
        starts = [w.start for w in result.words]
        self.assertEqual(starts, sorted(starts))


class WordsSchemaTests(unittest.TestCase):
    def test_rejects_non_monotonic_or_out_of_range(self) -> None:
        base = {
            "slug": "t", "title": "T", "language": "es", "durationSeconds": 2.0, "chapters": [],
            "alignment": {"provider": "local", "model": "x", "scriptWords": 2, "whisperWords": 2,
                          "matchedWords": 2, "matchRatio": 1.0},
        }
        words = [
            {"index": 0, "text": "a", "start": 1.0, "end": 1.2, "matched": True},
            {"index": 1, "text": "b", "start": 0.5, "end": 0.7, "matched": True},
        ]
        with self.assertRaises(ValidationError):
            WordsFile.model_validate({**base, "words": words})
        with self.assertRaises(ValidationError):
            WordsFile.model_validate({**base, "words": [{**words[0], "end": 3.0}]})
        with self.assertRaises(ValidationError):
            WordsFile.model_validate({**base, "words": [{**words[0], "extra": 1}]})


if __name__ == "__main__":
    unittest.main()
