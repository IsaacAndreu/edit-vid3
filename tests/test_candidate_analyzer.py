from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

from pipeline.candidate_analyzer import (
    DeepSeekVisualJudge,
    ScoredSegment,
    create_contact_sheet,
    score_candidate_segments,
)
from pipeline.clients.youtube_client import SubtitleCue, YouTubeCandidate


def make_candidate(
    subtitles: tuple[SubtitleCue, ...],
    *,
    title: str = "",
    description: str = "",
    duration_seconds: float = 30,
) -> YouTubeCandidate:
    return YouTubeCandidate(
        video_id="video-1",
        url="https://example.test/video-1",
        title=title,
        uploader="Uploader",
        description=description,
        duration_seconds=duration_seconds,
        view_count=1_000_000,
        thumbnail_url="https://example.test/thumb.jpg",
        query="query",
        subtitles=subtitles,
    )


class CandidateScoringTests(unittest.TestCase):
    def test_subtitle_evidence_ranks_relevant_windows_deterministically(self) -> None:
        candidate = make_candidate(
            (
                SubtitleCue(0, 1, "Un gato duerme tranquilamente."),
                SubtitleCue(1, 2, "Los gatos caminan por la calle."),
                SubtitleCue(2, 4, "Un perro salta sobre la cerca."),
                SubtitleCue(4, 6, "El perro juega en el parque."),
            ),
            title="Perros saltando cerca de una cerca",
        )

        first = score_candidate_segments(candidate, "perro salta", ["perro salta", "cerca"], top_k=3)
        second = score_candidate_segments(candidate, "perro salta", ["perro salta", "cerca"], top_k=3)

        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertEqual(first[0].start_seconds, 2)
        self.assertLessEqual(first[0].end_seconds - first[0].start_seconds, 5)
        self.assertIn("perro", first[0].transcript_excerpt)
        self.assertIn("Subtitle evidence", first[0].rationale)
        self.assertEqual(first, sorted(first, key=lambda segment: (-segment.relevance_score, segment.start_seconds, segment.end_seconds, segment.transcript_excerpt)))

    def test_normalizes_accents_punctuation_and_spanish_stopwords(self) -> None:
        candidate = make_candidate((SubtitleCue(3.2, 6.1, "La economía del mercado: ¡crisis financiera!"),))

        segments = score_candidate_segments(
            candidate,
            "economía de mercado",
            ["crisis financiera"],
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].start_seconds, 3.2)
        self.assertEqual(segments[0].end_seconds, 6.1)

    def test_metadata_nudge_cannot_create_or_dominate_subtitle_evidence(self) -> None:
        irrelevant = make_candidate(
            (SubtitleCue(1, 3, "A quiet morning beside the bank."),),
            title="bank robbery heist scene bank robbery",
            description="bank robbery heist",
        )

        self.assertEqual(
            score_candidate_segments(irrelevant, "heist in a bank", ["bank robbery scene"]),
            [],
        )

        supported = make_candidate(
            (SubtitleCue(2, 4, "A bank robbery suspect escapes the scene."),),
            title="bank robbery",
            description="heist",
        )
        segment = score_candidate_segments(supported, "heist in a bank", ["bank robbery scene"])[0]
        without_metadata = make_candidate(supported.subtitles)
        baseline = score_candidate_segments(without_metadata, "heist in a bank", ["bank robbery scene"])[0]
        self.assertGreater(segment.relevance_score, baseline.relevance_score)
        self.assertLessEqual(segment.relevance_score - baseline.relevance_score, 0.04)

    def test_timing_overlap_respects_duration_and_requested_clip_limit(self) -> None:
        candidate = make_candidate(
            (
                SubtitleCue(8, 10, "A rocket launches into orbit."),
                SubtitleCue(9.5, 12, "The rocket enters orbit."),
                SubtitleCue(20, 25, "A rocket launch lasts a long time."),
            ),
            duration_seconds=22,
        )

        segments = score_candidate_segments(
            candidate,
            "rocket launch into orbit",
            ["rocket orbit"],
            max_clip_seconds=3.5,
            top_k=5,
        )

        self.assertTrue(segments)
        self.assertTrue(all(segment.end_seconds <= 22 for segment in segments))
        self.assertTrue(all(segment.end_seconds - segment.start_seconds <= 3.5 for segment in segments))
        self.assertTrue(all(segment.start_seconds >= 8 for segment in segments))

        long_cue = make_candidate((SubtitleCue(0, 10, "A rocket launches into orbit."),))
        globally_capped = score_candidate_segments(
            long_cue,
            "rocket launch orbit",
            [],
            max_clip_seconds=20,
        )
        self.assertTrue(globally_capped)
        self.assertTrue(all(segment.end_seconds - segment.start_seconds <= 5 for segment in globally_capped))

    def test_no_subtitles_or_empty_query_returns_no_candidates(self) -> None:
        candidate = make_candidate(())
        self.assertEqual(score_candidate_segments(candidate, "mountain landscape", ["mountains"]), [])
        self.assertEqual(score_candidate_segments(candidate, "the and", []), [])

    def test_rejects_invalid_clip_limit(self) -> None:
        candidate = make_candidate((SubtitleCue(0, 1, "storm over the ocean"),))
        with self.assertRaises(ValueError):
            score_candidate_segments(candidate, "storm ocean", [], max_clip_seconds=float("nan"))


class ContactSheetTests(unittest.TestCase):
    def test_uses_ffprobe_and_ffmpeg_without_running_media_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "clip.mp4"
            output = Path(directory) / "nested" / "sheet.png"
            clip.touch()

            def fake_run(command: list[str], **_: object) -> SimpleNamespace:
                if command[0] == "ffprobe":
                    return SimpleNamespace(returncode=0, stdout='{"format":{"duration":"8"}}', stderr="")
                self.assertEqual(command[0], "ffmpeg")
                self.assertIn("fps=0.5000000000", command[command.index("-vf") + 1])
                Path(command[-1]).touch()
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch("pipeline.candidate_analyzer.subprocess.run", side_effect=fake_run) as run:
                result = create_contact_sheet(clip, output, frame_count=4)

            self.assertEqual(result, output)
            self.assertTrue(output.is_file())
            self.assertEqual(run.call_count, 2)

    def test_missing_media_tool_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "clip.mp4"
            clip.touch()
            with patch("pipeline.candidate_analyzer.subprocess.run", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(RuntimeError, "ffprobe.*PATH"):
                    create_contact_sheet(clip, Path(directory) / "sheet.png")


class DeepSeekVisualJudgeTests(unittest.TestCase):
    def _segment(self, index: int) -> ScoredSegment:
        candidate = make_candidate((SubtitleCue(0, 2, "A train crosses a bridge."),))
        return ScoredSegment(candidate, float(index), float(index + 2), 0.7, "A train crosses a bridge.")

    def test_posts_responses_payload_only_when_judge_is_invoked(self) -> None:
        judge = DeepSeekVisualJudge("secret-key")
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {"output_text": json.dumps({"judgments": [
                {"candidate_index": 0, "score": 0.92, "reason": "The train is clearly visible."}
            ]})},
        )
        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "read_bytes", return_value=b"image"), patch(
            "pipeline.candidate_analyzer.requests.post", return_value=response
        ) as post:
            result = judge.judge("a train crossing a bridge", [self._segment(0)], [Path("sheet.png")])

        self.assertEqual(result, [(0, 0.92, "The train is clearly visible.")])
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.deepseek.com/v1/responses")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-key")
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        user_content = payload["input"][0]["content"]
        self.assertEqual(user_content[1]["text"], "Contact sheet for candidate 0:")
        self.assertEqual(user_content[2]["type"], "input_image")
        self.assertTrue(user_content[2]["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(kwargs["timeout"], 45)

    def test_rejects_count_and_index_mismatches_and_invalid_json(self) -> None:
        judge = DeepSeekVisualJudge("secret-key")
        candidates = [self._segment(0), self._segment(1)]
        valid_image_patch = patch.object(Path, "is_file", return_value=True), patch.object(Path, "read_bytes", return_value=b"image")
        count_response = SimpleNamespace(
            status_code=200,
            json=lambda: {"output_text": '{"judgments":[{"candidate_index":0,"score":0.5,"reason":"ok"}]}'},
        )
        with valid_image_patch[0], valid_image_patch[1], patch(
            "pipeline.candidate_analyzer.requests.post", return_value=count_response
        ):
            with self.assertRaisesRegex(ValueError, "count"):
                judge.judge("train", candidates, [Path("one.png"), Path("two.png")])

        index_response = SimpleNamespace(
            status_code=200,
            json=lambda: {"output_text": json.dumps({"judgments": [
                {"candidate_index": 0, "score": 0.5, "reason": "first"},
                {"candidate_index": 0, "score": 0.7, "reason": "duplicate"},
            ]})},
        )
        with valid_image_patch[0], valid_image_patch[1], patch(
            "pipeline.candidate_analyzer.requests.post", return_value=index_response
        ):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                judge.judge("train", candidates, [Path("one.png"), Path("two.png")])

        invalid_json_response = SimpleNamespace(status_code=200, json=lambda: {"output_text": "not-json"})
        with valid_image_patch[0], valid_image_patch[1], patch(
            "pipeline.candidate_analyzer.requests.post", return_value=invalid_json_response
        ):
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                judge.judge("train", [candidates[0]], [Path("one.png")])

    def test_http_failure_does_not_expose_api_key(self) -> None:
        judge = DeepSeekVisualJudge("sensitive-key")
        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "read_bytes", return_value=b"image"), patch(
            "pipeline.candidate_analyzer.requests.post", side_effect=requests.Timeout("timed out")
        ):
            with self.assertRaises(RuntimeError) as error:
                judge.judge("train", [self._segment(0)], [Path("sheet.png")])
        self.assertNotIn("sensitive-key", str(error.exception))


if __name__ == "__main__":
    unittest.main()
