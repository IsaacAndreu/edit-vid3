from __future__ import annotations

import re
import unittest
from pathlib import Path

from pipeline.qa import PipelineQualityError, enforce_qa, validate_scene_plan
from pipeline.segment import DEFAULT_TEMPLATE_BY_TYPE, VALID_TEMPLATE_NAMES, VALID_TEMPLATES_BY_TYPE
from pipeline.templates import PROJECT_ROOT, TemplateManifestError, load_manifest, parse_manifest


def _scene(**extra: object) -> dict:
    base: dict = {
        "templateName": "kenburns-image",
        "sceneType": "narrative",
        "durationInFrames": 150,
        "text": "Casino por dentro",
    }
    base.update(extra)
    return base


def _errors(scenes: list[dict], seconds: float = 5.0) -> list[str]:
    return [issue.code for issue in validate_scene_plan(scenes, seconds) if issue.level == "error"]  # type: ignore[arg-type]


class KenBurnsMediaRuleTests(unittest.TestCase):
    def test_youtube_clip_on_kenburns_is_renderable(self) -> None:
        scene = _scene(
            videoUrl="/pipeline-assets/x/third-party/clips/youtube_abc.mp4",
            videoDurationInSeconds=5.0,
            mediaProvider="youtube",
            mediaClipDurationSeconds=5.0,
        )
        self.assertEqual(_errors([scene]), [])

    def test_pexels_video_on_kenburns_is_renderable(self) -> None:
        self.assertEqual(_errors([_scene(videoUrl="https://videos.pexels.com/a.mp4")]), [])

    def test_kenburns_without_any_media_is_still_blocked(self) -> None:
        self.assertEqual(_errors([_scene()]), ["missing-image"])

    def test_five_second_cap_still_blocks_on_kenburns(self) -> None:
        scene = _scene(videoUrl="/clip.mp4", mediaProvider="youtube", mediaClipDurationSeconds=5.2)
        self.assertEqual(_errors([scene]), ["third-party-clip-over-limit"])


class ManifestDrivenRuleTests(unittest.TestCase):
    def test_structured_templates_need_their_data(self) -> None:
        self.assertEqual(
            _errors([_scene(templateName="timeline-graphic")]), ["missing-structured-data"]
        )
        ok = _scene(templateName="timeline-graphic", timelinePoints=[{"label": "2008", "position": 0}])
        self.assertEqual(_errors([ok]), [])

    def test_numeric_and_duration_rules(self) -> None:
        self.assertEqual(
            _errors([_scene(templateName="stat-overlay", sceneType="stat", text="Sin cifra")]),
            ["numeric-template-without-number"],
        )
        self.assertEqual(
            _errors([_scene(templateName="whip-transition", sceneType="transition", durationInFrames=11)], 11 / 30),
            ["long-whip"],
        )
        self.assertEqual(_errors([_scene(templateName="placeholder", imageUrl="/a.png")]), ["unknown-template"])

    def test_blocking_message_lists_each_scene_on_its_own_line(self) -> None:
        issues = validate_scene_plan([_scene(), _scene(templateName="nope", imageUrl="/a.png")], 10.0)  # type: ignore[arg-type]
        with self.assertRaises(PipelineQualityError) as raised:
            enforce_qa(issues)
        message = str(raised.exception)
        self.assertIn("2 error(es)", message)
        self.assertIn("escena 1: [QA:missing-image]", message)
        self.assertIn("escena 2: [QA:unknown-template]", message)
        self.assertEqual(len(message.splitlines()), 3)


class ManifestTests(unittest.TestCase):
    def test_registry_and_manifest_declare_the_same_templates(self) -> None:
        registry = (PROJECT_ROOT / "templates" / "registry.ts").read_text(encoding="utf-8")
        body = registry[registry.index("export const templates") :]
        body = body[body.index("{") + 1 : body.index("};")]
        keys = {
            match.group(1) or match.group(2)
            for match in re.finditer(r"^\s*(?:'([^']+)'|([A-Za-z_]\w*))\s*:", body, flags=re.MULTILINE)
        }
        self.assertEqual(keys, set(load_manifest().templates))

    def test_every_registered_component_file_exists(self) -> None:
        registry = (PROJECT_ROOT / "templates" / "registry.ts").read_text(encoding="utf-8")
        for name in re.findall(r"from './components/(\w+)'", registry):
            self.assertTrue((PROJECT_ROOT / "templates" / "components" / f"{name}.tsx").is_file(), name)

    def test_python_views_match_previous_hardcoded_sets(self) -> None:
        self.assertEqual(len(VALID_TEMPLATE_NAMES), 12)
        self.assertEqual(VALID_TEMPLATES_BY_TYPE["hook"], {"kinetic-text-hook", "title-card"})
        self.assertEqual(VALID_TEMPLATES_BY_TYPE["transition"], {"title-card", "whip-transition"})
        self.assertEqual(DEFAULT_TEMPLATE_BY_TYPE["narrative"], "kenburns-image")
        self.assertEqual(DEFAULT_TEMPLATE_BY_TYPE["stat"], "number-callout")

    def test_invalid_manifest_is_rejected_with_a_reason(self) -> None:
        with self.assertRaisesRegex(TemplateManifestError, "media"):
            parse_manifest({"templates": {"x": {"media": "hologram"}}})
        with self.assertRaisesRegex(TemplateManifestError, "no existe"):
            parse_manifest({"templates": {}, "defaultTemplateBySceneType": {"hook": "missing"}})


if __name__ == "__main__":
    unittest.main()
