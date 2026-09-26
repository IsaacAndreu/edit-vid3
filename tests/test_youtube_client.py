from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.clients.youtube_client import (
    SubtitleCue,
    YouTubeCandidate,
    YouTubeClient,
    YouTubeClientError,
)


VIDEO_ID = "dQw4w9WgXcQ"


def candidate(*, url: str = f"https://www.youtube.com/watch?v={VIDEO_ID}") -> YouTubeCandidate:
    return YouTubeCandidate(
        video_id=VIDEO_ID,
        url=url,
        title="Example",
        uploader="Uploader",
        description="Description",
        duration_seconds=120.0,
        view_count=12,
        thumbnail_url=None,
        query="example",
    )


class FakeYoutubeDL:
    def __init__(self, options: dict, entries: list[dict] | None = None) -> None:
        self.options = options
        self.entries = entries or []
        self.downloaded_urls: list[str] = []

    def extract_info(self, _url: str, *, download: bool) -> dict:
        if download:
            raise AssertionError("metadata lookup must not download media")
        return {"entries": self.entries}

    def download(self, urls: list[str]) -> int:
        self.downloaded_urls.extend(urls)
        template = str(self.options["outtmpl"])
        if "%(ext)s" in template:
            if "%(id)s" in template:
                template = template.replace("%(id)s", VIDEO_ID).replace("%(ext)s", "vtt")
                Path(template).write_text(
                    "WEBVTT\n\n00:00:01.000 --> 00:00:02.250\nHello &amp; welcome\n",
                    encoding="utf-8",
                )
            else:
                Path(template.replace("%(ext)s", "mp4")).write_bytes(b"mock source")
        return 0


class YouTubeClientTests(unittest.TestCase):
    def test_search_is_bounded_filters_bad_candidates_and_reads_metadata_and_subtitles(self) -> None:
        entries = [
            {"id": VIDEO_ID, "title": "Valid", "duration": 120, "uploader": "Channel", "view_count": 55},
            {"id": "abcdefghijk", "title": "Too short", "duration": 4},
            {"id": "abcdefghij2", "title": "Too long", "duration": 1801},
            {"id": "abcdefghij3", "title": "Live", "duration": 300, "is_live": True},
            {"id": "abcdefghij4", "title": "Upcoming", "duration": 300, "live_status": "is_upcoming"},
            {"id": "abcdefghij5", "title": "No duration"},
        ]
        search_ydl = FakeYoutubeDL({}, entries)
        subtitle_ydl = FakeYoutubeDL({"outtmpl": "%(id)s.%(ext)s"})
        client = YouTubeClient()
        created: list[FakeYoutubeDL] = []

        def make_ydl(options: dict) -> FakeYoutubeDL:
            if options.get("writesubtitles"):
                subtitle_ydl.options = options
                created.append(subtitle_ydl)
                return subtitle_ydl
            search_ydl.options = options
            created.append(search_ydl)
            return search_ydl

        with patch.object(client, "_create_ydl", side_effect=make_ydl):
            results = client.search("  ocean documentary  ", limit=5)

        self.assertEqual([item.video_id for item in results], [VIDEO_ID])
        self.assertEqual(results[0].query, "ocean documentary")
        self.assertEqual(results[0].uploader, "Channel")
        self.assertEqual(results[0].view_count, 55)
        self.assertEqual(results[0].subtitles, (SubtitleCue(1.0, 2.25, "Hello & welcome"),))
        self.assertEqual(search_ydl.options["socket_timeout"], 20)
        self.assertIsNone(search_ydl.options["cookiefile"])
        self.assertIsNone(search_ydl.options["cookiesfrombrowser"])
        self.assertEqual(subtitle_ydl.options["subtitleslangs"], ["es", "es-419", "en", "en-US"])
        self.assertTrue(subtitle_ydl.options["skip_download"])
        self.assertEqual(subtitle_ydl.downloaded_urls, [results[0].url])

    def test_search_rejects_unbounded_limit(self) -> None:
        client = YouTubeClient()
        with self.assertRaises(ValueError):
            client.search("query", limit=6)

    def test_search_caches_subtitles_for_repeated_video_results(self) -> None:
        client = YouTubeClient()
        entry = {
            "id": VIDEO_ID,
            "title": "Example",
            "duration": 120,
            "webpage_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        }
        search_ydl = FakeYoutubeDL({}, [entry])
        with patch.object(client, "_create_ydl", return_value=search_ydl), patch.object(
            client,
            "_retrieve_subtitles",
            return_value=(SubtitleCue(0.0, 1.0, "robot factory"),),
        ) as retrieve:
            first = client.search("robot factory", limit=1)
            second = client.search("factory robots", limit=1)

        self.assertEqual(first[0].subtitles, second[0].subtitles)
        retrieve.assert_called_once_with(first[0].url, VIDEO_ID)

    def test_retrieve_subtitles_prefers_spanish_track_to_english(self) -> None:
        client = YouTubeClient()

        class MultiLanguageYoutubeDL:
            def __init__(self, options: dict) -> None:
                self.options = options

            def download(self, _urls: list[str]) -> None:
                output_dir = Path(self.options["outtmpl"]).parent
                (output_dir / f"{VIDEO_ID}.en.vtt").write_text(
                    "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nEnglish caption\n",
                    encoding="utf-8",
                )
                (output_dir / f"{VIDEO_ID}.es.vtt").write_text(
                    "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nSubtítulo en español\n",
                    encoding="utf-8",
                )

        with patch.object(client, "_create_ydl", side_effect=lambda options: MultiLanguageYoutubeDL(options)):
            cues = client._retrieve_subtitles(f"https://www.youtube.com/watch?v={VIDEO_ID}", VIDEO_ID)

        self.assertEqual(cues, (SubtitleCue(1.0, 2.0, "Subtítulo en español"),))

    def test_vtt_and_json3_subtitle_parsers(self) -> None:
        vtt = """WEBVTT

00:00:01.100 --> 00:00:02.250 align:start
<c>Hello</c>
world &amp; friends

"""
        json3 = json.dumps(
            {"events": [{"tStartMs": 3250, "dDurationMs": 800, "segs": [{"utf8": "Hola "}, {"utf8": "mundo"}]}]}
        )
        self.assertEqual(
            YouTubeClient._parse_vtt(vtt),
            [SubtitleCue(1.1, 2.25, "Hello world & friends")],
        )
        self.assertEqual(
            YouTubeClient._parse_json3(json3),
            [SubtitleCue(3.25, 4.05, "Hola mundo")],
        )

    def test_download_clip_caps_requested_range_and_transcodes_without_audio(self) -> None:
        client = YouTubeClient()
        options_seen: list[dict] = []
        ydl = FakeYoutubeDL({})
        callback = object()
        process_calls: list[list[str]] = []

        def make_ydl(options: dict) -> FakeYoutubeDL:
            ydl.options = options
            options_seen.append(options)
            return ydl

        def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
            process_calls.append(command)
            if command[0] == "ffmpeg":
                Path(command[-1]).write_bytes(b"mock mp4")
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(command, 0, '{"format":{"duration":"5.0"}}', "")

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(client, "_create_ydl", side_effect=make_ydl),
                patch.object(client, "_download_range_callback", return_value=callback) as range_factory,
                patch("pipeline.clients.youtube_client.subprocess.run", side_effect=run),
            ):
                result = client.download_clip(
                    candidate(), 12, 30, Path(temp_dir), max_clip_seconds=9,
                )
                provenance = json.loads(result.with_suffix(".json").read_text(encoding="utf-8"))

        self.assertEqual(range_factory.call_args.args, (12, 17))
        self.assertFalse(options_seen[0]["skip_download"])
        self.assertIs(options_seen[0]["download_ranges"], callback)
        self.assertLessEqual(17 - 12, 5)
        self.assertTrue(result.name.startswith("youtube_"))
        self.assertEqual(result.suffix, ".mp4")
        self.assertEqual(provenance["url"], candidate().url)
        self.assertEqual(provenance["title"], "Example")
        self.assertEqual(provenance["uploader"], "Uploader")
        self.assertEqual(provenance["clip_range_seconds"], {"start": 12, "end": 17})
        ffmpeg = process_calls[0]
        self.assertEqual(ffmpeg[ffmpeg.index("-t") + 1], "5.000000")
        self.assertIn("-an", ffmpeg)
        self.assertIn("libx264", ffmpeg)
        self.assertIn("fps=30", ffmpeg[ffmpeg.index("-vf") + 1])
        self.assertNotIn("-cookies", ffmpeg)

    def test_download_rejects_non_youtube_domain_before_downloader_is_created(self) -> None:
        client = YouTubeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(client, "_create_ydl") as make_ydl:
                with self.assertRaisesRegex(YouTubeClientError, "Only public HTTPS"):
                    client.download_clip(
                        candidate(url="https://youtube.com.evil.example/watch?v=" + VIDEO_ID),
                        0,
                        5,
                        Path(temp_dir),
                    )
        make_ydl.assert_not_called()

    def test_download_rejects_insecure_and_non_youtube_hosts(self) -> None:
        client = YouTubeClient()
        for url in (
            f"http://youtube.com/watch?v={VIDEO_ID}",
            f"https://example.com/watch?v={VIDEO_ID}",
            f"https://user@youtu.be/{VIDEO_ID}",
        ):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as temp_dir:
                with self.assertRaises(YouTubeClientError):
                    client.download_clip(candidate(url=url), 0, 3, Path(temp_dir))

    def test_download_rejects_url_that_does_not_match_candidate_id(self) -> None:
        client = YouTubeClient()
        other_id_url = "https://youtu.be/abcdefghijk"
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(YouTubeClientError, "does not match"):
                client.download_clip(candidate(url=other_id_url), 0, 3, Path(temp_dir))

    def test_ffprobe_rejects_clip_that_exceeds_requested_cap(self) -> None:
        client = YouTubeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl = FakeYoutubeDL({})

            def make_ydl(options: dict) -> FakeYoutubeDL:
                ydl.options = options
                return ydl

            def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"mock mp4")
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 0, '{"format":{"duration":"5.1"}}', "")

            with (
                patch.object(client, "_create_ydl", side_effect=make_ydl),
                patch.object(client, "_download_range_callback", return_value=object()),
                patch("pipeline.clients.youtube_client.subprocess.run", side_effect=run),
            ):
                with self.assertRaisesRegex(YouTubeClientError, "permitted maximum"):
                    client.download_clip(candidate(), 10, 15, Path(temp_dir))


if __name__ == "__main__":
    unittest.main()
