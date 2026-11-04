from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.config import ConfigError, load_settings


REQUIRED = "LLM_API_KEY=k\nPEXELS_API_KEY=p\nOPENAI_API_KEY=o\n"


def write_env(directory: str, extra: str = "") -> Path:
    path = Path(directory) / ".env"
    path.write_text(REQUIRED + extra, encoding="utf-8")
    return path


class ProxySettingsTests(unittest.TestCase):
    def test_proxies_are_optional_and_default_to_direct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            settings = load_settings(write_env(temp_dir))
        self.assertIsNone(settings.youtube_proxy)
        self.assertIsNone(settings.youtube_metadata_proxy)
        self.assertEqual(settings.youtube_cache_dir, settings.project_root / ".cache")
        self.assertEqual(settings.youtube_max_height, 720)

    def test_proxies_and_cache_settings_are_read_from_env_file(self) -> None:
        extra = (
            "YOUTUBE_PROXY=http://user:secret@res.example:8000\n"
            "YOUTUBE_METADATA_PROXY=http://meta:w@dc.example:9000\n"
            "YOUTUBE_CACHE_DIR=/var/cache/edit\n"
            "YOUTUBE_MAX_HEIGHT=480\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            settings = load_settings(write_env(temp_dir, extra))
        self.assertEqual(settings.youtube_proxy, "http://user:secret@res.example:8000")
        self.assertEqual(settings.youtube_metadata_proxy, "http://meta:w@dc.example:9000")
        self.assertEqual(settings.youtube_cache_dir, Path("/var/cache/edit"))
        self.assertEqual(settings.youtube_max_height, 480)

    def test_invalid_max_height_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                load_settings(write_env(temp_dir, "YOUTUBE_MAX_HEIGHT=abc\n"))
            with self.assertRaises(ConfigError):
                load_settings(write_env(temp_dir, "YOUTUBE_MAX_HEIGHT=100\n"))


if __name__ == "__main__":
    unittest.main()
