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


class TailTests(unittest.TestCase):
    """newgym11: 13.7 s of silence after the voice made the last shot 13.67 s and the planner fail every retry."""

    def test_silence_after_the_voice_is_trimmed_and_the_plan_cuts(self) -> None:
        from pipeline.planner import cut_shots

        script = " ".join(f"palabra{i}." for i in range(20))
        spoken = [(f"palabra{i}", i * 0.5, i * 0.5 + 0.4) for i in range(19)] + [("palabra19", 9.5, 23.67)]  # stretched
        words_file = _build(script, _raw(spoken, 23.67))
        self.assertAlmostEqual(words_file.durationSeconds, 9.5 + 1.2 + 1.0, places=3)
        self.assertLessEqual(words_file.words[-1].end, words_file.durationSeconds)
        shots = cut_shots(words_file.words, words_file.durationSeconds, target=2.6, forced_starts=set(), with_times=True)
        starts = shots[1] + [words_file.durationSeconds]
        self.assertTrue(all(1.5 - 1e-3 <= b - a <= 5.0 + 1e-3 for a, b in zip(starts, starts[1:])))

    def test_a_short_tail_is_kept(self) -> None:
        words_file = _build("Hola mundo.", _raw([("hola", 0.0, 0.5), ("mundo", 0.6, 1.0)], 1.5))
        self.assertEqual(words_file.durationSeconds, 1.5)


class PauseTests(unittest.TestCase):
    """newgym11: 27 s with no word of the script after «nada.» — two shots can share a pause, never 27 s."""

    def _words(self):
        script = " ".join(f"palabra{i}." for i in range(20))
        spoken = [(f"palabra{i}", i * 0.5, i * 0.5 + 0.4) for i in range(10)] \
            + [(f"palabra{i}", 4.5 + 27 + (i - 9) * 0.5, 4.5 + 27 + (i - 9) * 0.5 + 0.4) for i in range(10, 20)]
        return _build(script, _raw(spoken, 37.0))

    def test_a_long_pause_is_cut_and_every_shot_fits(self) -> None:
        from pipeline.align import long_pauses, without_pauses
        from pipeline.planner import cut_shots

        words_file = self._words()
        cuts = long_pauses(words_file.words)
        self.assertEqual(len(cuts), 1)
        start, end = cuts[0]
        self.assertAlmostEqual(start, 5.4, places=3)          # «palabra9» ends at 4.9, half the second kept after it
        self.assertAlmostEqual(end, 31.5, places=3)           # «palabra10» starts at 32.0
        cut = without_pauses(words_file, cuts)
        self.assertAlmostEqual(cut.words[10].start - cut.words[9].end, 1.0, places=3)
        self.assertAlmostEqual(cut.durationSeconds, words_file.durationSeconds - (end - start), places=3)
        WordsFile.model_validate(cut.model_dump())
        _, starts = cut_shots(cut.words, cut.durationSeconds, target=2.6, forced_starts=set(), with_times=True)
        bounds = starts + [cut.durationSeconds]
        self.assertTrue(all(1.5 - 1e-3 <= b - a <= 5.0 + 1e-3 for a, b in zip(bounds, bounds[1:])))

    def test_ordinary_pauses_stay(self) -> None:
        from pipeline.align import long_pauses

        words = _build("Hola. Adiós.", _raw([("hola", 0.0, 0.5), ("adios", 3.0, 3.5)], 4.0)).words
        self.assertEqual(long_pauses(words), [])
        self.assertEqual(long_pauses(self._words().words, 0), [])   # 0: never

    def test_the_voice_loses_the_pause(self) -> None:
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path

        from pipeline.align import cut_voice

        if not shutil.which("ffmpeg"):
            self.skipTest("sin ffmpeg")
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "voz.mp3", Path(folder) / "corta.mp3"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440:d=30", str(source)], check=True)
            cut_voice(source, target, [(5.0, 25.0)])
            seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                            str(target)], capture_output=True, text=True).stdout)
            self.assertAlmostEqual(seconds, 10.0, delta=0.2)


class PauseVoiceTests(unittest.TestCase):
    """The words move only if the voice really lost the pause (CI's ffmpeg kept 30 s with `aselect`)."""

    def _ctx(self, folder):
        import subprocess
        from pathlib import Path

        from pipeline.context import RunContext

        ctx = RunContext.create("t", root=Path(folder), config={"align": {"min_match_ratio": 0.5}})
        ctx.materials_dir.mkdir(parents=True, exist_ok=True)
        # spoken, 27.1 s of real silence (the pause), spoken: only real silence is cut
        from tests.test_pausas_reales import voice

        voice(ctx.materials_dir / "voz.mp3", [("t", 4.9), ("s", 27.1), ("t", 5)])
        return ctx

    def test_the_voice_and_the_words_lose_the_pause_together(self) -> None:
        import shutil
        import tempfile

        from pipeline import align

        if not shutil.which("ffmpeg"):
            self.skipTest("sin ffmpeg")
        with tempfile.TemporaryDirectory() as folder:
            ctx = self._ctx(folder)
            align._finish(ctx, PauseTests()._words())
            saved = WordsFile.model_validate(ctx.read_json(align.OUTPUT))
            seconds = align._seconds(ctx.materials_dir / "voz.mp3")
            self.assertAlmostEqual(seconds, 37.0 - 26.1, delta=0.2)          # the 26.1 s cut out of the mp3 itself
            self.assertAlmostEqual(saved.words[10].start, 32.0 - 26.1, delta=0.1)
            self.assertTrue((ctx.materials_dir / "voz.original.mp3").is_file())

    def test_a_cut_that_did_not_happen_moves_nothing(self) -> None:
        import shutil
        import tempfile

        from pipeline import align

        if not shutil.which("ffmpeg"):
            self.skipTest("sin ffmpeg")
        with tempfile.TemporaryDirectory() as folder:
            ctx = self._ctx(folder)
            before = (ctx.materials_dir / "voz.mp3").read_bytes()
            original = align.cut_voice
            align.cut_voice = lambda source, target, cuts: (shutil.copy2(source, target), 37.0)[1]   # ffmpeg ignored it
            try:
                with self.assertRaises(RuntimeError):
                    align._finish(ctx, PauseTests()._words())
            finally:
                align.cut_voice = original
            self.assertEqual((ctx.materials_dir / "voz.mp3").read_bytes(), before)
            self.assertFalse((ctx.work_dir / align.OUTPUT).is_file())

    def test_a_voice_the_old_cut_left_whole_is_aligned_again(self) -> None:
        import shutil
        import tempfile

        from pipeline import align

        if not shutil.which("ffmpeg"):
            self.skipTest("sin ffmpeg")
        with tempfile.TemporaryDirectory() as folder:
            ctx = self._ctx(folder)
            align._finish(ctx, PauseTests()._words())
            self.assertTrue(align.validate(ctx))                               # cut for real: up to date
            shutil.copy2(ctx.materials_dir / "voz.original.mp3", ctx.materials_dir / "voz.mp3")   # what aselect left
            self.assertFalse(align.validate(ctx))
