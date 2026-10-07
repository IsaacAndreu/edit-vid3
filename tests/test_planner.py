from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from pipeline import planner
from pipeline.context import RunContext
from pipeline.planner import _label_batch, check_numbers, cut_shots, normalize_groups, pace_targets
from pipeline.schemas import Shot, ShotsFile, Word


def _words(n: int, step: float = 0.4) -> list[Word]:
    return [
        Word(index=i, text=f"w{i}" + ("." if i % 7 == 6 else ""), start=i * step, end=i * step + 0.3,
             matched=True, sentenceEnd=i % 7 == 6)
        for i in range(n)
    ]


BROLL = {
    "visualIntent": "roulette wheel spinning",
    "queriesEn": ["roulette wheel close up", "casino roulette table", "roulette ball spinning"],
    "queriesEs": ["ruleta casino"],
}


def _structural(i: int, text: str = "texto") -> dict:
    return {"id": f"s{i:03d}", "startWord": i, "endWord": i, "start": 2.0 * i, "end": 2.0 * i + 2, "text": text, "chapter": 0}


class CutShotsTests(unittest.TestCase):
    def test_durations_within_limits_and_contiguous(self) -> None:
        words = _words(300)
        duration = words[-1].end + 0.2
        shots = cut_shots(words, duration, target=2.6, forced_starts={100})
        self.assertEqual(shots[0][0], 0)
        self.assertEqual(shots[-1][1], 299)
        for (a, b), (c, _) in zip(shots, shots[1:]):
            self.assertEqual(b + 1, c)
        starts = [0.0] + [words[a].start for a, _ in shots[1:]] + [duration]
        durations = [e - s for s, e in zip(starts, starts[1:])]
        self.assertTrue(all(1.5 <= d <= 4.0 for d in durations), durations)
        self.assertIn(100, [a for a, _ in shots])

    def test_a_long_pause_is_shared_instead_of_breaking_the_maximum(self) -> None:
        # "En 2016," then 5 s of silence, then more speech: no word boundary makes every shot ≤ 4 s.
        items = [("a", 0.0, 0.4), ("b", 0.5, 0.9), ("c", 1.0, 1.4), ("En", 1.5, 1.7), ("2016,", 1.8, 2.4),
                 ("la", 7.4, 7.6), ("beca", 7.7, 8.2), ("de", 8.3, 8.4), ("Tokio", 8.5, 9.0), ("fin.", 9.1, 9.6)]
        words = [Word.model_validate({"index": i, "text": t, "start": a, "end": b, "matched": True,
                                      "sentenceEnd": t.endswith(".")}) for i, (t, a, b) in enumerate(items)]
        shots, starts = cut_shots(words, 10.0, target=2.6, forced_starts=set(), with_times=True)
        ends = starts[1:] + [10.0]
        self.assertTrue(all(1.5 - 1e-6 <= e - s <= 4.0 + 1e-6 for s, e in zip(starts, ends)), list(zip(starts, ends)))
        self.assertEqual(shots[0][0], 0)
        self.assertEqual(shots[-1][1], len(words) - 1)

    def test_prefers_sentence_ends(self) -> None:
        words = _words(140)
        shots = cut_shots(words, words[-1].end + 0.2, target=2.6, forced_starts=set())
        ends_on_sentence = sum(words[b].sentenceEnd for _, b in shots[:-1])
        self.assertGreater(ends_on_sentence, len(shots) // 3)


class OutlineTests(unittest.TestCase):
    def test_drops_misplaced_chapters_instead_of_failing(self) -> None:
        # One sentence every 10 s.
        words = [Word.model_validate({"index": i, "text": "w.", "start": 10.0 * i, "end": 10.0 * i + 1, "matched": True,
                                      "sentenceEnd": True}) for i in range(40)]
        sentences = [(i, i) for i in range(40)]
        result = {"chapters": [{"title": "b", "sentence": 12}, {"title": "hook", "sentence": 1},
                               {"title": "a", "sentence": 3}, {"title": "too close", "sentence": 5},
                               {"title": "c", "sentence": 30}, {"title": "bad", "sentence": 99}]}
        chapters = planner._validate_outline(result, sentences, words)
        self.assertEqual([(c.title, c.startWord) for c in chapters], [("A", 3), ("B", 12), ("C", 30)])
        with self.assertRaises(ValueError):
            planner._validate_outline({"chapters": [{"title": "a", "sentence": 3}]}, sentences, words)


class StoryTests(unittest.TestCase):
    def test_parses_events_tolerantly_and_assigns_them_to_shots(self) -> None:
        sentences = [(i * 10, i * 10 + 9) for i in range(10)]
        result = {"subject": "Carlos Yulo · artistic gymnastics", "events": [
            {"sentence": 4, "label": "Carlos Yulo floor gold 2019 Stuttgart"},
            {"sentence": 2, "label": "Carlos Yulo Palarong Pambansa childhood"},
            {"sentence": 99, "label": "out of range"}, {"sentence": "x", "label": "bad"}, "junk"]}
        subject, events = planner.parse_story(result, sentences)
        self.assertEqual(subject, "Carlos Yulo · artistic gymnastics")
        self.assertEqual([(e.startWord, e.label) for e in events], [
            (0, "Carlos Yulo highlights"), (20, "Carlos Yulo Palarong Pambansa childhood"),
            (40, "Carlos Yulo floor gold 2019 Stuttgart")])
        self.assertEqual(planner.event_at(events, 45), "Carlos Yulo floor gold 2019 Stuttgart")
        self.assertEqual(planner.parse_story({}, sentences), ("", []))

    def test_event_becomes_the_first_query(self) -> None:
        broll = {"visualIntent": "podium", "queriesEn": ["gymnastics podium", "medal ceremony"], "queriesEs": ["podio"]}
        out = planner._with_event(broll, "Carlos Yulo 2019 Stuttgart podium")
        self.assertEqual(out["queriesEn"][0], "Carlos Yulo 2019 Stuttgart podium")
        self.assertEqual(out["event"], "Carlos Yulo 2019 Stuttgart podium")
        self.assertIs(planner._with_event(broll, None), broll)


class NumberCheckTests(unittest.TestCase):
    def test_rejects_invented_or_digitless_figures(self) -> None:
        stat = {"id": "s1", "type": "stat", "stat": {"value": "10-100 M€", "label": "x"}}
        self.assertTrue(check_numbers(stat, "entre varios millones y decenas de millones"))
        stat["stat"]["value"] = "decenas de M€"
        self.assertTrue(check_numbers(stat, "decenas de millones"))

    def test_accepts_numbers_written_as_words(self) -> None:
        stat = {"id": "s1", "type": "stat", "stat": {"value": "5º oro", "label": "x", "sign": "positive"}}
        self.assertEqual(check_numbers(stat, "se llevó su quinto oro consecutivo en suelo"), [])
        panel = {"id": "s2", "type": "datacard", "panel": {"title": "t", "rows": [
            {"label": "edad", "value": "16 años", "sign": "neutral"}, {"label": "x", "value": "32", "sign": "neutral"}]}}
        self.assertEqual(check_numbers(panel, "tenía dieciséis años y treinta y dos medallas"), [])
        self.assertTrue(check_numbers(stat, "se llevó el oro"))

    def test_accepts_spanish_formats(self) -> None:
        panel = {"id": "s1", "type": "datacard", "panel": {"title": "t", "rows": [
            {"label": "a", "value": "2,70 €"}, {"label": "b", "value": "305.800 M$"}, {"label": "c", "value": "x miles"}]}}
        self.assertEqual(check_numbers(panel, "se queda con 2,7 euros de 305.800 millones"), [])


class GroupTests(unittest.TestCase):
    def test_renumbers_batch_local_ids_and_merges_repeated_stats(self) -> None:
        panel = lambda title, n: {"title": title, "rows": [{"label": "r", "value": str(i)} for i in range(n)]}  # noqa: E731
        shots = [
            {"id": "s001", "type": "datacard", "panelId": "p1", "panel": panel("A", 1)},
            {"id": "s002", "type": "split", "panelId": "p1", "panel": panel("A", 2), "broll": BROLL},
            {"id": "s003", "type": "broll", "broll": BROLL},
            {"id": "s004", "type": "datacard", "panelId": "p1", "panel": panel("B", 1)},
            {"id": "s005", "type": "stat", "stat": {"value": "5%", "label": "x"}},
            {"id": "s006", "type": "stat", "stat": {"value": "5%", "label": "x"}},
            {"id": "s007", "type": "stat", "stat": {"value": "7%", "label": "y"}},
        ]
        normalize_groups(shots)
        ids = [s.get("panelId") for s in shots]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(shots[1]["type"], "datacard")      # group takes the first shot's type
        self.assertNotIn("broll", shots[1])
        self.assertIsNone(ids[2])
        self.assertNotEqual(ids[3], ids[0])                  # same raw "p1", different panel
        self.assertEqual(ids[4], ids[5])
        self.assertIsNone(ids[6])                            # singleton stat


class ShotSchemaTests(unittest.TestCase):
    def test_type_requires_its_fields(self) -> None:
        base = _structural(1)
        Shot.model_validate({**base, "type": "broll", "broll": BROLL})
        for bad in (
            {**base, "type": "broll"},
            {**base, "type": "split", "broll": BROLL},
            {**base, "type": "chapter", "broll": BROLL},
            {**base, "type": "stat"},
            {**base, "type": "broll", "broll": {**BROLL, "queriesEn": ["one", "two"]}},
            {**base, "type": "broll", "broll": {**BROLL, "queriesEs": []}},
        ):
            with self.assertRaises(ValidationError):
                Shot.model_validate(bad)

    def test_file_rejects_gaps_and_out_of_range_durations(self) -> None:
        shots = [
            {**_structural(0), "type": "broll", "broll": BROLL},
            {**_structural(1), "type": "broll", "broll": BROLL},
        ]
        base = {"slug": "t", "title": "T", "durationSeconds": 4.0,
                "chapters": [{"title": "X", "startWord": 0, "fromScript": False}]}
        ShotsFile.model_validate({**base, "shots": shots})
        with self.assertRaises(ValidationError):
            ShotsFile.model_validate({**base, "durationSeconds": 5.0, "shots": shots})
        long_shot = {**shots[0], "end": 5.5}          # emotional shots may hold 5 s, never more
        with self.assertRaises(ValidationError):
            ShotsFile.model_validate({**base, "shots": [long_shot, {**shots[1], "start": 5.5, "end": 7.0}], "durationSeconds": 7.0})


class LabelRetryTests(unittest.TestCase):
    def test_retry_asks_only_for_failed_shots_and_keeps_good_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext.create("t", root=Path(tmp), config={})
            batch = [_structural(1, "dice 2,7%"), _structural(2, "otra cosa")]
            responses = [
                {"shots": [{"id": "s001", "type": "stat", "stat": {"value": "2,7%", "label": "x"}, "broll": BROLL},
                           {"id": "s002", "type": "stat", "stat": {"value": "99%", "label": "inventado"}, "broll": BROLL}]},
                {"shots": [{"id": "s002", "type": "broll", "broll": BROLL}]},
            ]
            prompts: list[str] = []

            def fake(ctx, **kwargs):
                prompts.append(kwargs["user"])
                return responses[len(prompts) - 1]

            with patch.object(planner, "complete_json", side_effect=fake):
                result = _label_batch(ctx, batch, "H", 3, {"s001": "dice 2,7%", "s002": "otra cosa"})
        self.assertEqual([s["type"] for s in result], ["stat", "broll"])
        self.assertIn("RESPONDE SOLO con los planos s002", prompts[1])
        self.assertIn("99%", prompts[1])

    def test_a_stubborn_datacard_without_broll_becomes_broll_instead_of_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext.create("t", root=Path(tmp), config={})
            batch = [_structural(1, "dice 2,7%"), _structural(2, "otra cosa")]
            panel = {"title": "Notas", "rows": [{"label": "dif", "value": "4,22"}]}
            first = {"shots": [{"id": "s001", "type": "broll", "broll": BROLL},
                               {"id": "s002", "type": "datacard", "panel": panel}]}
            again = {"shots": [{"id": "s002", "type": "datacard", "panel": panel}]}
            with patch.object(planner, "complete_json", side_effect=[first, again, again]):
                result = _label_batch(ctx, batch, "H", 3, {"s001": "dice 2,7%", "s002": "otra cosa"})
        self.assertEqual([s["type"] for s in result], ["broll", "broll"])
        self.assertEqual(result[1]["broll"]["visualIntent"], result[0]["broll"]["visualIntent"])


if __name__ == "__main__":
    unittest.main()


class PacingTests(unittest.TestCase):
    def test_slow_passages_get_long_shots_and_fast_ones_quick_cuts(self) -> None:
        words = [Word(index=i, text=f"w{i}", start=i * 0.3, end=i * 0.3 + 0.25, matched=True, sentenceEnd=i % 20 == 19)
                 for i in range(60)]
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext.create("t", root=Path(tmp), config={"pacing": {"hook_seconds": 0}})
            targets, maxes, labels = pace_targets(ctx, words, {0: "slow", 2: "fast"}, 3.0)
        shots, starts = cut_shots(words, 18.0, target=3.0, forced_starts=set(), with_times=True, targets=targets, maxes=maxes)
        ends = starts[1:] + [18.0]
        lengths = {labels[a]: [] for a, _ in shots}
        for (a, _), s0, s1 in zip(shots, starts, ends):
            lengths[labels[a]].append(s1 - s0)
        slow, fast = lengths["slow"], lengths["fast"]
        assert max(slow) > 4.0 and max(slow) <= 5.0 + 1e-6
        assert sum(fast) / len(fast) < sum(slow) / len(slow) - 1.5


class CalmPaceTests(unittest.TestCase):
    def test_a_calm_channel_holds_shots_longer(self) -> None:
        words = [Word(index=i, text=f"w{i}", start=i * 0.3, end=i * 0.3 + 0.25, matched=True, sentenceEnd=i % 20 == 19)
                 for i in range(100)]
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext.create("t", root=Path(tmp), config={"pacing": {"hook_seconds": 0}})
            targets, maxes, _ = pace_targets(ctx, words, {}, 4.4)
        shots, starts = cut_shots(words, 30.0, target=4.4, forced_starts=set(), with_times=True, targets=targets, maxes=maxes)
        assert len(shots) <= 8 and max(b - a for a, b in zip(starts, starts[1:] + [30.0])) <= 5.0 + 1e-6


class HookPaceTests(unittest.TestCase):
    def test_the_first_half_minute_cuts_fast(self) -> None:
        words = [Word(index=i, text=f"w{i}", start=i * 0.3, end=i * 0.3 + 0.25, matched=True, sentenceEnd=i % 10 == 9)
                 for i in range(200)]
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext.create("t", root=Path(tmp), config={})
            targets, maxes, _ = pace_targets(ctx, words, {0: "slow"}, 3.0)
        shots, starts = cut_shots(words, 60.0, target=3.0, forced_starts=set(), with_times=True, targets=targets, maxes=maxes)
        ends = starts[1:] + [60.0]
        opening = [e - s for s, e in zip(starts, ends) if s < 28]
        rest = [e - s for s, e in zip(starts, ends) if s > 32]
        self.assertLess(sum(opening) / len(opening), 2.2)
        self.assertGreater(sum(rest) / len(rest), 2.6)
        self.assertTrue(all(d >= 1.5 - 1e-3 for d in opening))


def test_a_year_in_a_label_must_be_said():
    from pipeline.planner import check_numbers

    shot = {"id": "s203", "type": "datacard", "panel": {"title": "Comparación", "rows": [
        {"label": "Japón 2024", "value": "221,06"}, {"label": "Pekín 2022", "value": "251,73"}]}}
    text = "Septiembre de 2026. Su total en Japón, 221,06, queda lejos de los 251,73 de Pekín en 2022."
    errors = check_numbers(shot, text)
    assert len(errors) == 1 and "2024" in errors[0]
    shot["panel"]["rows"][0]["label"] = "Japón 2026"
    assert check_numbers(shot, text) == []
