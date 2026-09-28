from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


def _materials(root: Path, slug: str, *, done: bool = False, voice: bool = True) -> None:
    folder = root / "materiales" / slug
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("hola")
    if voice:
        (folder / "voz.mp3").write_bytes(b"x")
    if done:
        (root / "out" / slug).mkdir(parents=True)
        (root / "out" / slug / "video-final.mp4").write_bytes(b"x")


class QueueTests(unittest.TestCase):
    def test_pending_are_ready_videos_without_a_final_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materials(root, "A")
            _materials(root, "B", done=True)
            _materials(root, "C", voice=False)       # no voice yet → not ready
            _materials(root, "D")
            self.assertEqual(main.pending_slugs(root), ["A", "D"])

    def test_one_failure_does_not_stop_the_night(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for slug in ("A", "B", "C"):
                _materials(root, slug)
            done = []

            def fake_run(slug, **kwargs):
                if slug == "B":
                    raise SystemExit("YouTube pide confirmar que no eres un bot")
                done.append(slug)

            with patch.object(main, "run_one", side_effect=fake_run):
                failures = main.run_queue(force=set(), until=None, review=False, root=root)
            report = (root / main.QUEUE_REPORT).read_text()
            lock_left = (root / main.QUEUE_LOCK).exists()
        self.assertEqual((failures, done), (1, ["A", "C"]))
        self.assertIn("| B | ERROR |", report)
        self.assertIn("| C | OK |", report)
        self.assertFalse(lock_left)

    def test_a_second_queue_refuses_to_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "work").mkdir()
            (root / main.QUEUE_LOCK).write_text("123 ayer")
            with self.assertRaises(SystemExit):
                main.run_queue(force=set(), until=None, review=False, root=root)


if __name__ == "__main__":
    unittest.main()
