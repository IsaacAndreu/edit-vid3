from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from pipeline.schemas import BrollSpec, Candidate, Storyboard
from pipeline.sourcing.common import SourceUnavailable, fuse_ranks
from pipeline.sourcing.images import ImageSources, image_query
from pipeline.sourcing.youtube import YouTubeSource, _parse_rate


BROLL = BrollSpec.model_validate({
    "visualIntent": "Gran Casino de Madrid exterior",
    "queriesEn": ["gran casino madrid exterior aerial", "casino building spain", "casino entrance night"],
    "queriesEs": ["Gran Casino de Madrid Torrelodones"],
    "entities": ["Gran Casino de Madrid"],
})


def _youtube(tmp: str, **cfg) -> YouTubeSource:
    return YouTubeSource(root=Path(tmp), cache_dir=Path(tmp) / "cache", config={"min_interval": 0, **cfg})


class YouTubeFilterTests(unittest.TestCase):
    def test_search_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp)
            ok = {"id": "abcdefghijk", "duration": 300, "url": "https://www.youtube.com/watch?v=abcdefghijk"}
            self.assertTrue(yt.passes_search_filters(ok))
            self.assertFalse(yt.passes_search_filters({**ok, "duration": 20}))           # too short
            self.assertFalse(yt.passes_search_filters({**ok, "duration": 4000}))         # too long
            self.assertFalse(yt.passes_search_filters({**ok, "live_status": "is_live"}))
            self.assertFalse(yt.passes_search_filters({**ok, "url": "https://www.youtube.com/shorts/abcdefghijk"}))
            self.assertFalse(yt.passes_search_filters({**ok, "duration": None}))

    def test_metadata_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp)
            info = {"maxHeight": 1080, "width": 1920, "height": 1080, "channel": "Canal",
                    "storyboard": {"fps": 0.2, "width": 320}}
            self.assertTrue(yt.passes_metadata_filters(info))
            self.assertFalse(yt.passes_metadata_filters({**info, "maxHeight": 480}))
            self.assertFalse(yt.passes_metadata_filters({**info, "width": 1080, "height": 1920}))
            self.assertFalse(yt.passes_metadata_filters({**info, "channel": ""}))
            self.assertFalse(yt.passes_metadata_filters({**info, "storyboard": None}))


class StoryboardTests(unittest.TestCase):
    INFO = {"id": "AAAAAAAAAAA", "duration": 100, "storyboard": {
        "urls": ["https://i.ytimg.com/sb/a/M0.jpg", "https://i.ytimg.com/sb/a/M1.jpg"],
        "columns": 3, "rows": 3, "width": 320, "height": 180, "fps": 0.1}}

    def test_sheets_are_fetched_once_and_frames_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp)
            calls = []

            class Response:
                content = b"jpg"
                def raise_for_status(self): ...

            def fake_get(url, timeout):
                calls.append(url)
                return Response()

            with patch.object(yt.http, "get", side_effect=fake_get):
                board = yt.storyboard(self.INFO)
                again = yt.storyboard(self.INFO)
        self.assertEqual(len(calls), 2)                      # second call is served from disk
        self.assertEqual(board, again)
        self.assertEqual(board.frames, 11)                   # 100 s at 0.1 fps → frames 0..10
        self.assertAlmostEqual(board.interval, 10.0)
        self.assertEqual(board.locate(0), (0, 0, 0))
        self.assertEqual(board.locate(4), (0, 320, 180))
        self.assertEqual(board.locate(10), (1, 320, 0))


class YouTubeCandidateTests(unittest.TestCase):
    def _search_results(self, query: str):
        return [
            {"id": "AAAAAAAAAAA", "title": "Gran Casino de Madrid drone", "channel": "Drone ES", "duration": 200, "url": ""},
            {"id": "BBBBBBBBBBB", "title": "random vlog", "channel": "X", "duration": 900, "url": ""},
            {"id": "CCCCCCCCCCC", "title": "short", "channel": "Y", "duration": 200, "url": "https://www.youtube.com/shorts/CCCCCCCCCCC"},
        ]

    def test_builds_candidates_with_credit_and_storyboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp, videos_per_shot=2)
            infos = {
                "AAAAAAAAAAA": {"id": "AAAAAAAAAAA", "title": "Gran Casino de Madrid drone", "channel": "Drone ES", "uploader": "drone",
                                "license": "youtube-standard", "duration": 200, "width": 1920, "height": 1080, "maxHeight": 2160},
                "BBBBBBBBBBB": {"id": "BBBBBBBBBBB", "title": "vlog", "channel": "X", "uploader": None, "license": "creative-commons",
                                "duration": 900, "width": 1280, "height": 720, "maxHeight": 480},
            }

            for info in infos.values():
                info["storyboard"] = {"fps": 0.2, "width": 320}
            board = Storyboard(sheets=["cache/sb/000.jpg"], columns=3, rows=3, tileWidth=320, tileHeight=180,
                               interval=5.0, frames=9)

            with patch.object(yt, "search", side_effect=self._search_results), patch.object(
                yt, "info", side_effect=lambda v: infos[v]
            ), patch.object(yt, "storyboard", return_value=board):
                notes: list[str] = []
                result = yt.candidates(BROLL, notes)
        self.assertEqual([c.id for c in result], ["yt:AAAAAAAAAAA"])       # B fails 720p, C is a short
        candidate = result[0]
        self.assertEqual(candidate.credit, "Fuente: Drone ES")
        self.assertEqual(candidate.storyboard.frames, 9)

    def test_block_trips_the_breaker_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp)
            calls = []

            def boom():
                calls.append(1)
                raise Exception("ERROR: Sign in to confirm you’re not a bot")

            with self.assertRaises(SourceUnavailable):
                yt._call("metadata", boom)
            with self.assertRaises(SourceUnavailable):
                yt._call("metadata", boom)
            self.assertEqual(len(calls), 1)
            with patch.object(yt, "search", side_effect=SourceUnavailable("blocked")):
                with self.assertRaises(SourceUnavailable):
                    yt.candidates(BROLL, [])

    def test_429_is_retried_not_a_block(self) -> None:
        from pipeline.sourcing.youtube import RateLimited

        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp, rate_backoff=0)
            calls = []

            def flaky():
                calls.append(1)
                if len(calls) < 3:
                    raise Exception("HTTP Error 429: Too Many Requests")
                return "ok"

            self.assertEqual(yt._call("search", flaky), "ok")
            self.assertIsNone(yt.blocked)
            with self.assertRaises(RateLimited):
                yt._call("subtitles", lambda: (_ for _ in ()).throw(Exception("HTTP Error 429")), rate_retries=0)
            self.assertIsNone(yt.blocked)

    def test_rate_parsing(self) -> None:
        self.assertEqual(_parse_rate("2M"), 2 * 1024 * 1024)
        self.assertEqual(_parse_rate("500K"), 500 * 1024)
        with self.assertRaises(ValueError):
            _parse_rate("fast")


class ImageTests(unittest.TestCase):
    def test_image_query_drops_camera_words(self) -> None:
        self.assertEqual(image_query("american roulette wheel spinning"), "american roulette wheel")
        self.assertEqual(image_query("aerial drone footage"), "aerial drone footage")  # nothing left → keep

    def test_wikimedia_filters_licence_size_and_aspect(self) -> None:
        def page(pid, width, height, licence, mime="image/jpeg"):
            return {"pageid": pid, "index": pid, "title": f"File:Img{pid}.jpg", "imageinfo": [{
                "width": width, "height": height, "mime": mime, "thumburl": f"https://u/{pid}.jpg",
                "descriptionurl": f"https://commons/{pid}",
                "extmetadata": {"LicenseShortName": {"value": licence}, "Artist": {"value": "<a href='x'>Ana</a>"}}}]}

        payload = {"query": {"pages": {str(i): p for i, p in enumerate([
            page(1, 2000, 1200, "CC BY-SA 4.0"),
            page(2, 800, 500, "CC BY 2.0"),            # too small
            page(3, 1500, 2000, "CC0"),                # portrait
            page(4, 2000, 1200, "CC BY-NC 2.0"),       # non-commercial
            page(5, 2000, 1200, "Fair use"),           # unclear licence
            page(6, 2000, 1200, "CC BY-ND 3.0"),       # no derivatives
        ])}}}
        with tempfile.TemporaryDirectory() as tmp:
            sources = ImageSources(root=Path(tmp), cache_dir=Path(tmp) / "cache", config={})
            with patch("pipeline.sourcing.images.http_get_json", return_value=payload):
                results = sources._search_wikimedia("casino")
        self.assertEqual([r["id"] for r in results], ["wm:1"])
        self.assertEqual(results[0]["credit"], "Fuente: Ana / Wikimedia Commons")
        self.assertIn("CC BY-SA 4.0", results[0]["attribution"])

    def test_quota_exhaustion_disables_source_but_keeps_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sources = ImageSources(root=Path(tmp), cache_dir=Path(tmp) / "cache", config={})
            notes: list[str] = []
            with patch.object(sources, "_search_wikimedia", return_value=[]), patch.object(
                sources, "_search_openverse", side_effect=SourceUnavailable("429")
            ):
                sources.search(BROLL, notes)
                sources.search(BROLL, notes)
            self.assertIn("openverse", sources.disabled)
            self.assertEqual(sum("openverse desactivado" in n for n in notes), 1)


class CandidateSchemaTests(unittest.TestCase):
    def test_requires_media_and_a_real_credit(self) -> None:
        base = {"id": "yt:x", "source": "youtube", "kind": "video", "url": "u", "title": "t", "channel": "c",
                "license": "l", "attribution": "a", "query": "q", "rankScore": 0.1}
        board = {"sheets": ["s.jpg"], "columns": 3, "rows": 3, "tileWidth": 320, "tileHeight": 180, "interval": 5, "frames": 9}
        with self.assertRaises(ValidationError):
            Candidate.model_validate({**base, "credit": "Fuente: c"})                    # video without storyboard
        with self.assertRaises(ValidationError):
            Candidate.model_validate({**base, "credit": "c", "storyboard": board})
        Candidate.model_validate({**base, "credit": "Fuente: c", "storyboard": board})

    def test_rank_fusion(self) -> None:
        scores = fuse_ranks([["a", "b"], ["b", "c"]])
        self.assertGreater(scores["b"], scores["a"])
        self.assertGreater(scores["a"], scores["c"])


if __name__ == "__main__":
    unittest.main()
