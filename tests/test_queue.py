from __future__ import annotations

import os
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
                failures = main.run_queue(force=set(), until=None, review=False, root=root, check=False)
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
            (root / main.QUEUE_LOCK).write_text(f"{os.getppid()} ayer")   # a live process: another queue
            with self.assertRaises(SystemExit):
                main.run_queue(force=set(), until=None, review=False, root=root, check=False)


    def test_preflight_stops_the_queue_before_it_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materials(root, "A")
            ran = []
            with patch.object(main, "preflight", return_value=["falta la clave OPENAI_API_KEY en .env"]), \
                    patch.object(main, "run_one", side_effect=lambda slug, **k: ran.append(slug)):
                with self.assertRaises(SystemExit) as stop:
                    main.run_queue(force=set(), until=None, review=False, root=root)
            lock_left = (root / main.QUEUE_LOCK).exists()
        self.assertIn("OPENAI_API_KEY", str(stop.exception))
        self.assertEqual(ran, [])
        self.assertFalse(lock_left)


if __name__ == "__main__":
    unittest.main()


def test_the_watcher_does_not_retry_a_failed_video_until_its_files_change(tmp_path, monkeypatch):
    import json
    import os
    import time as clock

    import main

    root = tmp_path
    (root / "config.yaml").write_text("watch: {git_pull: false}\n")
    folder = root / "materiales" / "v1"
    folder.mkdir(parents=True)
    for name in ("guion.txt", "voz.mp3"):
        (folder / name).write_text("x")
    runs = []

    def fake_queue(**kwargs):
        runs.append(sorted(kwargs.get("skip") or []))
        main.LAST_RESULTS[:] = [("v1", "ERROR", 1.0, "boom")]
        return 1

    naps = []

    def nap(seconds):
        naps.append(seconds)
        if len(naps) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(main, "run_queue", fake_queue)
    monkeypatch.setattr(main.time, "sleep", nap)
    try:
        main.watch(0.01, root=root)
    except KeyboardInterrupt:
        pass
    assert runs == [[]]                                   # failed once, then left alone while unchanged
    state = json.loads((root / "out" / "_vigilar.json").read_text())
    assert state["v1"]["status"] == "ERROR"
    later = clock.time() + 5
    os.utime(folder / "guion.txt", (later, later))        # you fix the script: it is tried again
    naps.clear()
    try:
        main.watch(0.01, root=root)
    except KeyboardInterrupt:
        pass
    assert len(runs) == 2


def test_two_runs_of_one_video_never_overlap(tmp_path):
    import os

    import pytest

    from pipeline.context import RunContext

    ctx = RunContext.create("v", root=tmp_path, config={})
    lock = main._one_process(ctx)
    with lock:
        assert (ctx.work_dir / ".proceso").read_text().split()[0] == str(os.getpid())
        (ctx.work_dir / ".proceso").write_text(f"{os.getppid()} x")              # another live process holds it
        with pytest.raises(SystemExit):
            main._one_process(ctx).__enter__()
        (ctx.work_dir / ".proceso").write_text("999999 x")                       # a dead one: taken over
        with main._one_process(ctx):
            pass
    assert not (ctx.work_dir / ".proceso").exists()


def test_stale_queue_lock_is_removed(tmp_path):
    import main

    lock = tmp_path / "work" / ".cola.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("999999999 2026-10-04T20:00:00\n")
    main._clear_stale_lock(lock)
    assert not lock.exists()
    lock.write_text(f"{os.getpid()} 2026-10-04T20:00:00\n")
    main._clear_stale_lock(lock)
    assert lock.exists()


def test_a_finished_video_marked_to_redo_goes_back_to_the_queue(tmp_path):
    _materials(tmp_path, "B", done=True)
    assert main.pending_slugs(tmp_path) == []
    (tmp_path / "materiales" / "B" / main.REDO).write_text("planner\nbogus\n")
    assert main.pending_slugs(tmp_path) == ["B"]
    assert main.redo_stages(tmp_path / "materiales" / "B") == {"planner"}


def test_new_code_is_seen_even_when_someone_else_pulled_it(tmp_path):
    import subprocess

    import main

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "a")
    running = main.git_head(tmp_path)
    assert not main._git_update(tmp_path, running)          # no remote: the pull fails, nothing new
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "b")   # the studio pulled
    assert main._git_update(tmp_path, running)


def test_an_api_without_balance_says_which_one_and_is_not_a_video_failure():
    import main

    deepseek = RuntimeError("Error code: 402 - {'error': {'message': 'Insufficient Balance (request_id: x)'}}")
    assert "DeepSeek" in main.out_of_credit(deepseek)
    assert "OpenAI" in main.out_of_credit(RuntimeError("Error code: 429 - insufficient_quota"))
    assert main.out_of_credit(RuntimeError("Error code: 500 - boom")) is None
