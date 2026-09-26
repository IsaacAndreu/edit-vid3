from __future__ import annotations

import unittest

from pipeline.qa import category, credits_text, mmss


def _row(shot_id: str, start: float, source: str, **extra) -> dict:
    return {"shotId": shot_id, "start": start, "source": source, "credit": f"Fuente: {extra.get('channel', 'X')}", **extra}


class CreditsTests(unittest.TestCase):
    def test_groups_by_source_with_times_and_skips_generated(self) -> None:
        rows = [
            _row("s000", 3, "youtube", channel="Canal A", title="Vídeo", url="https://youtu.be/a"),
            _row("s001", 65, "youtube", channel="Canal A", title="Vídeo", url="https://youtu.be/a"),
            _row("s002", 70, "wikimedia", url="https://commons/x", attribution="Autor / CC BY-SA 4.0"),
            _row("s003", 75, "generated"),
            {"shotId": "s004", "start": 80, "source": None},  # data panel, no media
        ]
        text = credits_text(rows)
        self.assertIn("- Canal A — «Vídeo»: https://youtu.be/a (0:03, 1:05)", text)
        self.assertIn("- Autor / CC BY-SA 4.0 (1:10)", text)
        self.assertIn("1 imagen(es) generada(s) con IA.", text)
        self.assertEqual(text.count("Canal A"), 1)

    def test_categories_and_time_format(self) -> None:
        self.assertEqual(category("youtube"), "terceros (YouTube)")
        self.assertEqual(category("openverse"), "imágenes libres")
        self.assertEqual(mmss(125.9), "2:05")


if __name__ == "__main__":
    unittest.main()
