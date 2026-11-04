from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.clients.youtube_cache import (
    DEFAULT_INFO_TTL_SECONDS,
    ClipLibrary,
    InfoCache,
    earliest_format_expiry,
    sanitize_info,
)


VIDEO_ID = "dQw4w9WgXcQ"


def info_with_expiry(*expiries: int, video_id: str = VIDEO_ID) -> dict:
    return {
        "id": video_id,
        "title": "Example",
        "formats": [
            {"format_id": str(index), "url": f"https://rr1.googlevideo.com/videoplayback?expire={expire}&itag=1"}
            for index, expire in enumerate(expiries)
        ]
        + [{"format_id": "sb0", "url": "https://i.ytimg.com/sb/M$M.jpg?sigh=x"}],
    }


class SanitizeInfoTests(unittest.TestCase):
    def test_strips_private_and_requested_keys_like_clean_infojson(self) -> None:
        info = {
            "id": VIDEO_ID,
            "__postprocessors": [],
            "requested_formats": [{}],
            "requested_downloads": [{}],
            "filepath": "/tmp/x",
            "original_url": "https://youtu.be/x",
            "formats": [{"format_id": "1", "url": "u", "http_headers": {"A": "b"}, "__x": 1}],
            "none_value": None,
            "weird": object(),
        }
        sanitized = sanitize_info(info)
        self.assertEqual(
            set(sanitized),
            {"id", "formats", "weird", "_type"},
        )
        self.assertEqual(sanitized["formats"][0], {"format_id": "1", "url": "u", "http_headers": {"A": "b"}})
        self.assertIsInstance(sanitized["weird"], str)
        self.assertEqual(sanitized["_type"], "video")
        json.dumps(sanitized)


class ExpiryTests(unittest.TestCase):
    def test_earliest_expiry_ignores_urls_without_expire(self) -> None:
        self.assertEqual(earliest_format_expiry(info_with_expiry(2000, 1500)), 1500.0)
        self.assertIsNone(earliest_format_expiry({"id": VIDEO_ID, "formats": [{"url": "https://x/?a=1"}]}))


class InfoCacheTests(unittest.TestCase):
    def test_store_and_load_roundtrip_with_sanitization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = InfoCache(Path(temp_dir), margin_seconds=900)
            info = {**info_with_expiry(10_000), "requested_formats": [1], "__private": True}
            stored = cache.store(VIDEO_ID, info, proxy_role="metadata", session_id="abc", now=1000.0)
            self.assertNotIn("__private", stored.info)
            loaded = cache.load(VIDEO_ID, now=2000.0)
            assert loaded is not None
            self.assertEqual(loaded.info["id"], VIDEO_ID)
            self.assertNotIn("requested_formats", loaded.info)
            self.assertEqual(loaded.proxy_role, "metadata")
            self.assertEqual(loaded.session_id, "abc")
            self.assertEqual(loaded.stored_at, 1000.0)
            self.assertEqual(loaded.expires_at, 10_000.0)

    def test_entry_inside_margin_is_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = InfoCache(Path(temp_dir), margin_seconds=900)
            cache.store(VIDEO_ID, info_with_expiry(10_000), proxy_role="metadata", session_id=None, now=1000.0)
            self.assertIsNotNone(cache.load(VIDEO_ID, now=9_099.0))
            self.assertIsNone(cache.load(VIDEO_ID, now=9_101.0))
            self.assertFalse((Path(temp_dir) / f"{VIDEO_ID}.json").exists(), "stale entries are deleted")

    def test_entry_without_expire_uses_default_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = InfoCache(Path(temp_dir), margin_seconds=0)
            cache.store(VIDEO_ID, {"id": VIDEO_ID, "formats": []}, proxy_role="direct", session_id=None, now=0.0)
            self.assertIsNotNone(cache.load(VIDEO_ID, now=DEFAULT_INFO_TTL_SECONDS - 1))
            self.assertIsNone(cache.load(VIDEO_ID, now=DEFAULT_INFO_TTL_SECONDS + 1))

    def test_corrupt_or_mismatched_entries_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = InfoCache(Path(temp_dir))
            (Path(temp_dir) / f"{VIDEO_ID}.json").write_text("{not json", encoding="utf-8")
            self.assertIsNone(cache.load(VIDEO_ID))
            (Path(temp_dir) / f"{VIDEO_ID}.json").write_text(
                json.dumps({"stored_at": 1, "info": {"id": "other_video"}}), encoding="utf-8"
            )
            self.assertIsNone(cache.load(VIDEO_ID))
            with self.assertRaises(ValueError):
                cache.store(VIDEO_ID, {"id": "another1234"}, proxy_role="metadata", session_id=None)
            with self.assertRaises(ValueError):
                cache.load("../etc/passwd")

    def test_subtitle_cues_survive_a_store_without_cues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = InfoCache(Path(temp_dir), margin_seconds=0)
            cues = [{"s": 1.0, "e": 2.0, "t": "hola"}]
            cache.store(VIDEO_ID, info_with_expiry(10**10), proxy_role="metadata", session_id="a", subtitle_cues=cues)
            cache.store(VIDEO_ID, info_with_expiry(10**10), proxy_role="download", session_id="b")
            loaded = cache.load(VIDEO_ID)
            assert loaded is not None
            self.assertEqual(loaded.subtitle_cues, cues)
            self.assertEqual(loaded.proxy_role, "download")
            cache.update_subtitle_cues(VIDEO_ID, [])
            reloaded = cache.load(VIDEO_ID)
            assert reloaded is not None
            self.assertEqual(reloaded.subtitle_cues, [])


class ClipLibraryTests(unittest.TestCase):
    def test_store_find_and_resolution_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            library = ClipLibrary(Path(temp_dir) / "clips")
            clip = Path(temp_dir) / "clip.mp4"
            clip.write_bytes(b"video")
            self.assertIsNone(library.find(VIDEO_ID, 10, 15, required_height=720))

            entry = library.store(VIDEO_ID, 10, 15, clip, source_height=480, max_height_requested=480)
            self.assertTrue(entry.path.is_file())
            self.assertEqual(entry.path.name, f"{VIDEO_ID}_10p000_15p000.mp4")
            self.assertIsNotNone(library.find(VIDEO_ID, 10, 15, required_height=480))
            self.assertIsNone(library.find(VIDEO_ID, 10, 15, required_height=720), "480p clip must not serve a 720p request")

            library.store(VIDEO_ID, 10, 15, clip, source_height=480, max_height_requested=720)
            found = library.find(VIDEO_ID, 10, 15, required_height=720)
            self.assertIsNotNone(found, "the best the video offers under a 720p cap is reusable")

            library.store(VIDEO_ID, 10, 15, clip, source_height=1080, max_height_requested=1080)
            self.assertIsNotNone(library.find(VIDEO_ID, 10, 15, required_height=720))
            self.assertIsNone(library.find(VIDEO_ID, 10, 16, required_height=720), "ranges must match exactly")

    def test_invalid_video_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ClipLibrary.key("../x", 0, 1)


if __name__ == "__main__":
    unittest.main()
