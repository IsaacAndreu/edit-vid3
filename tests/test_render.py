from __future__ import annotations

import unittest
from pathlib import Path

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
        # only the frames under the question go to Remotion; the footage before and after stays in ffmpeg
        self.assertEqual([(s.kind, s.start, s.frames, s.offset) for s in segments],
                         [("ffmpeg", 0, 60, 0), ("ffmpeg", 60, 20, 0), ("remotion", 80, 50, 0), ("ffmpeg", 130, 50, 10)])
        props = condensed_props(timeline, segments)
        self.assertEqual(props["groups"][0]["from"], 0)
        self.assertEqual([(s["id"], s["from"], s["durationInFrames"], s["offset"], s["fullDuration"]) for s in props["shots"]],
                         [("s001~20", 0, 40, 20, 60), ("s002~0", 40, 10, 0, 60)])


class LayoutRenderTests(unittest.TestCase):
    def test_cards_and_labels_go_to_remotion(self) -> None:
        card = {**VIDEO, "layout": "card"}
        timeline = {
            "durationInFrames": 240,
            "shots": [_shot(0, 0, 60), _shot(1, 60, 60, media=card), _shot(2, 120, 60), _shot(3, 180, 60)],
            "groups": [],
            "labels": [{"kind": "name", "text": "Kohei Uchimura", "from": 124, "durationInFrames": 30}],
            "audio": {"voice": "v", "musicVolume": 0.2, "duckedVolume": 0.02, "speech": [], "sfx": []},
        }
        segments = plan_segments(timeline)
        # a framed card with nothing over it is composed by ffmpeg too; the label covers frames 124-154 of s002
        # and the 4 frames before it are too few for their own segment
        self.assertEqual([(s.kind, s.start, s.frames) for s in segments],
                         [("ffmpeg", 0, 60), ("ffmpeg", 60, 60), ("remotion", 120, 34), ("ffmpeg", 154, 26),
                          ("ffmpeg", 180, 60)])
        self.assertEqual(condensed_props(timeline, segments)["labels"][0]["from"], 4)
        timeline["labels"][0]["from"] = 70                       # a label over the card: the whole card to Remotion
        self.assertEqual([(s.kind, s.start, s.frames) for s in plan_segments(timeline)][1], ("remotion", 60, 60))

    def test_the_end_screen_is_its_own_cached_segment(self) -> None:
        timeline = {"durationInFrames": 120, "shots": [_shot(0, 0, 60), _shot(1, 60, 60, "endscreen", media=None)],
                    "groups": [], "audio": {"voice": "v", "musicVolume": 0.2, "duckedVolume": 0.02, "speech": [], "sfx": []}}
        self.assertEqual([(s.kind, s.start) for s in plan_segments(timeline)], [("ffmpeg", 0), ("endscreen", 60)])


class AudioMixTests(unittest.TestCase):
    def test_mixes_delayed_voice_cold_open_sound_music_and_sfx(self) -> None:
        import subprocess
        import tempfile

        from pipeline.context import RunContext
        from pipeline.ingest import probe
        from pipeline.render import Renderer

        def tone(path, seconds, freq, video=False):
            args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}"]
            if video:
                args += ["-f", "lavfi", "-i", f"color=black:s=320x180:d={seconds}", "-shortest"]
            subprocess.run([*args, str(path)], check=True)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = RunContext.create("t", root=root, config={"video": {"fps": 30}})
            for rel, secs, freq, video in (("audio/voz.wav", 1, 440, False), ("coldopen/c01.mp4", 1, 880, True),
                                           ("audio/music.mp3", 1, 220, False), ("audio/pop.wav", 0.3, 1000, False)):
                (ctx.work_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                tone(ctx.work_dir / rel, secs, freq, video)
            timeline = {"durationInFrames": 90, "audio": {
                "voice": "audio/voz.wav", "voiceFrom": 30, "music": "audio/music.mp3", "musicVolume": 0.25,
                "duckedVolume": 0.03, "speech": [[30, 60]],
                "clips": [{"src": "coldopen/c01.mp4", "from": 0, "durationInFrames": 30, "volume": 1.0}],
                "sfx": [{"src": "audio/pop.wav", "from": 45, "volume": 0.5}]}}
            out = Renderer(ctx).audio(timeline)
            self.assertAlmostEqual(probe(out)["duration"], 3.0, delta=0.05)


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


def test_png_sequences_never_go_under_a_folder_with_a_dot(tmp_path):
    from pipeline.context import RunContext
    from pipeline.render import Renderer

    ctx = RunContext.create("video1.ice", root=tmp_path, config={"paths": {}})
    folder = Renderer(ctx).sequence_dir("badges")
    assert "." not in str(folder.relative_to(tmp_path)) if folder.is_relative_to(tmp_path) else "." not in folder.name
