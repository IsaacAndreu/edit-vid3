from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

from pipeline.clients.openai_images import OpenAIImageClient
from pipeline.clients.pexels_client import (
    PexelsClient,
    PexelsError,
    PexelsRateLimitError,
    pick_video_file,
)


def video_file(width: int, height: int | None = None, link: str | None = None) -> dict:
    return {"width": width, "height": height or width * 9 // 16, "link": link or f"https://v/{width}.mp4"}


class PickVideoFileTests(unittest.TestCase):
    def test_prefers_smallest_file_that_covers_full_hd(self) -> None:
        files = [video_file(3840), video_file(1280), video_file(1920), video_file(2560)]
        self.assertEqual(pick_video_file(files, set())["width"], 1920)

    def test_falls_back_to_widest_when_nothing_reaches_full_hd(self) -> None:
        files = [video_file(960), video_file(1280), video_file(640)]
        self.assertEqual(pick_video_file(files, set())["width"], 1280)

    def test_skips_excluded_and_portrait_files(self) -> None:
        files = [video_file(1920), video_file(2560), video_file(1080, 1920, "https://v/portrait.mp4")]
        self.assertEqual(pick_video_file(files, {"https://v/1920.mp4"})["width"], 2560)
        self.assertIsNone(pick_video_file([video_file(1920)], {"https://v/1920.mp4"}))


def response(status: int, payload: dict | None = None, headers: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, json=lambda: payload or {}, headers=headers or {})


class PexelsRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("pipeline.clients.pexels_client.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = PexelsClient("key", min_interval_seconds=0)

    def test_network_errors_are_retried_then_reported(self) -> None:
        with patch.object(self.client._session, "get", side_effect=requests.Timeout("slow")) as get:
            with self.assertRaisesRegex(PexelsError, "no respondió"):
                self.client.search_image_candidates("casino")
        self.assertEqual(get.call_count, 3)

    def test_transient_error_recovers_and_result_is_cached(self) -> None:
        payload = {"photos": [{"src": {"large2x": "https://i/1.jpg"}, "url": "https://p/1", "alt": "casino"}]}
        with patch.object(
            self.client._session, "get", side_effect=[requests.ConnectionError("x"), response(200, payload)]
        ) as get:
            first = self.client.search_image_candidates("casino")
            second = self.client.search_image_candidates("casino")
        self.assertEqual(get.call_count, 2)
        self.assertEqual(first, second)
        self.assertEqual(first[0].url, "https://i/1.jpg")

    def test_rejected_key_names_the_setting(self) -> None:
        with patch.object(self.client._session, "get", return_value=response(401)):
            with self.assertRaisesRegex(PexelsError, "PEXELS_API_KEY"):
                self.client.search_video_candidates("casino")

    def test_rate_limit_keeps_its_own_error(self) -> None:
        with patch.object(self.client._session, "get", return_value=response(429)):
            with self.assertRaises(PexelsRateLimitError):
                self.client.search_video_candidates("casino")

    def test_video_search_selects_full_hd_file_and_thumbnail(self) -> None:
        payload = {
            "videos": [
                {
                    "url": "https://www.pexels.com/video/casino-1/",
                    "duration": 14,
                    "image": "https://images.pexels.com/thumb.jpg",
                    "user": {"name": "Ana"},
                    "video_files": [video_file(3840), video_file(1920), video_file(1280)],
                }
            ]
        }
        with patch.object(self.client._session, "get", return_value=response(200, payload)):
            assets = self.client.search_video_candidates("casino")
        self.assertEqual(assets[0].width, 1920)
        self.assertEqual(assets[0].thumbnail_url, "https://images.pexels.com/thumb.jpg")


class PexelsDownloadTests(unittest.TestCase):
    def test_download_is_stored_once(self) -> None:
        client = PexelsClient("key")

        class Stream:
            status_code = 200

            def __enter__(self) -> "Stream":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def iter_content(self, chunk_size: int) -> list[bytes]:
                return [b"abc", b"def"]

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pipeline.clients.pexels_client.requests.get", return_value=Stream()) as get:
                first = client.download_asset("https://videos.pexels.com/a/b.mp4", Path(temp_dir))
                second = client.download_asset("https://videos.pexels.com/a/b.mp4", Path(temp_dir))
            self.assertEqual(first, second)
            self.assertEqual(first.read_bytes(), b"abcdef")
            self.assertEqual(first.suffix, ".mp4")
            self.assertEqual(get.call_count, 1)
            self.assertNotIn("Authorization", get.call_args.kwargs.get("headers", {}))
            self.assertEqual([path.name for path in Path(temp_dir).iterdir()], [first.name])

    def test_plain_http_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(PexelsError):
                PexelsClient("key").download_asset("http://videos.pexels.com/a.mp4", Path(temp_dir))


class GeneratedImageCacheTests(unittest.TestCase):
    def _client(self) -> tuple[OpenAIImageClient, list[dict]]:
        calls: list[dict] = []

        def generate(**kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(b64_json="aGVsbG8=", url=None)])

        client = OpenAIImageClient.__new__(OpenAIImageClient)
        client._client = SimpleNamespace(images=SimpleNamespace(generate=generate))  # type: ignore[attr-defined]
        client._model = "gpt-image-2"  # type: ignore[attr-defined]
        return client, calls

    def test_same_prompt_and_quality_is_paid_once(self) -> None:
        client, calls = self._client()
        with tempfile.TemporaryDirectory() as temp_dir:
            first = client.generate_image("a casino", Path(temp_dir), quality="medium")
            second = client.generate_image("a casino", Path(temp_dir), quality="medium")
            other = client.generate_image("a casino", Path(temp_dir), quality="high")
            self.assertEqual(first, second)
            self.assertNotEqual(first, other)
            self.assertEqual(first.read_bytes(), b"hello")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["model"], "gpt-image-2")


if __name__ == "__main__":
    unittest.main()
