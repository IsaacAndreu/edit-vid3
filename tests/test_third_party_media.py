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


class StoryboardYouTube(FakeYouTube):
    """FakeYouTube that also offers seek-bar storyboards for some videos."""

    def __init__(self, candidates: list[YouTubeCandidate], *, without_storyboard: set[str] | None = None) -> None:
        super().__init__(candidates)
        self.without_storyboard = without_storyboard or set()
        self.storyboard_calls: list[str] = []

    def storyboard_sheet(
        self,
        candidate: YouTubeCandidate,
        _start: float,
        _end: float,
        output_path: Path,
    ) -> Path | None:
        self.storyboard_calls.append(candidate.video_id)
        if candidate.video_id in self.without_storyboard:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"preview")
        return output_path


class SequenceJudge:
    """Returns one prepared judgment list per call, in order."""

    def __init__(self, rounds: list[list[tuple[int, float, str]]]) -> None:
        self.rounds = rounds
        self.calls: list[tuple[str, list[str], list[Path]]] = []

    def judge(self, intent: str, candidates: list[ScoredSegment], sheets: list[Path]) -> list[tuple[int, float, str]]:
        self.calls.append((intent, [segment.candidate.video_id for segment in candidates], list(sheets)))
        return self.rounds.pop(0)


def three_segments(candidates: list[YouTubeCandidate]) -> list[ScoredSegment]:
    return [
        ScoredSegment(candidate, 10.0 + index, 14.0 + index, 0.8 - index * 0.1, "robot assembly")
        for index, candidate in enumerate(candidates)
    ]


class StoryboardPreviewTests(unittest.TestCase):
    def test_preview_ranks_with_storyboards_and_downloads_only_the_winner(self) -> None:
        candidates = [make_candidate(index) for index in range(1, 4)]
        youtube = StoryboardYouTube(candidates)
        judge = SequenceJudge(
            [
                [(0, 0.4, "train"), (1, 0.9, "robots"), (2, 0.6, "factory")],  # storyboard preview
                [(0, 0.88, "robot assembly line confirmed")],  # verification on real frames
            ]
        )
        segments = three_segments(candidates)
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pipeline.third_party_media.score_candidate_segments", side_effect=[[segment] for segment in segments]
        ), patch("pipeline.third_party_media.create_contact_sheet", side_effect=lambda _clip, path, **_kw: path):
            used_ids: set[str] = set()
            selected = select_third_party_clip(
                visual_intent="robots assembling cars",
                keywords=["robot factory"],
                youtube=youtube,  # type: ignore[arg-type]
                judge=judge,  # type: ignore[arg-type]
                assets_dir=Path(temp_dir),
                used_video_ids=used_ids,
            )

        assert selected is not None
        self.assertEqual(selected.candidate.video_id, candidates[1].video_id)
        self.assertEqual(selected.visual_score, 0.88)
        self.assertEqual(len(youtube.download_calls), 1, "only the storyboard winner is downloaded")
        self.assertEqual(youtube.download_calls[0][0], candidates[1].video_id)
        self.assertEqual(len(youtube.storyboard_calls), 3)
        self.assertEqual(len(judge.calls), 2)
        self.assertIn("storyboard", judge.calls[0][0])
        self.assertEqual(judge.calls[1][1], [candidates[1].video_id])
        self.assertEqual(used_ids, {candidates[1].video_id})

    def test_failed_verification_moves_to_next_finalist(self) -> None:
        candidates = [make_candidate(index) for index in range(1, 4)]
        youtube = StoryboardYouTube(candidates)
        judge = SequenceJudge(
            [
                [(0, 0.9, "looks right"), (1, 0.7, "maybe"), (2, 0.2, "no")],
                [(0, 0.3, "actually a talking head")],  # winner rejected on real frames
                [(0, 0.7, "robots visible")],  # runner-up accepted
            ]
        )
        segments = three_segments(candidates)
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pipeline.third_party_media.score_candidate_segments", side_effect=[[segment] for segment in segments]
        ), patch("pipeline.third_party_media.create_contact_sheet", side_effect=lambda _clip, path, **_kw: path):
            selected = select_third_party_clip(
                visual_intent="robots assembling cars",
                keywords=["robot factory"],
                youtube=youtube,  # type: ignore[arg-type]
                judge=judge,  # type: ignore[arg-type]
                assets_dir=Path(temp_dir),
                used_video_ids=set(),
            )

        assert selected is not None
        self.assertEqual(selected.candidate.video_id, candidates[1].video_id)
        self.assertEqual([call[0] for call in youtube.download_calls], [candidates[0].video_id, candidates[1].video_id])

    def test_missing_storyboard_falls_back_to_downloading_every_finalist(self) -> None:
        candidates = [make_candidate(index) for index in range(1, 4)]
        youtube = StoryboardYouTube(candidates, without_storyboard={candidates[2].video_id})
        judge = SequenceJudge([[(0, 0.6, "train"), (1, 0.93, "robots"), (2, 0.7, "factory")]])
        segments = three_segments(candidates)
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pipeline.third_party_media.score_candidate_segments", side_effect=[[segment] for segment in segments]
        ), patch("pipeline.third_party_media.create_contact_sheet", side_effect=lambda _clip, path, **_kw: path):
            selected = select_third_party_clip(
                visual_intent="robots assembling cars",
                keywords=["robot factory"],
                youtube=youtube,  # type: ignore[arg-type]
                judge=judge,  # type: ignore[arg-type]
                assets_dir=Path(temp_dir),
                used_video_ids=set(),
            )

        assert selected is not None
        self.assertEqual(selected.candidate.video_id, candidates[1].video_id)
        self.assertEqual(len(youtube.download_calls), 3)
        self.assertEqual(len(judge.calls), 1)

    def test_preview_can_be_disabled(self) -> None:
        candidates = [make_candidate(index) for index in range(1, 3)]
        youtube = StoryboardYouTube(candidates)
        judge = SequenceJudge([[(0, 0.6, "train"), (1, 0.93, "robots")]])
        segments = three_segments(candidates)
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pipeline.third_party_media.score_candidate_segments", side_effect=[[segment] for segment in segments]
        ), patch("pipeline.third_party_media.create_contact_sheet", side_effect=lambda _clip, path, **_kw: path):
            select_third_party_clip(
                visual_intent="robots assembling cars",
                keywords=["robot factory"],
                youtube=youtube,  # type: ignore[arg-type]
                judge=judge,  # type: ignore[arg-type]
                assets_dir=Path(temp_dir),
                used_video_ids=set(),
                preview_with_storyboards=False,
            )
        self.assertEqual(youtube.storyboard_calls, [])
        self.assertEqual(len(youtube.download_calls), 2)


if __name__ == "__main__":
    unittest.main()
