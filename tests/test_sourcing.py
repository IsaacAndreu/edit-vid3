from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from pipeline.schemas import BrollSpec, Candidate
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
            info = {"maxHeight": 1080, "width": 1920, "height": 1080, "channel": "Canal"}
            self.assertTrue(yt.passes_metadata_filters(info))
            self.assertFalse(yt.passes_metadata_filters({**info, "maxHeight": 480}))
            self.assertFalse(yt.passes_metadata_filters({**info, "width": 1080, "height": 1920}))
            self.assertFalse(yt.passes_metadata_filters({**info, "channel": ""}))


class SectionPlanTests(unittest.TestCase):
    def test_short_video_is_downloaded_whole(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_youtube(tmp).plan_sections({"id": "x", "duration": 300}, set(), set()), [(0.0, 300, "full")])

    def test_long_video_uses_subtitle_hits_outside_intro_and_outro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp, section_padding=10, max_sections=2)
            cues = [
                (5.0, 8.0, "casino madrid casino madrid"),          # inside the first 5 %: ignored
                (600.0, 604.0, "the gran casino madrid building"),
                (1200.0, 1203.0, "nothing relevant here"),
                (1500.0, 1504.0, "casino building at night"),
            ]
            with patch.object(yt, "subtitles", return_value=cues):
                sections = yt.plan_sections({"id": "x", "duration": 2000}, {"casino", "building", "night"}, {"madrid"})
            self.assertEqual([(a, b) for a, b, _ in sections], [(590.0, 614.0), (1490.0, 1514.0)])
            self.assertTrue(all(reason.startswith("subtítulo") for *_, reason in sections))

    def test_long_video_without_subtitles_is_sampled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp)
            with patch.object(yt, "subtitles", return_value=[]):
                sections = yt.plan_sections({"id": "x", "duration": 1000}, {"casino"}, set())
            self.assertEqual(len(sections), 3)
            self.assertTrue(all(reason == "muestreo" and b - a == 30 for a, b, reason in sections))


class YouTubeCandidateTests(unittest.TestCase):
    def _search_results(self, query: str):
        return [
            {"id": "AAAAAAAAAAA", "title": "Gran Casino de Madrid drone", "channel": "Drone ES", "duration": 200, "url": ""},
            {"id": "BBBBBBBBBBB", "title": "random vlog", "channel": "X", "duration": 900, "url": ""},
            {"id": "CCCCCCCCCCC", "title": "short", "channel": "Y", "duration": 200, "url": "https://www.youtube.com/shorts/CCCCCCCCCCC"},
        ]

    def test_builds_candidates_with_credit_and_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt = _youtube(tmp, videos_per_shot=2)
            infos = {
                "AAAAAAAAAAA": {"id": "AAAAAAAAAAA", "title": "Gran Casino de Madrid drone", "channel": "Drone ES", "uploader": "drone",
                                "license": "youtube-standard", "duration": 200, "width": 1920, "height": 1080, "maxHeight": 2160},
                "BBBBBBBBBBB": {"id": "BBBBBBBBBBB", "title": "vlog", "channel": "X", "uploader": None, "license": "creative-commons",
                                "duration": 900, "width": 1280, "height": 720, "maxHeight": 480},
            }

            def fake_download(video_id, start, end):
                path = Path(tmp) / "cache" / "videos" / video_id / f"a360_{start:.2f}_{end:.2f}.mp4"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
                return path

            with patch.object(yt, "search", side_effect=self._search_results), patch.object(
                yt, "info", side_effect=lambda v: infos[v]
            ), patch.object(yt, "download_section", side_effect=fake_download):
                notes: list[str] = []
                result = yt.candidates(BROLL, notes)
        self.assertEqual([c.id for c in result], ["yt:AAAAAAAAAAA"])       # B fails 720p, C is a short
        candidate = result[0]
        self.assertEqual(candidate.credit, "Fuente: Drone ES")
        self.assertEqual(candidate.analysis[0].reason, "full")
        self.assertTrue(candidate.analysis[0].path.startswith("cache/videos/AAAAAAAAAAA/"))

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
        with self.assertRaises(ValidationError):
            Candidate.model_validate({**base, "credit": "Fuente: c"})                    # video without ranges
        with self.assertRaises(ValidationError):
            Candidate.model_validate({**base, "credit": "c", "analysis": [{"path": "p", "start": 0, "end": 5}]})
        Candidate.model_validate({**base, "credit": "Fuente: c", "analysis": [{"path": "p", "start": 0, "end": 5}]})

    def test_rank_fusion(self) -> None:
        scores = fuse_ranks([["a", "b"], ["b", "c"]])
        self.assertGreater(scores["b"], scores["a"])
        self.assertGreater(scores["a"], scores["c"])


if __name__ == "__main__":
    unittest.main()
