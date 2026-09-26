from __future__ import annotations

import unittest
from unittest.mock import patch

from pipeline.segment import segment_script


class AvatarDisabledTests(unittest.TestCase):
    def test_avatar_scene_from_llm_is_normalized_to_narrative_template(self) -> None:
        transcript = {
            "text": "Inicio dato contexto cierre",
            "duration_seconds": 2.0,
            "words": [
                {"word": "Inicio", "start": 0.0, "end": 0.4},
                {"word": "dato", "start": 0.5, "end": 0.9},
                {"word": "contexto", "start": 1.0, "end": 1.4},
                {"word": "cierre", "start": 1.5, "end": 1.9},
            ],
            "segments": [],
        }
        raw_scenes = [
            {"start_word_index": 0, "end_word_index": 0, "sceneType": "hook", "text": "Inicio"},
            {
                "start_word_index": 1,
                "end_word_index": 3,
                "sceneType": "avatar",
                "text": "Dato contexto cierre",
                "keywords": ["news footage"],
            },
        ]

        with patch("pipeline.segment.segment_with_deepseek", return_value=raw_scenes):
            scenes = segment_script("Guion de prueba", transcript, settings=None)  # type: ignore[arg-type]

        self.assertEqual(scenes[1]["sceneType"], "narrative")
        self.assertEqual(scenes[1]["templateName"], "kenburns-image")


if __name__ == "__main__":
    unittest.main()
