from __future__ import annotations

import unittest

from pipeline.render import condensed_props, music_volume_expr, plan_segments

VIDEO = {"src": "media/a.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}
IMAGE = {"src": "media/b.jpg", "kind": "image", "source": "wikimedia", "credit": "Fuente: Y"}


def _shot(i: int, start: int, frames: int, kind: str = "broll", media=VIDEO, group=None) -> dict:
    return {"id": f"s{i:03d}", "type": kind, "from": start, "durationInFrames": frames, "text": "t",
            "media": media, "groupId": group}


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timeline = {
            "durationInFrames": 300,
            "shots": [
                _shot(0, 0, 60),                             # fast
                _shot(1, 60, 60, "chapter"),                 # slow
                _shot(2, 120, 60, media=IMAGE),              # slow (Ken Burns)
                _shot(3, 180, 60, "stat", group="stat-s003"),  # slow
                _shot(4, 240, 60),                           # fast
            ],
            "groups": [{"id": "stat-s003", "kind": "stat", "from": 180, "durationInFrames": 60, "steps": []}],
            "audio": {"voice": "audio/voz.mp3", "musicVolume": 0.25, "duckedVolume": 0.03, "speech": [[0, 30]], "sfx": []},
        }

    def test_fast_shots_go_to_ffmpeg_and_slow_runs_merge(self) -> None:
        segments = plan_segments(self.timeline)
        self.assertEqual([(s.kind, s.start, s.frames) for s in segments],
                         [("ffmpeg", 0, 60), ("remotion", 60, 180), ("ffmpeg", 240, 60)])
        self.assertEqual(sum(s.frames for s in segments), 300)
        self.assertEqual([s.kind for s in plan_segments(self.timeline, hybrid=False)], ["remotion"])

    def test_condensed_timeline_shifts_shots_and_groups(self) -> None:
        props = condensed_props(self.timeline, plan_segments(self.timeline))
        self.assertEqual([(s["id"], s["from"]) for s in props["shots"]], [("s001", 0), ("s002", 60), ("s003", 120)])
        self.assertEqual(props["groups"][0]["from"], 120)
        self.assertEqual(props["durationInFrames"], 180)
        self.assertEqual(props["audio"]["speech"], [])


class QuestionRenderTests(unittest.TestCase):
    def test_group_starting_mid_shot_makes_its_shots_slow(self) -> None:
        timeline = {
            "durationInFrames": 180,
            "shots": [_shot(0, 0, 60), _shot(1, 60, 60), _shot(2, 120, 60)],
            "groups": [{"id": "q01", "kind": "question", "from": 80, "durationInFrames": 50, "steps": [], "words": []}],
            "audio": {"voice": "v", "musicVolume": 0.2, "duckedVolume": 0.02, "speech": [], "sfx": []},
        }
        segments = plan_segments(timeline)
        self.assertEqual([(s.kind, s.start, s.frames) for s in segments], [("ffmpeg", 0, 60), ("remotion", 60, 120)])
        props = condensed_props(timeline, segments)
        self.assertEqual(props["groups"][0]["from"], 20)


class DuckingTests(unittest.TestCase):
    def test_expression_matches_audiobed(self) -> None:
        expr = music_volume_expr([(30, 60)], 30, 120, 0.25, 0.05)

        def at(t: float) -> float:
            return eval(expr.replace("between", "_b").replace("min(", "_m("), {
                "_b": lambda x, a, b: 1.0 if a <= x <= b else 0.0, "_m": min, "t": t})

        self.assertAlmostEqual(at(0.0), 0.25)          # before any speech (no ramp at the start)
        self.assertAlmostEqual(at(1.5), 0.05)          # during speech: ducked
        self.assertAlmostEqual(at(2.0 + 4 / 30), 0.05 + 0.20 * 0.5, places=3)   # half-way up the 8-frame ramp
        self.assertAlmostEqual(at(3.9), 0.25)          # back to full
        self.assertEqual(music_volume_expr([], 30, 120, 0.25, 0.05), "0.25000")


if __name__ == "__main__":
    unittest.main()
