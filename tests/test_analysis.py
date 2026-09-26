from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from pydantic import ValidationError

from pipeline.analysis import coarse_moments, entity_score, file_start, fine_options, storyboard_frames, total_score
from pipeline.analysis import detectors as det
from pipeline.schemas import Candidate, Option


def _board_candidate(root: Path, tiles: list[np.ndarray], duration: float, interval: float) -> Candidate:
    sheet = np.zeros((180 * 3, 320 * 3, 3), np.uint8)
    for i, tile in enumerate(tiles):
        y, x = divmod(i, 3)
        sheet[y * 180 : (y + 1) * 180, x * 320 : (x + 1) * 320] = tile
    cv2.imwrite(str(root / "sheet.jpg"), sheet)
    return Candidate.model_validate({
        "id": "yt:AAAAAAAAAAA", "source": "youtube", "kind": "video", "url": "u", "title": "t", "channel": "c",
        "license": "l", "credit": "Fuente: c", "attribution": "a", "query": "q", "rankScore": 0.1,
        "durationSeconds": duration,
        "storyboard": {"sheets": ["sheet.jpg"], "columns": 3, "rows": 3, "tileWidth": 320, "tileHeight": 180,
                       "interval": interval, "frames": len(tiles)},
    })


def _noise(seed: int, level: int = 128) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (180, 320, 3), dtype=np.uint8) // 2 + level // 2


class StoryboardFrameTests(unittest.TestCase):
    def test_skips_edges_blanks_and_repeats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tiles = [
                _noise(0),                                  # t=0   → first 5 % (intro)
                _noise(1),                                  # t=10  ok
                np.zeros((180, 320, 3), np.uint8),          # t=20  black
                _noise(1),                                  # t=30  same as t=10 → deduped
                _noise(2),                                  # t=40  ok
                np.full((180, 320, 3), 200, np.uint8),      # t=50  flat
                _noise(3),                                  # t=60  ok
                _noise(4),                                  # t=70  ok
                _noise(5),                                  # t=80  last 5 % (outro): 80+10 > 95
            ]
            candidate = _board_candidate(root, tiles, duration=90, interval=10)
            times, frames = storyboard_frames(candidate, root, {})
        self.assertEqual(times, [10, 40, 60, 70])
        self.assertEqual(len(frames), 4)

    def test_frame_cap_is_uniform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = _board_candidate(root, [_noise(i) for i in range(9)], duration=900, interval=10)
            times, _ = storyboard_frames(candidate, root, {"max_frames_per_video": 3, "edge_margin": 0})
        self.assertEqual(times, [0, 40, 80])


class MomentTests(unittest.TestCase):
    def test_best_moments_are_spread_out(self) -> None:
        times = np.array([0, 5, 10, 15, 20, 25, 30], np.float32)
        sims = np.array([0.1, 0.30, 0.29, 0.1, 0.1, 0.25, 0.1], np.float32)
        self.assertEqual([t for t, _ in coarse_moments(times, sims, 5, 2)], [5, 25])


class ScoringTests(unittest.TestCase):
    def test_entity_from_transcript_then_title(self) -> None:
        captions = [(95.0, 99.0, "welcome to the Gran Casino de Madrid"), (300.0, 303.0, "nothing")]
        self.assertEqual(entity_score(captions, "vlog", ["Gran Casino de Madrid"], 100, 104), 1.0)
        self.assertEqual(entity_score(captions, "Casino Gran Madrid tour", ["Gran Casino de Madrid"], 200, 204), 0.5)
        self.assertEqual(entity_score(captions, "vlog", ["Gran Casino de Madrid"], 200, 204), 0.0)
        self.assertEqual(entity_score(captions, "vlog", [], 100, 104), 0.0)

    def test_total_uses_weights(self) -> None:
        scores = {"clip": 0.3, "entity": 1.0, "sharpness": 0.5, "motion": 1.0}
        self.assertAlmostEqual(total_score(scores, {"clip": 1, "entity": 0.04, "sharpness": 0.02, "motion": 0.01}), 0.36)

    def test_option_enforces_five_second_cap(self) -> None:
        base = {"candidateId": "yt:x", "source": "youtube", "kind": "video", "pass": "fine",
                "scores": {"clip": 0.3}, "total": 0.3}
        Option.model_validate({**base, "start": 10, "end": 15})
        with self.assertRaises(ValidationError):
            Option.model_validate({**base, "start": 10, "end": 15.2})
        with self.assertRaises(ValidationError):
            Option.model_validate({**base, "start": 10})

    def test_phash_and_file_start(self) -> None:
        a, b = _noise(1), _noise(1)
        self.assertEqual(det.hamming(det.phash(a), det.phash(b)), 0)
        self.assertGreater(det.hamming(det.phash(a), det.phash(_noise(9))), 10)
        self.assertEqual(file_start(Path("cache/videos/x/a360_120.50_130.00.mp4")), 120.5)


class _FakeClip:
    def embed_images(self, images):
        # brightness-based fake embedding: bright frames match the "shot" better
        return np.array([[float(im.mean()) / 255.0, 1.0] for im in images], np.float32)


class _FakeDetectors:
    def __init__(self, text=0.0, face=(0.0, 0.5)):
        self.text, self.face = text, face

    def text_area(self, frame):
        return self.text

    def face_area(self, frame):
        return self.face


class FineTests(unittest.TestCase):
    def _video(self, path: Path, seconds: int = 12) -> None:
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 180))
        rng = np.random.default_rng(0)
        for i in range(seconds * 10):
            level = 60 if i < 60 else 200            # a hard cut at 6 s: dark scene, then bright scene
            frame = np.clip(rng.normal(level, 30, (180, 320, 3)), 0, 255).astype(np.uint8)
            writer.write(frame)
        writer.release()

    def test_best_span_inside_one_scene_in_source_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a360_100.00_112.00.mp4"
            self._video(path)
            shot_vector = np.array([1.0, 0.0], np.float32)
            results = fine_options(window_path=path, window=(100.0, 112.0), needed=3.0, shot_vector=shot_vector,
                                   clip=_FakeClip(), detectors=_FakeDetectors(), cfg={})
            best = max(results, key=lambda r: r["scores"]["clip"])
            self.assertGreaterEqual(best["start"], 106.0 - 0.2)           # inside the bright scene
            self.assertLessEqual(best["end"], 112.0 + 1e-6)
            self.assertAlmostEqual(best["end"] - best["start"], 3.0)
            self.assertIsNone(best["discarded"])

            heavy_text = fine_options(window_path=path, window=(100.0, 112.0), needed=3.0, shot_vector=shot_vector,
                                      clip=_FakeClip(), detectors=_FakeDetectors(text=0.3), cfg={})
            self.assertTrue(all("texto" in r["discarded"] for r in heavy_text))
            presenter = fine_options(window_path=path, window=(100.0, 112.0), needed=3.0, shot_vector=shot_vector,
                                     clip=_FakeClip(), detectors=_FakeDetectors(face=(0.12, 0.5)), cfg={})
            self.assertTrue(all(r["discarded"] == "presentador hablando a cámara" for r in presenter))


if __name__ == "__main__":
    unittest.main()
