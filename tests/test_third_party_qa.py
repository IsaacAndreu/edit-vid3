from __future__ import annotations

import unittest

from pipeline.qa import validate_scene_plan


class ThirdPartyClipQATests(unittest.TestCase):
    def test_accepts_youtube_scene_clip_at_five_second_limit(self) -> None:
        scenes = [
            {
                "templateName": "lower-third",
                "sceneType": "narrative",
                "durationInFrames": 60,
                "accentColor": "#ffffff",
                "text": "Robot factory",
                "videoUrl": "/pipeline-assets/clip.mp4",
                "videoDurationInSeconds": 5.0,
                "mediaProvider": "youtube",
                "mediaClipDurationSeconds": 5.0,
            }
        ]
        issues = validate_scene_plan(scenes, 2.0)
        self.assertFalse([issue for issue in issues if issue.level == "error"])

    def test_blocks_youtube_scene_clip_over_five_seconds(self) -> None:
        scenes = [
            {
                "templateName": "lower-third",
                "sceneType": "narrative",
                "durationInFrames": 60,
                "accentColor": "#ffffff",
                "text": "Robot factory",
                "videoUrl": "/pipeline-assets/clip.mp4",
                "videoDurationInSeconds": 5.2,
                "mediaProvider": "youtube",
                "mediaClipDurationSeconds": 5.2,
            }
        ]
        issues = validate_scene_plan(scenes, 2.0)
        self.assertIn("third-party-clip-over-limit", {issue.code for issue in issues})

    def test_blocks_youtube_montage_shot_over_five_seconds(self) -> None:
        scenes = [
            {
                "templateName": "multi-shot-montage",
                "sceneType": "narrative",
                "durationInFrames": 60,
                "accentColor": "#ffffff",
                "text": "Robots at work",
                "shots": [
                    {
                        "url": "/pipeline-assets/clip.mp4",
                        "type": "video",
                        "provider": "youtube",
                        "durationInSeconds": 5.01,
                    }
                ],
            }
        ]
        issues = validate_scene_plan(scenes, 2.0)
        self.assertIn("third-party-clip-over-limit", {issue.code for issue in issues})

    def test_warns_youtube_clip_will_hold_last_frame_in_longer_scene(self) -> None:
        scenes = [
            {
                "templateName": "lower-third",
                "sceneType": "narrative",
                "durationInFrames": 300,
                "accentColor": "#ffffff",
                "text": "Robot factory",
                "videoUrl": "/pipeline-assets/clip.mp4",
                "videoDurationInSeconds": 5.0,
                "mediaProvider": "youtube",
                "mediaClipDurationSeconds": 5.0,
            }
        ]

        issues = validate_scene_plan(scenes, 10.0)

        warning = next(issue for issue in issues if issue.level == "warning")
        self.assertEqual(warning.code, "short-third-party-video")
        self.assertIn("último fotograma", warning.message)


if __name__ == "__main__":
    unittest.main()
