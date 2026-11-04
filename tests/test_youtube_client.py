from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.clients.youtube_cache import InfoCache
from pipeline.clients.youtube_client import (
    StoryboardFrame,
    SubtitleCue,
    YouTubeCandidate,
    YouTubeClient,
    YouTubeClientError,
)
from pipeline.clients.youtube_proxy import ProxyConfig


VIDEO_ID = "dQw4w9WgXcQ"
OTHER_ID = "abcdefghijk"


def candidate(
    *,
    video_id: str = VIDEO_ID,
    url: str | None = None,
    duration: float = 120.0,
) -> YouTubeCandidate:
    return YouTubeCandidate(
        video_id=video_id,
        url=url or f"https://www.youtube.com/watch?v={video_id}",
        title="Example",
        uploader="Uploader",
        description="Description",
        duration_seconds=duration,
        view_count=12,
        thumbnail_url=None,
        query="example",
    )


def make_info(video_id: str = VIDEO_ID, *, expire: float | None = None, storyboard: bool = True) -> dict:
    expire_value = int(expire if expire is not None else time.time() + 6 * 3600)
    formats = [
        {
            "format_id": "136",
            "url": f"https://rr1---sn-example.googlevideo.com/videoplayback?expire={expire_value}&itag=136",
            "height": 720,
            "width": 1280,
            "fps": 30,
            "vcodec": "avc1.64001F",
            "acodec": "none",
            "protocol": "https",
        }
    ]
    if storyboard:
        formats.insert(
            0,
            {
                "format_id": "sb0",
                "format_note": "storyboard",
                "ext": "mhtml",
                "protocol": "mhtml",
                "acodec": "none",
                "vcodec": "none",
                "url": "https://i.ytimg.com/sb/x/storyboard3_L2/M$M.jpg?sqp=abc&sigh=def",
                "width": 160,
                "height": 90,
                "fps": 0.5,  # one thumbnail every two seconds
                "rows": 5,
                "columns": 5,
                "fragments": [
                    {"url": f"https://i.ytimg.com/sb/x/storyboard3_L2/M{index}.jpg?sqp=abc&sigh=def", "duration": 50}
                    for index in range(3)
                ],
            },
        )
    return {
        "id": video_id,
        "title": "Example",
        "duration": 120,
        "uploader": "Channel",
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "formats": formats,
        "requested_formats": [{"format_id": "136"}],
        "__private": "drop me",
    }


class FakeYoutubeDL:
    """Mimics the two YoutubeDL behaviours the client relies on.

    ``extract_info`` with ``download=True`` writes captions when ``skip_download``
    is set and a media file otherwise. ``process_ie_result`` replays a stored info
    dict the same way, without any extraction.
    """

    def __init__(
        self,
        options: dict,
        *,
        entries: list[dict] | None = None,
        subtitle_tracks: tuple[str, ...] = ("en",),
        fail_process: bool = False,
        fail_extract: bool = False,
    ) -> None:
        self.params = dict(options)
        self.entries = entries or []
        self.subtitle_tracks = subtitle_tracks
        self.fail_process = fail_process
        self.fail_extract = fail_extract
        self.extract_calls: list[tuple[str, bool]] = []
        self.process_calls: list[str] = []

    def extract_info(self, url: str, *, download: bool) -> dict:
        self.extract_calls.append((url, download))
        if url.startswith("ytsearch"):
            if download:
                raise AssertionError("search must not download anything")
            return {"_type": "playlist", "entries": self.entries}
        if self.fail_extract:
            raise RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
        video_id = url.rsplit("=", 1)[-1]
        info = make_info(video_id)
        if download:
            self._write_outputs(info)
        return {**info, "requested_downloads": [{"height": 720}]}

    def process_ie_result(self, info: dict, *, download: bool) -> dict:
        self.process_calls.append(info["id"])
        if "__private" in info or "requested_formats" in info:
            raise AssertionError("cached info must be sanitized before replay")
        if self.fail_process:
            raise RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
        if download:
            self._write_outputs(info)
        return {**info, "requested_downloads": [{"height": 720}]}

    def _write_outputs(self, info: dict) -> None:
        template = str(self.params["outtmpl"]["default"])
        if self.params.get("skip_download"):
            for language in self.subtitle_tracks:
                path = template.replace("%(id)s", info["id"]).replace("%(ext)s", f"{language}.vtt")
                Path(path).write_text(
                    f"WEBVTT\n\n00:00:01.000 --> 00:00:02.250\nHello &amp; welcome ({language})\n",
                    encoding="utf-8",
                )
        else:
            Path(template.replace("%(ext)s", "mp4")).write_bytes(b"mock source")


def fake_media_tools(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
    if command[0] == "ffmpeg":
        Path(command[-1]).write_bytes(b"mock mp4")
        return subprocess.CompletedProcess(command, 0, "", "")
    return subprocess.CompletedProcess(command, 0, '{"format":{"duration":"5.0"}}', "")


class ClientHarness:
    """Creates a client whose YoutubeDL instances are fakes, one per proxy role."""

    def __init__(self, cache_dir: Path, *, entries: list[dict] | None = None, **client_kwargs: object) -> None:
        self.entries = entries or []
        self.created: dict[str, FakeYoutubeDL] = {}
        self.options_seen: list[dict] = []
        self.fake_kwargs: dict[str, object] = {}
        self.client = YouTubeClient(cache_dir=cache_dir, **client_kwargs)  # type: ignore[arg-type]
        self._patch = patch.object(self.client, "_create_ydl", side_effect=self._make)

    def _make(self, options: dict) -> FakeYoutubeDL:
        self.options_seen.append(options)
        fake = FakeYoutubeDL(options, entries=self.entries, **self.fake_kwargs)  # type: ignore[arg-type]
        role = "metadata" if options.get("skip_download") else "download"
        self.created[role] = fake
        return fake

    def __enter__(self) -> "ClientHarness":
        self._patch.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._patch.stop()


class YouTubeSearchTests(unittest.TestCase):
    def test_search_is_flat_filters_bad_candidates_and_extracts_each_video_once(self) -> None:
        entries = [
            {
                "id": VIDEO_ID,
                "title": "Valid",
                "duration": 120,
                "uploader": "Channel",
                "view_count": 55,
                "url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
                "thumbnails": [{"url": "https://i.ytimg.com/vi/x/hqdefault.jpg"}],
            },
            {"id": OTHER_ID, "title": "Too short", "duration": 4},
            {"id": "abcdefghij2", "title": "Too long", "duration": 1801},
            {"id": "abcdefghij3", "title": "Live", "duration": 300, "is_live": True},
            {"id": "abcdefghij4", "title": "Upcoming", "duration": 300, "live_status": "is_upcoming"},
            {"id": "abcdefghij5", "title": "No duration"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir), entries=entries) as harness:
            results = harness.client.search("  ocean documentary  ", limit=5)
            metadata = harness.created["metadata"]

            self.assertEqual([item.video_id for item in results], [VIDEO_ID])
            self.assertEqual(results[0].query, "ocean documentary")
            self.assertEqual(results[0].uploader, "Channel")
            self.assertEqual(results[0].view_count, 55)
            self.assertEqual(results[0].thumbnail_url, "https://i.ytimg.com/vi/x/hqdefault.jpg")
            self.assertEqual(results[0].subtitles, (SubtitleCue(1.0, 2.25, "Hello & welcome (en)"),))
            # One flat search request plus exactly one full extraction for the surviving video.
            self.assertEqual(
                metadata.extract_calls,
                [("ytsearch5:ocean documentary", False), (results[0].url, True)],
            )
            options = metadata.params
            self.assertEqual(options["extract_flat"], "in_playlist")
            self.assertTrue(options["skip_download"])
            self.assertEqual(options["subtitleslangs"], ["es", "es-419", "en", "en-US"])
            self.assertEqual(options["socket_timeout"], 20)
            self.assertIsNone(options["cookiefile"])
            self.assertIsNone(options["cookiesfrombrowser"])
            self.assertNotIn("proxy", options)
            self.assertTrue(str(options["cachedir"]).startswith(temp_dir), "player cache must persist on disk")
            self.assertEqual(harness.client.traffic.extractions, 1)
            self.assertIsNotNone(harness.client.info_cache.load(VIDEO_ID))

    def test_search_rejects_unbounded_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            with self.assertRaises(ValueError):
                client.search("query", limit=6)

    def test_repeated_results_reuse_cached_info_across_searches_and_runs(self) -> None:
        entry = {"id": VIDEO_ID, "title": "Example", "duration": 120}
        with tempfile.TemporaryDirectory() as temp_dir:
            with ClientHarness(Path(temp_dir), entries=[entry]) as harness:
                first = harness.client.search("robot factory", limit=1)
                second = harness.client.search("factory robots", limit=1)
                self.assertEqual(first[0].subtitles, second[0].subtitles)
                self.assertEqual(harness.created["metadata"].extract_calls.count((first[0].url, True)), 1)

            # A later run (new client, same cache directory) needs no extraction at all.
            with ClientHarness(Path(temp_dir), entries=[entry]) as later:
                results = later.client.search("robot factory", limit=1)
                self.assertEqual(results[0].subtitles, first[0].subtitles)
                self.assertEqual(later.created["metadata"].extract_calls, [("ytsearch1:robot factory", False)])
                self.assertEqual(later.client.traffic.extractions, 0)
                self.assertEqual(later.client.traffic.info_reuses, 1)

    def test_cached_info_without_cues_downloads_subtitles_from_stored_urls(self) -> None:
        entry = {"id": VIDEO_ID, "title": "Example", "duration": 120}
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = InfoCache(Path(temp_dir) / "youtube-info")
            cache.store(VIDEO_ID, make_info(), proxy_role="download", session_id="abc")
            with ClientHarness(Path(temp_dir), entries=[entry]) as harness:
                results = harness.client.search("robot factory", limit=1)
                metadata = harness.created["metadata"]
                self.assertEqual(results[0].subtitles, (SubtitleCue(1.0, 2.25, "Hello & welcome (en)"),))
                self.assertEqual(metadata.process_calls, [VIDEO_ID])
                self.assertEqual(metadata.extract_calls, [("ytsearch1:robot factory", False)])
                stored = cache.load(VIDEO_ID)
                assert stored is not None
                self.assertEqual(stored.subtitle_cues, [{"s": 1.0, "e": 2.25, "t": "Hello & welcome (en)"}])

    def test_retrieve_subtitles_prefers_spanish_track_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir)) as harness:
            harness.fake_kwargs["subtitle_tracks"] = ("en", "es")
            cues = harness.client._retrieve_subtitles(f"https://www.youtube.com/watch?v={VIDEO_ID}", VIDEO_ID)
            self.assertEqual(cues, (SubtitleCue(1.0, 2.25, "Hello & welcome (es)"),))

    def test_vtt_and_json3_subtitle_parsers(self) -> None:
        vtt = """WEBVTT

00:00:01.100 --> 00:00:02.250 align:start
<c>Hello</c>
world &amp; friends

"""
        json3 = json.dumps(
            {"events": [{"tStartMs": 3250, "dDurationMs": 800, "segs": [{"utf8": "Hola "}, {"utf8": "mundo"}]}]}
        )
        self.assertEqual(YouTubeClient._parse_vtt(vtt), [SubtitleCue(1.1, 2.25, "Hello world & friends")])
        self.assertEqual(YouTubeClient._parse_json3(json3), [SubtitleCue(3.25, 4.05, "Hola mundo")])


class YouTubeDownloadTests(unittest.TestCase):
    def test_download_reuses_cached_info_instead_of_extracting_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir)) as harness:
            harness.client.info_cache.store(VIDEO_ID, make_info(), proxy_role="metadata", session_id="s1")
            callback = object()
            process_calls: list[list[str]] = []

            def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
                process_calls.append(command)
                return fake_media_tools(command, **kwargs)

            with (
                patch.object(harness.client, "_download_range_callback", return_value=callback) as range_factory,
                patch("pipeline.clients.youtube_client.subprocess.run", side_effect=run),
            ):
                result = harness.client.download_clip(candidate(), 12, 30, Path(temp_dir) / "out", max_clip_seconds=9)
            provenance = json.loads(result.with_suffix(".json").read_text(encoding="utf-8"))
            download = harness.created["download"]

            self.assertEqual(range_factory.call_args.args, (12, 17))
            self.assertEqual(download.process_calls, [VIDEO_ID])
            self.assertEqual(download.extract_calls, [])
            self.assertFalse(download.params["skip_download"])
            self.assertIs(download.params["download_ranges"], callback)
            self.assertEqual(download.params["format"], "bestvideo[height<=720][fps<=30]/bestvideo[height<=720]/best[height<=720]")
            self.assertEqual(download.params["format_sort"], ["res", "fps", "+size", "+br"])
            self.assertTrue(download.params["force_keyframes_at_cuts"])
            self.assertTrue(result.name.startswith("youtube_"))
            self.assertEqual(provenance["clip_range_seconds"], {"start": 12, "end": 17})
            self.assertEqual(provenance["source_height"], 720)
            self.assertFalse(provenance["reused_from_library"])
            ffmpeg = process_calls[0]
            self.assertEqual(ffmpeg[ffmpeg.index("-t") + 1], "5.000000")
            self.assertIn("-an", ffmpeg)
            self.assertIn("libx264", ffmpeg)
            self.assertIn("fps=30", ffmpeg[ffmpeg.index("-vf") + 1])
            traffic = harness.client.traffic
            self.assertEqual(traffic.info_reuses, 1)
            self.assertEqual(traffic.extractions, 0)
            self.assertEqual(traffic.clip_downloads, 1)
            self.assertEqual(traffic.bytes_for("download"), len(b"mock source"))
            # The prepared clip is now in the shared library for other runs.
            self.assertIsNotNone(harness.client.clip_library.find(VIDEO_ID, 12, 17, required_height=720))

    def test_failed_replay_invalidates_cache_and_falls_back_to_one_fresh_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir)) as harness:
            harness.fake_kwargs["fail_process"] = True
            harness.client.info_cache.store(VIDEO_ID, make_info(), proxy_role="metadata", session_id="s1")
            with patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools):
                result = harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")
            download = harness.created["download"]

            self.assertTrue(result.is_file())
            self.assertEqual(download.process_calls, [VIDEO_ID])
            self.assertEqual(download.extract_calls, [(candidate().url, True)])
            self.assertEqual(harness.client.traffic.info_refreshes, 1)
            self.assertEqual(harness.client.traffic.extractions, 1)
            refreshed = harness.client.info_cache.load(VIDEO_ID)
            assert refreshed is not None
            self.assertEqual(refreshed.proxy_role, "download")
            self.assertNotIn("__private", refreshed.info)

    def test_download_without_cached_info_extracts_once_and_caches_for_later(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir)) as harness:
            with patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools):
                harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")
                harness.client.download_clip(candidate(), 40, 45, Path(temp_dir) / "out")
            download = harness.created["download"]
            self.assertEqual(download.extract_calls, [(candidate().url, True)])
            self.assertEqual(download.process_calls, [VIDEO_ID])
            self.assertEqual(harness.client.traffic.extractions, 1)
            self.assertEqual(harness.client.traffic.info_reuses, 1)

    def test_expired_cached_info_is_not_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir)) as harness:
            harness.client.info_cache.store(
                VIDEO_ID,
                make_info(expire=time.time() + 10 * 60),  # inside the 15-minute margin
                proxy_role="metadata",
                session_id="s1",
            )
            with patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools):
                harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")
            download = harness.created["download"]
            self.assertEqual(download.process_calls, [])
            self.assertEqual(download.extract_calls, [(candidate().url, True)])

    def test_fresh_download_failure_rotates_sticky_session(self) -> None:
        proxies = ProxyConfig.from_values(download="http://user:secret@proxy.example:8000", metadata=None)
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir), proxies=proxies) as harness:
            harness.fake_kwargs["fail_extract"] = True
            first_session = harness.client.session_id
            with patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools):
                with self.assertRaises(YouTubeClientError):
                    harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")
            first_proxy = harness.options_seen[0]["proxy"]
            self.assertIn(f"user-time-30-session-{first_session}:secret@proxy.example:8000", first_proxy)
            self.assertNotEqual(harness.client.session_id, first_session)
            harness.fake_kwargs["fail_extract"] = False
            with patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools):
                harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")
            second_proxy = harness.options_seen[-1]["proxy"]
            self.assertNotEqual(first_proxy, second_proxy)
            self.assertIn(f"session-{harness.client.session_id}:secret@", second_proxy)

    def test_metadata_and_download_roles_get_their_own_proxy(self) -> None:
        proxies = ProxyConfig.from_values(
            download="http://user:p%40ss@residential.example:8000",
            metadata="http://meta:word@datacenter.example:9000",
        )
        entry = {"id": VIDEO_ID, "title": "Example", "duration": 120}
        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir), entries=[entry], proxies=proxies) as harness:
            harness.client.search("robots", limit=1)
            with patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools):
                harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")
            session = harness.client.session_id
            self.assertEqual(
                harness.created["metadata"].params["proxy"],
                f"http://meta-time-30-session-{session}:word@datacenter.example:9000",
            )
            self.assertEqual(
                harness.created["download"].params["proxy"],
                f"http://user-time-30-session-{session}:p%40ss@residential.example:8000",
            )
            self.assertNotIn("word", proxies.describe())
            self.assertNotIn("p%40ss", proxies.describe())

    def test_download_rejects_non_youtube_domain_before_downloader_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
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
        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            for url in (
                f"http://youtube.com/watch?v={VIDEO_ID}",
                f"https://example.com/watch?v={VIDEO_ID}",
                f"https://user@youtu.be/{VIDEO_ID}",
            ):
                with self.subTest(url=url):
                    with self.assertRaises(YouTubeClientError):
                        client.download_clip(candidate(url=url), 0, 3, Path(temp_dir))

    def test_download_rejects_url_that_does_not_match_candidate_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            with self.assertRaisesRegex(YouTubeClientError, "does not match"):
                client.download_clip(candidate(url="https://youtu.be/abcdefghijk"), 0, 3, Path(temp_dir))

    def test_ffprobe_rejects_clip_that_exceeds_requested_cap(self) -> None:
        def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
            if command[0] == "ffmpeg":
                Path(command[-1]).write_bytes(b"mock mp4")
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(command, 0, '{"format":{"duration":"5.1"}}', "")

        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir)) as harness:
            with patch("pipeline.clients.youtube_client.subprocess.run", side_effect=run):
                with self.assertRaisesRegex(YouTubeClientError, "permitted maximum"):
                    harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")

    def test_local_ffmpeg_and_ffprobe_never_inherit_proxy_variables(self) -> None:
        seen_envs: list[dict] = []

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            seen_envs.append(dict(kwargs["env"]))  # type: ignore[arg-type]
            return fake_media_tools(command, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir, ClientHarness(Path(temp_dir)) as harness:
            with (
                patch.dict(os.environ, {"HTTPS_PROXY": "http://u:p@proxy.example:1", "http_proxy": "http://x"}),
                patch("pipeline.clients.youtube_client.subprocess.run", side_effect=run),
            ):
                harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "out")
        self.assertEqual(len(seen_envs), 2)
        for env in seen_envs:
            self.assertNotIn("HTTPS_PROXY", env)
            self.assertNotIn("http_proxy", env)


class ClipLibraryReuseTests(unittest.TestCase):
    def test_second_run_reuses_prepared_clip_without_any_network_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with ClientHarness(Path(temp_dir)) as harness, patch(
                "pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools
            ):
                first = harness.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "run-a")

            client = YouTubeClient(cache_dir=Path(temp_dir))
            with (
                patch.object(client, "_create_ydl") as make_ydl,
                patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools),
            ):
                second = client.download_clip(candidate(), 10, 15, Path(temp_dir) / "run-b")
            make_ydl.assert_not_called()
            self.assertEqual(second.read_bytes(), first.read_bytes())
            provenance = json.loads(second.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertTrue(provenance["reused_from_library"])
            self.assertEqual(client.traffic.clip_library_hits, 1)
            self.assertEqual(client.traffic.clip_downloads, 0)

    def test_library_entry_from_a_lower_resolution_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with ClientHarness(Path(temp_dir), max_height=480) as low, patch(
                "pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools
            ):
                low.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "run-a")
            # The fake reports a 720p source; pretend it was really 480p.
            manifest = low.client.clip_library.directory / f"{VIDEO_ID}_10p000_15p000.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["source_height"] = 480
            manifest.write_text(json.dumps(data), encoding="utf-8")

            with ClientHarness(Path(temp_dir)) as high, patch(
                "pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools
            ):
                high.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "run-b")
            self.assertEqual(high.client.traffic.clip_library_hits, 0)
            self.assertEqual(high.client.traffic.clip_downloads, 1)

    def test_library_entry_from_a_higher_resolution_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with ClientHarness(Path(temp_dir), max_height=1080) as high, patch(
                "pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools
            ):
                high.client.download_clip(candidate(), 10, 15, Path(temp_dir) / "run-a")
            manifest = high.client.clip_library.directory / f"{VIDEO_ID}_10p000_15p000.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["source_height"] = 1080
            manifest.write_text(json.dumps(data), encoding="utf-8")

            client = YouTubeClient(cache_dir=Path(temp_dir))
            with (
                patch.object(client, "_create_ydl") as make_ydl,
                patch("pipeline.clients.youtube_client.subprocess.run", side_effect=fake_media_tools),
            ):
                client.download_clip(candidate(), 10, 15, Path(temp_dir) / "run-b")
            make_ydl.assert_not_called()
            self.assertEqual(client.traffic.clip_library_hits, 1)


class StoryboardTests(unittest.TestCase):
    def test_storyboard_frames_map_times_to_mosaic_crops(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            client.info_cache.store(VIDEO_ID, make_info(), proxy_role="metadata", session_id="s")
            frames = client.storyboard_frames(candidate(), 60.0, 65.0, max_frames=4)

        # 0.5 fps -> thumbnails every 2 s; samples at 60.6, 61.9, 63.1, 64.4 s -> indices 30, 30, 31, 32.
        self.assertEqual([frame.time_seconds for frame in frames], [60.0, 62.0, 64.0])
        first = frames[0]
        self.assertEqual(first.fragment_url, "https://i.ytimg.com/sb/x/storyboard3_L2/M1.jpg?sqp=abc&sigh=def")
        self.assertEqual((first.x, first.y, first.width, first.height), (0, 90, 160, 90))  # index 30 -> fragment 1, slot 5
        self.assertEqual((frames[2].x, frames[2].y), (320, 90))  # index 32 -> slot 7 -> column 2, row 1

    def test_storyboard_frames_add_neighbours_for_coarse_storyboards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            info = make_info()
            info["formats"][0]["fps"] = 0.1  # one thumbnail every 10 s
            client.info_cache.store(VIDEO_ID, info, proxy_role="metadata", session_id="s")
            frames = client.storyboard_frames(candidate(), 60.0, 65.0)
        self.assertEqual([frame.time_seconds for frame in frames], [50.0, 60.0, 70.0])

    def test_storyboard_frames_empty_without_storyboard_or_cached_info(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            self.assertEqual(client.storyboard_frames(candidate(), 1, 4), [])
            client.info_cache.store(VIDEO_ID, make_info(storyboard=False), proxy_role="metadata", session_id="s")
            self.assertEqual(client.storyboard_frames(candidate(), 1, 4), [])

    def test_storyboard_sheet_fetches_cdn_directly_and_tiles_locally(self) -> None:
        fetched: list[str] = []
        tiled: list[tuple] = []

        def fetch(url: str) -> bytes:
            fetched.append(url)
            return b"jpegdata"

        def tile(crops: list[tuple], output_path: Path) -> Path:
            tiled.append(tuple(crops))
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"sheet")
            return output_path

        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            client.info_cache.store(VIDEO_ID, make_info(), proxy_role="metadata", session_id="s")
            with (
                patch.object(client, "_fetch_direct", side_effect=lambda url: (client.traffic.record("direct", 8), fetch(url))[1]),
                patch("pipeline.candidate_analyzer.create_storyboard_contact_sheet", side_effect=tile),
            ):
                sheet = client.storyboard_sheet(candidate(), 60.0, 65.0, Path(temp_dir) / "sheets" / "preview.jpg")
            assert sheet is not None
            self.assertTrue(sheet.is_file())

        self.assertEqual(fetched, ["https://i.ytimg.com/sb/x/storyboard3_L2/M1.jpg?sqp=abc&sigh=def"])
        self.assertEqual(len(tiled[0]), 3)
        self.assertEqual(client.traffic.storyboard_previews, 1)
        self.assertEqual(client.traffic.bytes_for("direct"), 8)
        self.assertEqual(client.traffic.bytes_for("metadata"), 0)
        self.assertEqual(client.traffic.bytes_for("download"), 0)

    def test_fetch_direct_ignores_environment_proxies(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            content = b"img"

            def raise_for_status(self) -> None:
                return None

        class FakeSession:
            def __init__(self) -> None:
                self.trust_env = True

            def get(self, url: str, *, timeout: float) -> FakeResponse:
                captured["trust_env"] = self.trust_env
                captured["url"] = url
                return FakeResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            client = YouTubeClient(cache_dir=Path(temp_dir))
            with patch("requests.Session", FakeSession):
                data = client._fetch_direct("https://i.ytimg.com/sb/x/M0.jpg")
        self.assertEqual(data, b"img")
        self.assertFalse(captured["trust_env"])
        self.assertEqual(client.traffic.bytes_for("direct"), 3)

    def test_storyboard_frame_is_a_plain_record(self) -> None:
        frame = StoryboardFrame(1.0, "https://i.ytimg.com/x.jpg", 0, 0, 160, 90)
        self.assertEqual(frame.width * frame.height, 14400)


if __name__ == "__main__":
    unittest.main()
