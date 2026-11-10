from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.clients.pexels_client import PexelsError, PexelsRateLimitError
from pipeline.fetch_media import MediaFetchError, MediaOptions, fetch_media
from pipeline.qa import validate_scene_plan
from pipeline.third_party_media import OUTCOME_SEARCH_FAILED

from tests.helpers import FakeImages, FakePexels, FakeSelector, assets_dir_for, make_settings, scene


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.settings = make_settings(self.root)
        self.assets = assets_dir_for(self.root)
        self.checkpoint = self.root / "out" / "video.media.json"
        patcher = patch("pipeline.fetch_media.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_media(
        self,
        scenes: list[dict],
        *,
        selector: FakeSelector | None = None,
        pexels: FakePexels | None = None,
        images: FakeImages | None = None,
        third_party: bool = True,
        **option_overrides: object,
    ) -> list[dict]:
        options = MediaOptions(
            third_party_enabled=third_party,
            concurrency=option_overrides.pop("concurrency", 1),  # type: ignore[arg-type]
            checkpoint_path=self.checkpoint,
            **option_overrides,  # type: ignore[arg-type]
        )
        with patch("pipeline.fetch_media.select_third_party_clip", side_effect=selector or FakeSelector()):
            return fetch_media(
                scenes,  # type: ignore[arg-type]
                self.settings,
                assets_dir=self.assets,
                options=options,
                pexels=pexels or FakePexels(),  # type: ignore[arg-type]
                images=images or FakeImages(),
                youtube=object() if third_party else None,  # type: ignore[arg-type]
                judge=object() if third_party else None,  # type: ignore[arg-type]
            )  # type: ignore[return-value]


class TemplateNeedsTests(_Base):
    def test_templates_without_media_trigger_no_lookups(self) -> None:
        selector, pexels, images = FakeSelector(), FakePexels(), FakeImages()
        scenes = [
            scene("blueprint-data-panel", "stat"),
            scene("timeline-graphic", "narrative"),
            scene("comparison-panel", "stat"),
            scene("title-card", "transition"),
            scene("whip-transition", "transition", durationInFrames=8),
        ]
        resolved = self.run_media(scenes, selector=selector, pexels=pexels, images=images)

        self.assertEqual(selector.calls, [])
        self.assertEqual(pexels.calls, [])
        self.assertEqual(images.calls, [])
        for item in resolved:
            self.assertNotIn("imageUrl", item)
            self.assertNotIn("videoUrl", item)

    def test_youtube_clip_on_default_narrative_template_passes_qa(self) -> None:
        resolved = self.run_media([scene("kenburns-image")], pexels=FakePexels())

        item = resolved[0]
        self.assertEqual(item["mediaProvider"], "youtube")
        self.assertTrue(item["videoUrl"].startswith("/pipeline-assets/run/third-party/clips/"))
        self.assertEqual(item["mediaClipDurationSeconds"], 4.5)
        self.assertEqual(item["mediaUploader"], "Uploader")
        self.assertEqual(item["mediaSourceUrl"], "https://www.youtube.com/watch?v=auto0000001")
        self.assertEqual(item["mediaStartSeconds"], 10.0)
        self.assertEqual(item["mediaEndSeconds"], 14.5)
        errors = [issue for issue in validate_scene_plan(resolved, 5.0) if issue.level == "error"]  # type: ignore[arg-type]
        self.assertEqual(errors, [])

    def test_montage_combines_youtube_and_pexels_shots_with_provenance(self) -> None:
        resolved = self.run_media([scene("multi-shot-montage")])

        shots = resolved[0]["shots"]
        self.assertEqual([shot["provider"] for shot in shots], ["youtube", "youtube", "pexels", "pexels"])
        self.assertTrue(all(shot["durationInSeconds"] <= 5 for shot in shots if shot["provider"] == "youtube"))
        self.assertEqual(len({shot["videoId"] for shot in shots if shot["provider"] == "youtube"}), 2)
        self.assertEqual(resolved[0]["mediaProvider"], "youtube")
        self.assertEqual(resolved[0]["mediaSourceUrl"], shots[0]["sourceUrl"])


class FallbackTests(_Base):
    def test_falls_back_to_pexels_and_stores_a_local_copy(self) -> None:
        pexels = FakePexels()
        resolved = self.run_media([scene("lower-third")], selector=FakeSelector(miss=True), pexels=pexels)

        item = resolved[0]
        self.assertEqual(item["mediaProvider"], "pexels")
        self.assertTrue(item["videoUrl"].startswith("/pipeline-assets/run/stock/"))
        self.assertTrue(item["mediaRemoteUrl"].startswith("https://videos.pexels.com/"))
        self.assertEqual(item["mediaPhotographer"], "Ana")
        self.assertEqual(pexels.downloads, [item["mediaRemoteUrl"]])

    def test_failed_local_copy_keeps_remote_url(self) -> None:
        pexels = FakePexels(download_error=PexelsError("boom"))
        resolved = self.run_media([scene("lower-third")], selector=FakeSelector(miss=True), pexels=pexels)
        self.assertTrue(resolved[0]["videoUrl"].startswith("https://videos.pexels.com/"))

    def test_pexels_network_error_degrades_to_generated_image(self) -> None:
        images = FakeImages()
        resolved = self.run_media(
            [scene("kenburns-image")],
            third_party=False,
            pexels=FakePexels(error=PexelsError("timeout")),
            images=images,
        )
        self.assertEqual(resolved[0]["mediaProvider"], "openai-image")
        self.assertTrue(resolved[0]["imageUrl"].startswith("/pipeline-assets/run/images/"))
        self.assertEqual(len(images.calls), 1)

    def test_rate_limit_disables_pexels_for_remaining_scenes(self) -> None:
        pexels = FakePexels(error=PexelsRateLimitError("429"))
        images = FakeImages()
        self.run_media(
            [scene("kenburns-image"), scene("kenburns-image", text="Otra")],
            third_party=False,
            pexels=pexels,
            images=images,
        )
        self.assertEqual(len(pexels.calls), 1)
        self.assertEqual(len(images.calls), 2)

    def test_hook_and_stat_fallback_images_use_high_quality(self) -> None:
        images = FakeImages()
        self.run_media(
            [scene("kinetic-text-hook", "hook"), scene("lower-third")],
            third_party=False,
            pexels=FakePexels(videos=False, images=False),
            images=images,
        )
        self.assertEqual([quality for _prompt, quality in images.calls], ["high", "medium"])

    def test_image_failure_is_reported_and_other_scenes_survive_in_checkpoint(self) -> None:
        scenes = [scene("lower-third"), scene("kenburns-image", text="Sin nada")]
        empty_pexels = FakePexels(videos=False, images=False)
        selector = FakeSelector(video_ids=["onlyone0001"])  # second scene gets no clip
        with self.assertRaisesRegex(MediaFetchError, "escenas 2") as raised:
            self.run_media(scenes, selector=selector, pexels=empty_pexels, images=FakeImages(fail_times=5))
        self.assertIn("content policy", str(raised.exception))

        # Re-running retries only the failed scene.
        selector_again = FakeSelector(miss=True)
        images = FakeImages()
        resolved = self.run_media(scenes, selector=selector_again, pexels=empty_pexels, images=images)
        self.assertEqual(resolved[0]["mediaProvider"], "youtube")
        self.assertEqual(resolved[1]["mediaProvider"], "openai-image")
        self.assertEqual(len(images.calls), 1)
        self.assertEqual(len(selector_again.calls), 0)  # the genuine miss was remembered


class CheckpointTests(_Base):
    def test_second_run_reuses_everything(self) -> None:
        scenes = [scene("kenburns-image"), scene("lower-third", text="Dos"), scene("multi-shot-montage", text="Tres")]
        first = self.run_media(scenes)

        selector, pexels, images = FakeSelector(), FakePexels(), FakeImages()
        second = self.run_media(scenes, selector=selector, pexels=pexels, images=images)

        self.assertEqual(selector.calls, [])
        self.assertEqual(pexels.calls, [])
        self.assertEqual(images.calls, [])
        self.assertEqual(first, second)

    def test_fresh_run_ignores_checkpoint(self) -> None:
        scenes = [scene("kenburns-image")]
        self.run_media(scenes)
        selector = FakeSelector()
        self.run_media(scenes, selector=selector, resume=False)
        self.assertEqual(len(selector.calls), 1)

    def test_changed_scene_is_resolved_again(self) -> None:
        self.run_media([scene("kenburns-image")])
        selector = FakeSelector()
        self.run_media([scene("kenburns-image", keywords=["slot machine"])], selector=selector)
        self.assertEqual(len(selector.calls), 1)

    def test_missing_local_file_invalidates_reuse(self) -> None:
        scenes = [scene("kenburns-image")]
        first = self.run_media(scenes)
        (self.root / "public" / first[0]["videoUrl"].lstrip("/")).unlink()
        selector = FakeSelector()
        self.run_media(scenes, selector=selector)
        self.assertEqual(len(selector.calls), 1)

    def test_redo_scene_avoids_previous_pick_and_keeps_the_rest(self) -> None:
        scenes = [scene("kenburns-image"), scene("lower-third", text="Dos")]
        first = self.run_media(scenes, selector=FakeSelector(video_ids=["aaaaaaaaaaa", "bbbbbbbbbbb"]))
        self.assertEqual(first[1]["mediaVideoId"], "bbbbbbbbbbb")

        selector = FakeSelector(video_ids=["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])
        second = self.run_media(scenes, selector=selector, redo_scenes=frozenset({2}))

        self.assertEqual(len(selector.calls), 1)
        self.assertEqual(second[0], first[0])
        self.assertEqual(second[1]["mediaVideoId"], "ccccccccccc")

    def test_redo_unknown_scene_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(MediaFetchError, "No existen las escenas"):
            self.run_media([scene("kenburns-image")], redo_scenes=frozenset({9}))


class ParallelAndHealthTests(_Base):
    def test_parallel_scenes_never_share_a_video(self) -> None:
        scenes = [scene("lower-third", text=f"Escena {index}") for index in range(12)]
        selector = FakeSelector(video_ids=[f"vid{index:08d}" for index in range(12)])
        resolved = self.run_media(scenes, selector=selector, concurrency=4)

        ids = [item["mediaVideoId"] for item in resolved]
        self.assertEqual(len(set(ids)), 12)
        self.assertEqual(len(selector.calls), 12)

    def test_youtube_is_switched_off_after_repeated_search_failures(self) -> None:
        calls: list[int] = []

        def failing_selector(**kwargs: object) -> None:
            calls.append(1)
            trace = kwargs["trace"]
            trace.queries = ["a", "b"]  # type: ignore[attr-defined]
            trace.search_errors = ["a: blocked", "b: blocked"]  # type: ignore[attr-defined]
            trace.outcome = OUTCOME_SEARCH_FAILED  # type: ignore[attr-defined]
            return None

        scenes = [scene("lower-third", text=f"Escena {index}") for index in range(8)]
        with patch("pipeline.fetch_media.select_third_party_clip", side_effect=failing_selector):
            resolved = fetch_media(
                scenes,  # type: ignore[arg-type]
                self.settings,
                assets_dir=self.assets,
                options=MediaOptions(concurrency=1, checkpoint_path=self.checkpoint),
                pexels=FakePexels(),  # type: ignore[arg-type]
                images=FakeImages(),
                youtube=object(),  # type: ignore[arg-type]
                judge=object(),  # type: ignore[arg-type]
            )
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(item["mediaProvider"] == "pexels" for item in resolved))

        # An outage is not remembered as the final answer: the same command,
        # run again, tries YouTube for every scene that had to fall back.
        selector = FakeSelector()
        again = self.run_media(scenes, selector=selector)
        self.assertEqual(len(selector.calls), 8)
        self.assertTrue(all(item["mediaProvider"] == "youtube" for item in again))


class OverrideTests(_Base):
    def test_local_file_override_skips_every_provider(self) -> None:
        source = self.root / "plano.mp4"
        source.write_bytes(b"video")
        selector, pexels = FakeSelector(), FakePexels()
        with patch("pipeline.fetch_media.probe_duration_seconds", return_value=7.5):
            resolved = self.run_media(
                [scene("lower-third", mediaOverride=str(source))], selector=selector, pexels=pexels
            )
        item = resolved[0]
        self.assertEqual(item["mediaProvider"], "local")
        self.assertEqual(item["videoUrl"], "/pipeline-assets/run/overrides/scene-001.mp4")
        self.assertEqual(item["videoDurationInSeconds"], 7.5)
        self.assertEqual(selector.calls, [])
        self.assertEqual(pexels.calls, [])


if __name__ == "__main__":
    unittest.main()
