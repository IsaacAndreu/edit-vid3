from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from pipeline.cache import JsonCache, atomic_write_json, read_json, sha256_text
from pipeline.clients import deepseek_client
from pipeline.segment import segment_script
from pipeline.timing import Metrics
from pipeline import transcribe

from tests.helpers import make_settings


WORDS = [
    {"word": "Inicio", "start": 0.0, "end": 0.4},
    {"word": "dato", "start": 0.5, "end": 0.9},
    {"word": "cierre", "start": 1.0, "end": 1.9},
]
TRANSCRIPT = {"text": "Inicio dato cierre", "duration_seconds": 2.0, "words": WORDS, "segments": []}
RAW_SCENES = [
    {"start_word_index": 0, "end_word_index": 0, "sceneType": "hook", "text": "Inicio"},
    {"start_word_index": 1, "end_word_index": 2, "sceneType": "narrative", "text": "Dato cierre", "keywords": ["casino"]},
]


class JsonCacheTests(unittest.TestCase):
    def test_round_trip_and_disabled_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = JsonCache(Path(temp_dir))
            self.assertIsNone(cache.get("ns", "key"))
            cache.put("ns", "key", {"a": 1})
            self.assertEqual(cache.get("ns", "key"), {"a": 1})

            fresh = JsonCache(Path(temp_dir), enabled=False)
            self.assertIsNone(fresh.get("ns", "key"))
            fresh.put("ns", "key", {"a": 2})  # --fresh still refreshes the stored entry
            self.assertEqual(cache.get("ns", "key"), {"a": 2})

    def test_corrupt_file_reads_as_missing_and_writes_are_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "x.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(read_json(path))
            atomic_write_json(path, {"ok": True})
            self.assertEqual(read_json(path), {"ok": True})
            self.assertEqual([item.name for item in Path(temp_dir).iterdir()], ["x.json"])

    def test_hash_separates_parts(self) -> None:
        self.assertNotEqual(sha256_text("ab", "c"), sha256_text("a", "bc"))


class MetricsTests(unittest.TestCase):
    def test_steps_counters_and_scenes_are_flushed_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "video.timing.json"
            metrics = Metrics()
            metrics.reset(path, output="video.mp4")
            with metrics.step("media") as step:
                step["scenes"] = 3
                metrics.count("youtube.searches", 2)
                with metrics.timed("youtube.search"):
                    pass
                metrics.scene(2, provider="youtube")
            with self.assertRaises(RuntimeError):
                with metrics.step("render"):
                    raise RuntimeError("boom")
            metrics.finish("error")

            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "error")
        self.assertEqual([step["name"] for step in data["steps"]], ["media", "render"])
        self.assertEqual(data["steps"][0]["status"], "ok")
        self.assertEqual(data["steps"][0]["scenes"], 3)
        self.assertEqual(data["steps"][1]["status"], "error")
        self.assertGreaterEqual(data["steps"][0]["seconds"], 0)
        self.assertEqual(data["counters"]["youtube.searches"], 2)
        self.assertEqual(data["counters"]["youtube.search.calls"], 1)
        self.assertEqual(data["scenes"], [{"index": 2, "provider": "youtube"}])
        self.assertEqual(data["output"], "video.mp4")


class SegmentationPromptTests(unittest.TestCase):
    def test_prompt_template_list_comes_from_manifest(self) -> None:
        line = next(line for line in deepseek_client.SEGMENTATION_SYSTEM_PROMPT.splitlines() if '"templateName"' in line)
        self.assertEqual(
            line.strip(),
            '"templateName": "kinetic-text-hook | kenburns-image | lower-third | multi-shot-montage | '
            "news-image-montage | number-callout | stat-overlay | blueprint-data-panel | timeline-graphic | "
            'comparison-panel | title-card | whip-transition",',
        )
        self.assertNotIn("__TEMPLATE_NAMES__", deepseek_client.SEGMENTATION_SYSTEM_PROMPT)
        self.assertNotIn("placeholder", line)

    def test_compact_words_keep_index_word_and_start(self) -> None:
        prompt = deepseek_client.build_segmentation_user_prompt("Guion", WORDS, words_format="compact")
        payload = json.loads(prompt.rsplit("\n", 1)[1])
        self.assertEqual(payload, [[0, "Inicio", 0.0], [1, "dato", 0.5], [2, "cierre", 1.0]])
        self.assertIn("termina en el segundo 1.90", prompt)

        full = deepseek_client.build_segmentation_user_prompt("Guion", WORDS, words_format="full")
        self.assertEqual(json.loads(full.rsplit("\n", 1)[1])[2], {"index": 2, "word": "cierre", "start": 1.0, "end": 1.9})
        self.assertLess(len(prompt), len(full))

    def test_fingerprint_depends_on_model_and_format(self) -> None:
        base = make_settings(Path("."))
        self.assertNotEqual(
            deepseek_client.segmentation_cache_fingerprint(base),
            deepseek_client.segmentation_cache_fingerprint(make_settings(Path("."), segment_words_format="full")),
        )
        self.assertNotEqual(
            deepseek_client.segmentation_cache_fingerprint(base),
            deepseek_client.segmentation_cache_fingerprint(make_settings(Path("."), llm_model="other")),
        )


class SegmentationCacheTests(unittest.TestCase):
    def test_identical_inputs_call_the_model_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = JsonCache(Path(temp_dir))
            settings = make_settings(Path(temp_dir))
            with patch("pipeline.segment.segment_with_deepseek", return_value=RAW_SCENES) as llm:
                first = segment_script("Guion", TRANSCRIPT, settings, cache=cache)  # type: ignore[arg-type]
                second = segment_script("Guion", TRANSCRIPT, settings, cache=cache)  # type: ignore[arg-type]
                segment_script("Guion cambiado", TRANSCRIPT, settings, cache=cache)  # type: ignore[arg-type]
            self.assertEqual(first, second)
            self.assertEqual(llm.call_count, 2)
            self.assertEqual(sum(scene["durationInFrames"] for scene in first), 60)


class TranscriptionTests(unittest.TestCase):
    def _fake_openai(self, calls: list[str]):
        """Patch that swaps in a stand-in ``openai`` module, so the SDK need not be installed."""

        class FakeOpenAI:
            def __init__(self, api_key: str) -> None:
                self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

            def _create(self, *, file: object, **kwargs: object) -> dict:
                calls.append(getattr(file, "name", ""))
                return {"text": "Inicio dato cierre", "duration": 2.0, "words": WORDS, "segments": []}

        module = ModuleType("openai")
        module.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
        return patch.dict(sys.modules, {"openai": module})

    def test_same_audio_is_transcribed_once(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "voz.mp3"
            audio.write_bytes(b"audio-bytes")
            cache = JsonCache(Path(temp_dir) / "cache")
            settings = make_settings(Path(temp_dir))
            with self._fake_openai(calls), patch.object(
                transcribe, "_probe_duration_seconds", return_value=2.5
            ):
                first = transcribe.transcribe_audio(audio, settings, cache=cache)
                second = transcribe.transcribe_audio(audio, settings, cache=cache)
                audio.write_bytes(b"other-audio")
                transcribe.transcribe_audio(audio, settings, cache=cache)
        self.assertEqual(first, second)
        self.assertEqual(first["duration_seconds"], 2.5)
        self.assertEqual(len(calls), 2)

    def test_oversized_audio_is_compressed_before_upload(self) -> None:
        calls: list[str] = []
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
            commands.append(command)
            Path(command[-1]).write_bytes(b"small")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "voz.wav"
            audio.write_bytes(b"x" * 2048)
            with (
                patch.object(transcribe, "_UPLOAD_COMFORT_BYTES", 1024),
                self._fake_openai(calls),
                patch("pipeline.transcribe.shutil.which", return_value="/usr/bin/ffmpeg"),
                patch("pipeline.transcribe.subprocess.run", side_effect=fake_run),
                patch.object(transcribe, "_probe_duration_seconds", return_value=2.0),
            ):
                transcribe.transcribe_audio(audio, make_settings(Path(temp_dir)))
        self.assertEqual(len(commands), 1)
        self.assertIn("-ac", commands[0])
        self.assertTrue(calls[0].endswith("upload.mp3"))

    def test_oversized_audio_without_ffmpeg_explains_the_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "voz.wav"
            audio.write_bytes(b"x" * 2048)
            with (
                patch.object(transcribe, "_UPLOAD_COMFORT_BYTES", 1024),
                self._fake_openai([]),
                patch("pipeline.transcribe.shutil.which", return_value=None),
            ):
                with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                    transcribe.transcribe_audio(audio, make_settings(Path(temp_dir)))


if __name__ == "__main__":
    unittest.main()
