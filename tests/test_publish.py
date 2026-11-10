from __future__ import annotations

import unittest

from pipeline.publish import chapter_lines, compact_credits
from pipeline.schemas import Timeline


def _timeline(chapters: list[tuple[int, str]]) -> Timeline:
    shots, cursor = [], 0
    for frame, title in chapters:
        if frame > cursor:
            shots.append({"id": f"s{len(shots):03d}", "type": "datacard", "from": cursor, "durationInFrames": frame - cursor, "text": "t"})
        shots.append({"id": f"s{len(shots):03d}", "type": "chapter", "from": frame, "durationInFrames": 60, "text": "t",
                      "chapterTitle": title, "media": {"src": "a.jpg", "kind": "image", "source": "generated"}})
        cursor = frame + 60
    shots.append({"id": "s999", "type": "datacard", "from": cursor, "durationInFrames": 600, "text": "t"})
    return Timeline.model_validate({"slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080,
                                    "durationInFrames": cursor + 600, "shots": shots, "groups": [],
                                    "audio": {"voice": "v"}})


class PublishTests(unittest.TestCase):
    def test_chapters_start_at_zero_and_need_three(self) -> None:
        self.assertEqual(chapter_lines(_timeline([(3000, "TOKIO 2020"), (9000, "PARÍS 2024")])),
                         ["0:00 Intro", "1:40 Tokio 2020", "5:00 París 2024"])
        self.assertEqual(chapter_lines(_timeline([(3000, "TOKIO 2020")])), [])        # only 2 → YouTube ignores them

    def test_compact_credits_group_names_and_fit_the_budget(self) -> None:
        rows = [{"source": "youtube", "credit": "Fuente: Olympic Games"}, {"source": "youtube", "credit": "Fuente: Olympic Games"},
                {"source": "web", "credit": "Fuente: rappler.com"}, {"source": "generated", "credit": None}]
        text = compact_credits(rows, 5000)
        self.assertIn("Vídeos: Olympic Games\n", text)
        self.assertIn("Fotografías: rappler.com", text)
        many = [{"source": "youtube", "credit": f"Fuente: Canal {i}"} for i in range(500)]
        self.assertLessEqual(len(compact_credits(many, 1000)), 1000)


if __name__ == "__main__":
    unittest.main()
