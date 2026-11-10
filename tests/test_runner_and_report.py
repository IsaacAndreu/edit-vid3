from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import runner
from pipeline.qa import PipelineQualityError
from pipeline.report import write_report
from pipeline.runner import RunRequest, render_only, resolve_render_target, run_pipeline

from tests.helpers import make_settings


TRANSCRIPT = {
    "text": "uno dos",
    "duration_seconds": 8.0,
    "words": [{"word": "uno", "start": 0.0, "end": 3.9}, {"word": "dos", "start": 4.0, "end": 7.9}],
    "segments": [],
}


def planned_scenes() -> list[dict]:
    return [
        {"text": "¿Cuánto gana <la casa>?", "sceneType": "hook", "templateName": "kinetic-text-hook",
         "durationInFrames": 120, "keywords": ["casino"], "visualIntent": "casino floor"},
        {"text": "La ruleta", "sceneType": "narrative", "templateName": "kenburns-image",
         "durationInFrames": 120, "keywords": ["roulette"], "visualIntent": "roulette wheel"},
    ]


def with_media(scenes: list[dict], *, clip_seconds: float = 4.5) -> list[dict]:
    first, second = (dict(scene) for scene in scenes)
    first.update(videoUrl="https://videos.pexels.com/a.mp4", mediaProvider="pexels", mediaSourceUrl="https://www.pexels.com/video/a/",
                 mediaPhotographer="Ana", videoDurationInSeconds=12.0)
    second.update(
        videoUrl="/pipeline-assets/video/third-party/clips/youtube_x.mp4", videoDurationInSeconds=clip_seconds,
        mediaProvider="youtube", mediaSourceUrl="https://www.youtube.com/watch?v=aaaaaaaaaaa", mediaSourceTitle="Roulette <b>doc</b>",
        mediaUploader="Canal", mediaStartSeconds=61.0, mediaEndSeconds=61.0 + clip_seconds, mediaClipDurationSeconds=clip_seconds,
        mediaSelectionScore=0.6, mediaVisualScore=0.83, mediaSelectionReason="wheel visible", mediaTranscriptExcerpt="the wheel",
        mediaVideoId="aaaaaaaaaaa", mediaContactSheet="/pipeline-assets/video/third-party/contact-sheets/candidate-01-youtube_x.jpg",
        mediaSelectionTrace=[{"outcome": "selected", "queries": ["roulette wheel"], "totalSeconds": 71.2, "finalists": [
            {"videoId": "aaaaaaaaaaa", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "title": "Roulette doc", "uploader": "Canal",
             "startSeconds": 61.0, "endSeconds": 65.5, "relevanceScore": 0.6, "visualScore": 0.83, "reason": "wheel visible",
             "selected": True, "contactSheet": "/pipeline-assets/video/third-party/contact-sheets/candidate-01-youtube_x.jpg"},
            {"videoId": "bbbbbbbbbbb", "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "title": "Slots", "uploader": "Otro",
             "startSeconds": 5.0, "endSeconds": 9.0, "relevanceScore": 0.4, "visualScore": 0.31, "reason": "slot machines, no wheel"}]}],
    )
    return [first, second]


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.script = self.root / "guion.txt"
        self.script.write_text("uno dos", encoding="utf-8")
        self.audio = self.root / "voz.mp3"
        self.audio.write_bytes(b"audio")
        self.output = self.root / "out" / "video.mp4"
        self.settings = make_settings(self.root)
        self.order: list[str] = []

    def _patches(self, *, media: list[dict] | None = None, postflight_issues: list[dict] | None = None):
        def fake(name: str, result: object = None):
            def call(*_args: object, **_kwargs: object) -> object:
                self.order.append(name)
                return result
            return call

        def fake_render(_props: Path, output: Path, *_args: object, **_kwargs: object) -> None:
            self.order.append("render")
            output.write_bytes(b"mp4")

        return [
            patch.object(runner, "load_settings", return_value=self.settings),
            patch.object(runner, "transcribe_audio", side_effect=fake("transcribe", TRANSCRIPT)),
            patch.object(runner, "segment_script", side_effect=fake("segment", planned_scenes())),
            patch.object(runner, "fetch_media", side_effect=fake("media", media if media is not None else with_media(planned_scenes()))),
            patch.object(runner, "render_remotion", side_effect=fake_render),
            patch.object(runner, "master_audio", side_effect=fake("master")),
            patch.object(runner, "inspect_render", side_effect=fake("postflight", postflight_issues or [])),
            patch.object(runner, "configure_log"),
            patch("pipeline.runner.METRICS.reset", wraps=runner.METRICS.reset),
        ]

    def _run(self, request: RunRequest, **kwargs: object) -> Path:
        patches = self._patches(**kwargs)  # type: ignore[arg-type]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return run_pipeline(request)

    def _request(self, **extra: object) -> RunRequest:
        return RunRequest(self.script, self.audio, self.output, skip_preflight=True, **extra)  # type: ignore[arg-type]

    def test_full_run_writes_every_sidecar_in_order(self) -> None:
        result = self._run(self._request())

        self.assertEqual(result, self.output.resolve())
        self.assertEqual(self.order, ["transcribe", "segment", "media", "render", "master", "postflight"])
        for kind in ("props.json", "qa.json", "timeline.json", "postflight.json", "timing.json", "report.html"):
            self.assertTrue(self.output.with_suffix(f".{kind}").is_file(), kind)
        timing = json.loads(self.output.with_suffix(".timing.json").read_text(encoding="utf-8"))
        self.assertEqual(timing["status"], "ok")
        self.assertEqual(
            [step["name"] for step in timing["steps"]],
            ["transcribe", "segment", "media", "qa", "props", "render", "audio_master", "postflight"],
        )
        props = json.loads(self.output.with_suffix(".props.json").read_text(encoding="utf-8"))
        self.assertEqual(props["audioUrl"], "/pipeline-assets/video/audio/voice.mp3")
        self.assertNotIn("mediaSelectionTrace", props["scenes"][1])
        timeline = json.loads(self.output.with_suffix(".timeline.json").read_text(encoding="utf-8"))
        self.assertEqual(timeline["scenes"][1]["mediaContactSheet"].rsplit("/", 1)[1], "candidate-01-youtube_x.jpg")
        self.assertEqual(len(timeline["scenes"][1]["mediaSelectionTrace"][0]["finalists"]), 2)

    def test_skip_render_stops_after_props(self) -> None:
        result = self._run(self._request(skip_render=True, skip_audio_master=True))
        self.assertEqual(result.name, "video.props.json")
        self.assertEqual(self.order, ["transcribe", "segment", "media"])

    def test_blocked_qa_leaves_report_but_no_props(self) -> None:
        with self.assertRaises(PipelineQualityError) as raised:
            self._run(self._request(), media=with_media(planned_scenes(), clip_seconds=6.0))
        self.assertIn("third-party-clip-over-limit", str(raised.exception))
        self.assertNotIn("render", self.order)
        self.assertFalse(self.output.with_suffix(".props.json").exists())
        self.assertTrue(self.output.with_suffix(".report.html").is_file())
        timing = json.loads(self.output.with_suffix(".timing.json").read_text(encoding="utf-8"))
        self.assertEqual(timing["status"], "error")

    def test_overrides_reach_the_media_stage(self) -> None:
        overrides = self.root / "overrides.json"
        overrides.write_text('{"scenes": {"2": {"keywords": ["roulette wheel close-up"]}}}', encoding="utf-8")
        patches = self._patches()
        mocks = [item.start() for item in patches]
        for item in patches:
            self.addCleanup(item.stop)
        run_pipeline(self._request(skip_render=True, overrides_path=overrides, fresh=True, redo_scenes=frozenset({2})))

        fetch_call = mocks[3].call_args
        self.assertEqual(fetch_call.args[0][1]["keywords"], ["roulette wheel close-up"])
        options = fetch_call.kwargs["options"]
        self.assertFalse(options.resume)
        self.assertEqual(options.redo_scenes, frozenset({2}))
        self.assertEqual(options.checkpoint_path, self.output.resolve().with_suffix(".media.json"))


class RenderOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.output = self.root / "video.mp4"
        self.settings = make_settings(self.root)

    def _write_props(self, scenes: list[dict]) -> None:
        self.output.with_suffix(".props.json").write_text(json.dumps({"scenes": scenes}), encoding="utf-8")

    def test_accepts_mp4_or_props_path(self) -> None:
        props = self.output.with_suffix(".props.json")
        self.assertEqual(resolve_render_target(self.output), (self.output.resolve(), props.resolve()))
        self.assertEqual(resolve_render_target(props), (self.output.resolve(), props.resolve()))

    def test_renders_masters_and_verifies_with_duration_from_props(self) -> None:
        self._write_props(with_media(planned_scenes()))
        seen: dict[str, object] = {}

        def fake_render(props: Path, output: Path, *_a: object, **kwargs: object) -> None:
            seen["concurrency"] = kwargs.get("concurrency")
            output.write_bytes(b"mp4")

        def fake_inspect(_output: Path, expected: float) -> list:
            seen["expected"] = expected
            return []

        with (
            patch.object(runner, "load_settings", return_value=self.settings),
            patch.object(runner, "render_remotion", side_effect=fake_render),
            patch.object(runner, "master_audio") as master,
            patch.object(runner, "inspect_render", side_effect=fake_inspect),
            patch.object(runner, "configure_log"),
        ):
            render_only(self.output, render_concurrency="75%", skip_preflight=True)

        self.assertEqual(seen, {"concurrency": "75%", "expected": 8.0})
        master.assert_called_once()
        self.assertTrue(self.output.with_suffix(".postflight.json").is_file())

    def test_hand_edited_props_still_pass_the_five_second_gate(self) -> None:
        self._write_props(with_media(planned_scenes(), clip_seconds=7.0))
        with (
            patch.object(runner, "load_settings", return_value=self.settings),
            patch.object(runner, "render_remotion") as render,
            patch.object(runner, "configure_log"),
        ):
            with self.assertRaisesRegex(PipelineQualityError, "third-party-clip-over-limit"):
                render_only(self.output, skip_preflight=True)
        render.assert_not_called()

    def test_missing_props_tells_how_to_create_them(self) -> None:
        with patch.object(runner, "configure_log"), self.assertRaisesRegex(FileNotFoundError, "python main.py"):
            render_only(self.output, skip_preflight=True)


class RenderCommandTests(unittest.TestCase):
    def test_concurrency_and_browser_are_optional_flags(self) -> None:
        from pipeline.render import render_command

        with patch.dict("os.environ", {"REMOTION_BROWSER_EXECUTABLE": ""}):
            plain = render_command(Path("v.props.json"), Path("v.mp4"))
            tuned = render_command(Path("v.props.json"), Path("v.mp4"), concurrency="75%")
        self.assertEqual(plain[1:5], ["remotion", "render", "src/index.ts", "YoutubeVideo"])
        self.assertNotIn("--concurrency", plain)
        self.assertNotIn("--browser-executable", plain)
        self.assertEqual(tuned[tuned.index("--concurrency") + 1], "75%")

        with patch.dict("os.environ", {"REMOTION_BROWSER_EXECUTABLE": "/opt/chrome"}):
            custom = render_command(Path("v.props.json"), Path("v.mp4"))
        self.assertEqual(custom[custom.index("--browser-executable") + 1], "/opt/chrome")

    def test_render_failure_says_how_to_retry_only_the_render(self) -> None:
        import subprocess

        from pipeline.render import RenderError, render_remotion

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            with patch(
                "pipeline.render.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["npx"])
            ):
                with self.assertRaisesRegex(RenderError, "python main.py render"):
                    render_remotion(Path("v.props.json"), Path("v.mp4"), settings)
            with patch("pipeline.render.subprocess.run", side_effect=FileNotFoundError("npx")):
                with self.assertRaisesRegex(RenderError, "npm install"):
                    render_remotion(Path("v.props.json"), Path("v.mp4"), settings)


class ReportTests(unittest.TestCase):
    def test_report_is_built_from_sidecars_and_escapes_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "out" / "video.mp4"
            output.parent.mkdir()
            self.assertIsNone(write_report(output, project_root=root))

            from pipeline.analytics import write_timeline_manifest

            write_timeline_manifest(with_media(planned_scenes()), output.with_suffix(".timeline.json"))  # type: ignore[arg-type]
            output.with_suffix(".qa.json").write_text(json.dumps({"status": "ok", "issues": [
                {"level": "warning", "code": "short-third-party-video", "message": "se quedará en el último fotograma", "scene_index": 2}]}),
                encoding="utf-8")
            output.with_suffix(".timing.json").write_text(json.dumps({"totalSeconds": 4000, "steps": [
                {"name": "media", "seconds": 3600, "status": "ok"}, {"name": "transcribe", "seconds": 1, "status": "ok", "cached": True}],
                "counters": {"youtube.search.calls": 9}, "scenes": [{"index": 2, "thirdPartySeconds": 71.2}]}), encoding="utf-8")

            report = write_report(output, project_root=root)
            assert report is not None
            html_text = report.read_text(encoding="utf-8")

        self.assertEqual(report.name, "video.report.html")
        self.assertIn("&lt;la casa&gt;", html_text)
        self.assertNotIn("<la casa>", html_text)
        self.assertIn("Roulette &lt;b&gt;doc&lt;/b&gt;", html_text)
        self.assertIn("../public/pipeline-assets/video/third-party/contact-sheets/candidate-01-youtube_x.jpg", html_text)
        self.assertIn("../public/pipeline-assets/video/third-party/clips/youtube_x.mp4", html_text)
        self.assertIn("1:01.0 – 1:05.5", html_text)
        self.assertIn("slot machines, no wheel", html_text)
        self.assertIn("short-third-party-video", html_text)
        self.assertIn("Material visual", html_text)
        self.assertIn("60 min 00 s", html_text)
        self.assertIn("66 min 40 s", html_text)
        self.assertIn("youtube.search.calls", html_text)
        self.assertIn('data-f="p-youtube"', html_text)
        self.assertIn("sin render todavía", html_text)


if __name__ == "__main__":
    unittest.main()
