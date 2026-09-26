from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from pipeline.context import RunContext
from pipeline.schemas import Timeline, WordsFile
from pipeline.timeline import run, speech_segments

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
            for sid, kind, ext in (("s000", "video", "mp4"), ("s001", "image", "jpg")):
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
        self.assertIsNone(timeline.shots[4].media.credit)                          # generated: no credit badge
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


class SpeechTests(unittest.TestCase):
    def test_merges_close_words(self) -> None:
        words = WordsFile.model_validate({
            "slug": "t", "title": "T", "language": "es", "durationSeconds": 5.0,
            "words": [{"index": i, "text": "w", "start": s, "end": e, "matched": True}
                      for i, (s, e) in enumerate([(0, 0.4), (0.7, 1.0), (2.0, 2.5)])],
            "chapters": [], "alignment": {"provider": "l", "model": "m", "scriptWords": 3, "whisperWords": 3,
                                          "matchedWords": 3, "matchRatio": 1.0}})
        self.assertEqual(speech_segments(words, 30), [(0, 30), (60, 75)])


if __name__ == "__main__":
    unittest.main()
