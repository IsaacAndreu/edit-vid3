from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.clients.youtube_client import SubtitleCue, YouTubeCandidate, YouTubeClient, YouTubeClientError


VIDEO_ID = "dQw4w9WgXcQ"
OTHER_ID = "abcdefghijk"


class SinglePassYoutubeDL:
    """Mimics yt-dlp writing captions while it extracts a search (skip_download)."""

    instances: list["SinglePassYoutubeDL"] = []

    def __init__(self, options: dict, entries: list[dict], *, captions: dict[str, str] | None = None) -> None:
        self.options = options
        self.entries = entries
        self.captions = captions or {}
        self.extract_calls: list[tuple[str, bool]] = []
        self.download_calls: list[list[str]] = []
        SinglePassYoutubeDL.instances.append(self)

    def extract_info(self, url: str, *, download: bool) -> dict:
        self.extract_calls.append((url, download))
        if download:
            assert self.options["skip_download"] is True, "a search must never download media"
            directory = Path(str(self.options["outtmpl"])).parent
            for name, text in self.captions.items():
                (directory / name).write_text(text, encoding="utf-8")
        return {"entries": self.entries}

    def download(self, urls: list[str]) -> int:
        self.download_calls.append(urls)
        return 0


def entry(video_id: str = VIDEO_ID) -> dict:
    return {"id": video_id, "title": "Valid", "duration": 120, "uploader": "Channel"}


VTT = "WEBVTT\n\n00:00:01.000 --> 00:00:02.250\nHola mundo\n"


class SinglePassSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        SinglePassYoutubeDL.instances.clear()

    def test_metadata_and_captions_come_from_one_extraction(self) -> None:
        client = YouTubeClient()
        created: list[SinglePassYoutubeDL] = []

        def make(options: dict) -> SinglePassYoutubeDL:
            ydl = SinglePassYoutubeDL(options, [entry()], captions={f"{VIDEO_ID}.es.vtt": VTT})
            created.append(ydl)
            return ydl

        with patch.object(client, "_create_ydl", side_effect=make):
            results = client.search("casino roulette", limit=4)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].extract_calls, [("ytsearch4:casino roulette", True)])
        self.assertEqual(created[0].download_calls, [])
        self.assertTrue(created[0].options["skip_download"])
        self.assertTrue(created[0].options["ignoreerrors"])
        self.assertEqual(created[0].options["subtitleslangs"], ["es", "es-419", "en", "en-US"])
        self.assertIsNone(created[0].options["cookiefile"])
        self.assertEqual(results[0].subtitles, (SubtitleCue(1.0, 2.25, "Hola mundo"),))

    def test_repeated_query_is_served_from_cache(self) -> None:
        client = YouTubeClient()
        with patch.object(
            client, "_create_ydl", side_effect=lambda options: SinglePassYoutubeDL(options, [entry()])
        ) as create:
            first = client.search("Casino Roulette", limit=4)
            second = client.search("casino roulette", limit=4)
            client.search("casino roulette", limit=2)

        self.assertEqual(first, second)
        self.assertEqual(create.call_count, 2)  # one per distinct (query, limit)

    def test_failed_search_reports_cause_and_is_not_cached(self) -> None:
        client = YouTubeClient()

        class Blocked:
            def __init__(self, options: dict) -> None:
                self.options = options

            def extract_info(self, _url: str, *, download: bool) -> None:
                self.options["logger"].error("ERROR: [youtube] Sign in to confirm you're not a bot")
                return None

        with patch.object(client, "_create_ydl", side_effect=lambda options: Blocked(options)) as create:
            with self.assertRaisesRegex(YouTubeClientError, "not a bot"):
                client.search("casino", limit=4)
            with self.assertRaises(YouTubeClientError):
                client.search("casino", limit=4)
        self.assertEqual(create.call_count, 2)

    def test_exception_message_keeps_the_original_reason(self) -> None:
        client = YouTubeClient()

        class Exploding:
            def extract_info(self, _url: str, *, download: bool) -> None:
                raise RuntimeError("HTTP Error 429: Too Many Requests")

        with patch.object(client, "_create_ydl", return_value=Exploding()):
            with self.assertRaisesRegex(YouTubeClientError, "429"):
                client.search("casino", limit=4)

    def test_caption_found_later_is_used_for_cached_video(self) -> None:
        client = YouTubeClient()
        batches = [{}, {f"{VIDEO_ID}.en.vtt": VTT}]

        def make(options: dict) -> SinglePassYoutubeDL:
            return SinglePassYoutubeDL(options, [entry()], captions=batches.pop(0))

        with patch.object(client, "_create_ydl", side_effect=make):
            first = client.search("query one", limit=1)
            second = client.search("query two", limit=1)
        self.assertEqual(first[0].subtitles, ())
        self.assertEqual(len(second[0].subtitles), 1)


class IdempotentDownloadTests(unittest.TestCase):
    def test_prepared_clip_is_reused_and_cap_is_rechecked(self) -> None:
        client = YouTubeClient()
        candidate = YouTubeCandidate(
            video_id=VIDEO_ID,
            url=f"https://www.youtube.com/watch?v={VIDEO_ID}",
            title="Example",
            uploader="Uploader",
            description="",
            duration_seconds=120.0,
            view_count=1,
            thumbnail_url=None,
            query="example",
        )

        class Downloader:
            def __init__(self, options: dict) -> None:
                self.options = options

            def download(self, _urls: list[str]) -> int:
                Path(str(self.options["outtmpl"]).replace("%(ext)s", "mp4")).write_bytes(b"source")
                return 0

        probed: list[str] = []

        def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
            if command[0] == "ffmpeg":
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")
            probed.append(command[-1])
            return subprocess.CompletedProcess(command, 0, '{"format":{"duration":"5.0"}}', "")

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(client, "_create_ydl", side_effect=lambda options: Downloader(options)) as create,
                patch.object(client, "_download_range_callback", return_value=object()),
                patch("pipeline.clients.youtube_client.subprocess.run", side_effect=run),
            ):
                first = client.download_clip(candidate, 12, 17, Path(temp_dir))
                second = client.download_clip(candidate, 12, 17, Path(temp_dir))

            self.assertEqual(first, second)
            self.assertEqual(create.call_count, 1)
            self.assertEqual(len(probed), 2)  # validated when created and again when reused
            self.assertTrue(first.with_suffix(".json").is_file())
            self.assertEqual(sorted(path.name for path in Path(temp_dir).iterdir()), sorted([first.name, first.with_suffix(".json").name]))


if __name__ == "__main__":
    unittest.main()
