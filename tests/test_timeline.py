from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from pipeline.context import RunContext
from pipeline.schemas import Timeline, WordsFile
from pipeline.timeline import question_groups, question_spans, run, speech_segments, with_cold_open

BROLL = {"visualIntent": "roulette", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}
PANEL = lambda n: {"title": "Ruleta", "rows": [{"label": f"r{i}", "value": f"{i} €"} for i in range(n)]}  # noqa: E731


def _shot(i: int, kind: str = "broll", **extra) -> dict:
    return {"id": f"s{i:03d}", "type": kind, "startWord": i, "endWord": i, "start": 2.0 * i, "end": 2.0 * i + 2,
            "text": f"texto {i}", "chapter": 0, **extra}


class TimelineBuildTests(unittest.TestCase):
    def test_merges_media_groups_frames_and_audio(self) -> None:
        shots = [
            _shot(0, broll=BROLL),
            _shot(1, "chapter", broll=BROLL, chapterTitle="LA LICENCIA"),
            _shot(2, "datacard", panel=PANEL(1), panelId="g01"),
            _shot(3, "datacard", panel=PANEL(2), panelId="g01"),
            _shot(4, "stat", broll=BROLL, stat={"value": "2,7%", "label": "ventaja"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "materiales" / "t").mkdir(parents=True)
            (root / "materiales" / "t" / "voz.mp3").write_bytes(b"mp3")
            ctx = RunContext.create("t", root=root, config={"video": {"fps": 30}})
            ctx.write_json("shots.json", {"slug": "t", "title": "T", "durationSeconds": 10.0,
                                          "chapters": [{"title": "X", "startWord": 0, "fromScript": False}], "shots": shots})
            ctx.write_json("words.json", {
                "slug": "t", "title": "T", "language": "es", "durationSeconds": 10.0,
                "words": [{"index": 0, "text": "a", "start": 0.0, "end": 0.4, "matched": True},
                          {"index": 1, "text": "b", "start": 0.6, "end": 1.0, "matched": True},
                          {"index": 2, "text": "c", "start": 3.0, "end": 3.5, "matched": True}],
                "chapters": [], "alignment": {"provider": "local", "model": "x", "scriptWords": 3,
                                              "whisperWords": 3, "matchedWords": 3, "matchRatio": 1.0}})
            media = []
            # s004 also has an ingested clip, but fallback replaced it (e.g. a look-alike): fallback wins.
            for sid, kind, ext in (("s000", "video", "mp4"), ("s001", "image", "jpg"), ("s004", "video", "mp4")):
                path = ctx.work_dir / "media" / f"{sid}.{ext}"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
                media.append({"shotId": sid, "kind": kind, "path": str(path.relative_to(root)), "source": "youtube" if kind == "video" else "wikimedia",
                              "candidateId": "c", "start": 1, "end": 3, "durationSeconds": 2.0 if kind == "video" else None,
                              "width": 1920 if kind == "video" else 2304, "height": 1080 if kind == "video" else 1296,
                              "credit": "Fuente: Canal", "specHash": "h"})
            ctx.write_json("media/_ingest.json", {"slug": "t", "media": media})
            generated = ctx.work_dir / "media_fallback" / "s004.jpg"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"x")
            ctx.write_json("fallback.json", {"slug": "t", "items": [{
                "shotId": "s004", "reason": "r", "method": "generated", "kind": "image",
                "path": str(generated.relative_to(root)), "source": "generated", "candidateId": "gen:1", "specHash": "h"}]})
            run(ctx)
            timeline = Timeline.model_validate(ctx.read_json("timeline.json"))
            self.assertTrue((ctx.work_dir / "audio" / "voz.mp3").is_file())
        self.assertEqual([s.from_ for s in timeline.shots], [0, 60, 120, 180, 240])
        self.assertEqual(timeline.durationInFrames, 300)
        self.assertEqual(timeline.shots[0].media.src, "media/s000.mp4")            # relative to the public dir
        self.assertEqual(timeline.shots[4].media.src, "media_fallback/s004.jpg")
        self.assertEqual(timeline.shots[4].media.credit, "Imagen generada (IA)")    # generated: said on screen
        self.assertEqual(timeline.shots[1].chapterTitle, "LA LICENCIA")
        panel = next(g for g in timeline.groups if g.kind == "datacard")
        self.assertEqual((panel.from_, panel.durationInFrames), (120, 120))        # one panel over two shots
        self.assertEqual([len(s.rows) for s in panel.steps], [1, 2])
        self.assertEqual(panel.steps[1].from_, 60)
        self.assertEqual(next(g for g in timeline.groups if g.kind == "stat").stat.value, "2,7%")
        self.assertEqual(timeline.audio.speech, [(0, 30), (90, 105)])
        self.assertAlmostEqual(timeline.audio.duckedVolume, 0.25 * 10 ** (-18 / 20))
        self.assertIsNone(timeline.audio.music)                                    # no assets → voice only


class TimelineSchemaTests(unittest.TestCase):
    BASE = {"slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 60,
            "groups": [], "audio": {"voice": "audio/voz.mp3"}}
    MEDIA = {"src": "media/s000.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}

    def test_rejects_gaps_missing_credit_and_long_third_party_clips(self) -> None:
        shot = {"id": "s000", "type": "broll", "from": 0, "durationInFrames": 60, "text": "t", "media": self.MEDIA}
        Timeline.model_validate({**self.BASE, "shots": [shot]})
        for bad in (
            {**shot, "from": 5},
            {**shot, "media": {**self.MEDIA, "credit": None}},
            {**shot, "media": None},
        ):
            with self.assertRaises(ValidationError):
                Timeline.model_validate({**self.BASE, "shots": [bad]})
        with self.assertRaises(ValidationError):
            Timeline.model_validate({**self.BASE, "durationInFrames": 200, "shots": [{**shot, "durationInFrames": 200}]})


class ColdOpenTests(unittest.TestCase):
    def test_cold_open_goes_first_and_pushes_the_narration(self) -> None:
        base = Timeline.model_validate({
            "slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 60,
            "shots": [{"id": "s000", "type": "broll", "from": 0, "durationInFrames": 60, "text": "t",
                       "media": {"src": "media/s000.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}}],
            "groups": [{"id": "q01", "kind": "question", "from": 10, "durationInFrames": 20, "words": []}],
            "labels": [{"kind": "name", "text": "Kohei Uchimura", "from": 5, "durationInFrames": 30}],
            "audio": {"voice": "audio/voz.mp3", "speech": [(0, 30)]},
        })
        tl = with_cold_open(base, [("coldopen/c01.mp4", 3.5, "Fuente: Olympics", 1920, 1080),
                                   ("coldopen/c02.mp4", 9.0, "Fuente: FIG", 1080, 1920)], 30, 0.9)
        self.assertEqual([(s.id, s.from_, s.durationInFrames, s.coldOpen) for s in tl.shots],
                         [("c01", 0, 105, True), ("c02", 105, 150, True), ("s000", 255, 60, False)])   # 9 s → capped at 5 s
        self.assertEqual(tl.durationInFrames, 315)
        self.assertEqual(tl.shots[1].media.layout, "card")
        self.assertEqual((tl.groups[0].from_, tl.labels[0].from_), (265, 260))
        self.assertEqual(tl.audio.voiceFrom, 255)
        self.assertEqual(tl.audio.speech, [(255, 285)])
        self.assertEqual([(c.src, c.from_, c.volume) for c in tl.audio.clips],
                         [("coldopen/c01.mp4", 0, 0.9), ("coldopen/c02.mp4", 105, 0.9)])
        self.assertIs(with_cold_open(base, [], 30), base)


class SpeechTests(unittest.TestCase):
    def test_merges_close_words(self) -> None:
        words = WordsFile.model_validate({
            "slug": "t", "title": "T", "language": "es", "durationSeconds": 5.0,
            "words": [{"index": i, "text": "w", "start": s, "end": e, "matched": True}
                      for i, (s, e) in enumerate([(0, 0.4), (0.7, 1.0), (2.0, 2.5)])],
            "chapters": [], "alignment": {"provider": "l", "model": "m", "scriptWords": 3, "whisperWords": 3,
                                          "matchedWords": 3, "matchRatio": 1.0}})
        self.assertEqual(speech_segments(words, 30), [(0, 30), (60, 75)])


def _words(items: list[tuple[str, float, float]]) -> WordsFile:
    return WordsFile.model_validate({
        "slug": "t", "title": "T", "language": "es", "durationSeconds": 20.0,
        "words": [{"index": i, "text": t, "start": a, "end": b, "matched": True} for i, (t, a, b) in enumerate(items)],
        "chapters": [], "alignment": {"provider": "l", "model": "m", "scriptWords": 1, "whisperWords": 1,
                                      "matchedWords": 1, "matchRatio": 1.0}})


class QuestionTests(unittest.TestCase):
    WORDS = _words([
        ("Pero", 0.0, 0.3), ("la", 0.3, 0.4), ("pregunta", 0.4, 0.8), ("es:", 0.8, 1.0),
        ("¿sabes", 1.0, 1.3), ("cuánto", 1.3, 1.6), ("gana?", 1.6, 2.0),
        ("Y", 2.5, 2.6), ("sobre", 2.6, 2.8), ("todo,", 2.8, 3.0), ("¿sabes", 3.0, 3.3), ("cómo?", 3.3, 3.6),
        ("Fin.", 8.0, 8.4), ("Esto", 12.0, 12.2), ("vale?", 12.2, 12.6),
    ])

    def test_finds_questions_with_and_without_opening_mark(self) -> None:
        self.assertEqual(question_spans(self.WORDS), [(4, 6), (10, 11), (13, 14)])

    def test_merges_close_questions_and_avoids_chapters(self) -> None:
        from pipeline.schemas import TimelineShot
        shots = [TimelineShot.model_validate({"id": "s0", "type": "broll", "from": 0, "durationInFrames": 330, "text": "t"}),
                 TimelineShot.model_validate({"id": "s1", "type": "chapter", "from": 330, "durationInFrames": 270, "text": "t"})]
        groups = question_groups(self.WORDS, shots, [], 30, 600, {"opening_question": False})   # merging only
        self.assertEqual(len(groups), 1)                    # "Esto vale?" falls on the chapter title → skipped
        q = groups[0]
        self.assertEqual(q.kind, "question")
        self.assertEqual(q.from_, 27)                       # 3 frames before "¿sabes"
        self.assertEqual(" ".join(w.text for w in q.words), "¿sabes cuánto gana? Y sobre todo, ¿sabes cómo?")
        self.assertEqual(q.words[-1].from_, 99 - 27)
        self.assertEqual(q.from_ + q.durationInFrames, 108 + 36)   # holds 1.2 s after the last word
        self.assertEqual(question_groups(self.WORDS, shots, [], 30, 600, {"questions": False}), [])


if __name__ == "__main__":
    unittest.main()
