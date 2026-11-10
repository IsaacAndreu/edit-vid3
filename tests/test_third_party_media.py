from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.candidate_analyzer import ScoredSegment
from pipeline.clients.youtube_client import YouTubeCandidate
from pipeline.third_party_media import select_third_party_clip


def make_candidate(index: int) -> YouTubeCandidate:
    video_id = f"videoid{index:04d}"
    return YouTubeCandidate(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title=f"Candidate {index}",
        uploader="Uploader",
        description="Description",
        duration_seconds=120,
        view_count=10,
        thumbnail_url=None,
        query="robots",
    )


class FakeYouTube:
    def __init__(self, candidates: list[YouTubeCandidate]) -> None:
        self.candidates = candidates
        self.search_calls: list[str] = []
        self.download_calls: list[tuple[str, float, float, float]] = []

    def search(self, query: str, *, limit: int) -> list[YouTubeCandidate]:
        self.search_calls.append(query)
        return self.candidates[:limit]

    def download_clip(
        self,
        candidate: YouTubeCandidate,
        start_seconds: float,
        end_seconds: float,
        output_dir: Path,
        *,
        max_clip_seconds: float,
    ) -> Path:
        self.download_calls.append((candidate.video_id, start_seconds, end_seconds, max_clip_seconds))
        return output_dir / f"{candidate.video_id}-{start_seconds}.mp4"


class FakeJudge:
    def __init__(self, judgments: list[tuple[int, float, str]]) -> None:
        self.judgments = judgments
        self.received_candidates: list[ScoredSegment] = []
        self.received_intent = ""

    def judge(
        self,
        _intent: str,
        candidates: list[ScoredSegment],
        _contact_sheets: list[Path],
    ) -> list[tuple[int, float, str]]:
        self.received_intent = _intent
        self.received_candidates = candidates
        return self.judgments


class ThirdPartyMediaSelectionTests(unittest.TestCase):
    def test_judge_selects_visual_winner_and_reuses_downloaded_clip(self) -> None:
        candidates = [make_candidate(index) for index in range(1, 4)]
        youtube = FakeYouTube(candidates)
        judge = FakeJudge([(0, 0.6, "train maybe"), (1, 0.93, "robot assembly line"), (2, 0.7, "factory" )])
        segments = [
            ScoredSegment(candidate, 10.0 + index, 14.0 + index, 0.8 - index * 0.1, "robot assembly")
            for index, candidate in enumerate(candidates)
        ]

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pipeline.third_party_media.score_candidate_segments", side_effect=[[segment] for segment in segments]
        ) as score_mock, patch(
            "pipeline.third_party_media.create_contact_sheet", side_effect=lambda _clip, path, **_kw: path
        ):
            used_ids: set[str] = set()
            selected = select_third_party_clip(
                visual_intent="robots assembling cars",
                keywords=["robot factory", "assembly line"],
                transcript_context="Los robots ensamblan vehículos",
                selection_guidance="Must visibly include: robotic arm; Avoid: logos",
                youtube=youtube,  # type: ignore[arg-type]
                judge=judge,  # type: ignore[arg-type]
                assets_dir=Path(temp_dir),
                used_video_ids=used_ids,
            )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.candidate.video_id, candidates[1].video_id)
        self.assertEqual(selected.path.name, f"{candidates[1].video_id}-11.0.mp4")
        self.assertEqual(len(youtube.download_calls), 3)
        self.assertTrue(all(call[3] <= 5 for call in youtube.download_calls))
        self.assertEqual(used_ids, {candidates[1].video_id})
        self.assertEqual(len(judge.received_candidates), 3)
        self.assertIn("Los robots ensamblan vehículos", score_mock.call_args_list[0].args[2])
        self.assertIn("Must visibly include: robotic arm", judge.received_intent)
        self.assertIn("Los robots ensamblan vehículos", youtube.search_calls)

    def test_low_visual_score_rejects_candidate(self) -> None:
        candidate = make_candidate(1)
        youtube = FakeYouTube([candidate])
        judge = FakeJudge([(0, 0.54, "visual intent is unclear")])
        segment = ScoredSegment(candidate, 1, 4, 0.8, "robot assembly")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pipeline.third_party_media.score_candidate_segments", return_value=[segment]
        ), patch("pipeline.third_party_media.create_contact_sheet", side_effect=lambda _clip, path, **_kw: path):
            selected = select_third_party_clip(
                visual_intent="robots assembling cars",
                keywords=["robot factory"],
                youtube=youtube,  # type: ignore[arg-type]
                judge=judge,  # type: ignore[arg-type]
                assets_dir=Path(temp_dir),
                used_video_ids=set(),
            )

        self.assertIsNone(selected)
        self.assertEqual(len(youtube.download_calls), 1)



class SelectionRobustnessTests(unittest.TestCase):
    def _select(self, judge: object, youtube: FakeYouTube, segments: list[ScoredSegment], **extra: object):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pipeline.third_party_media.score_candidate_segments", side_effect=[[segment] for segment in segments]
        ), patch(
            "pipeline.third_party_media.create_contact_sheet", side_effect=lambda _clip, path, **_kw: path
        ), patch("pipeline.third_party_media.time.sleep"):
            return select_third_party_clip(
                visual_intent="robots assembling cars",
                keywords=["robot factory"],
                youtube=youtube,  # type: ignore[arg-type]
                judge=judge,  # type: ignore[arg-type]
                assets_dir=Path(temp_dir),
                **extra,  # type: ignore[arg-type]
            )

    def test_one_judge_failure_does_not_waste_downloaded_clips(self) -> None:
        from pipeline.third_party_media import SelectionTrace

        candidate = make_candidate(1)

        class FlakyJudge:
            def __init__(self) -> None:
                self.calls = 0

            def judge(self, *_args: object) -> list[tuple[int, float, str]]:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("DeepSeek visual judging failed with HTTP 502.")
                return [(0, 0.9, "robot arm visible")]

        judge = FlakyJudge()
        youtube = FakeYouTube([candidate])
        trace = SelectionTrace()
        selected = self._select(
            judge, youtube, [ScoredSegment(candidate, 1, 4, 0.8, "robot assembly")], used_video_ids=set(), trace=trace
        )

        self.assertIsNotNone(selected)
        self.assertEqual(judge.calls, 2)
        self.assertEqual(len(youtube.download_calls), 1)
        self.assertEqual(trace.outcome, "selected")
        self.assertTrue(trace.finalists[0]["selected"])
        self.assertEqual(trace.finalists[0]["visualScore"], 0.9)

    def test_winner_claimed_by_another_scene_falls_to_next_valid_candidate(self) -> None:
        candidates = [make_candidate(1), make_candidate(2)]
        used: set[str] = set()

        class RacingJudge:
            def judge(self, *_args: object) -> list[tuple[int, float, str]]:
                used.add(candidates[0].video_id)  # another scene takes the best one meanwhile
                return [(0, 0.95, "best"), (1, 0.7, "good enough")]

        segments = [ScoredSegment(candidate, 1, 4, 0.8, "robot assembly") for candidate in candidates]
        selected = self._select(RacingJudge(), FakeYouTube(candidates), segments, used_video_ids=used)

        assert selected is not None
        self.assertEqual(selected.candidate.video_id, candidates[1].video_id)

    def test_excluded_videos_are_never_shortlisted(self) -> None:
        candidates = [make_candidate(1), make_candidate(2)]
        youtube = FakeYouTube(candidates)
        judge = FakeJudge([(0, 0.9, "ok")])
        segments = [ScoredSegment(candidates[1], 1, 4, 0.8, "robot assembly")]
        selected = self._select(
            judge, youtube, segments, used_video_ids=set(), excluded_video_ids={candidates[0].video_id}
        )
        assert selected is not None
        self.assertEqual(selected.candidate.video_id, candidates[1].video_id)
        self.assertEqual([call[0] for call in youtube.download_calls], [candidates[1].video_id])

    def test_trace_marks_total_search_failure(self) -> None:
        from pipeline.third_party_media import SelectionTrace

        class DownYouTube(FakeYouTube):
            def search(self, query: str, *, limit: int) -> list[YouTubeCandidate]:
                raise RuntimeError("network unreachable")

        trace = SelectionTrace()
        selected = self._select(FakeJudge([]), DownYouTube([]), [], used_video_ids=set(), trace=trace)
        self.assertIsNone(selected)
        self.assertEqual(trace.outcome, "search-failed")
        self.assertTrue(trace.all_searches_failed)
        self.assertIn("network unreachable", trace.search_errors[0])

if __name__ == "__main__":
    unittest.main()
