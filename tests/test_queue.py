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


def test_the_pilot_waits_for_api_quota_alone_and_the_queue_goes_on(tmp_path):
    import time as clock

    from pipeline.budget import ApiSearchesShort

    for slug in ("A", "PILOT", "C"):
        _materials(tmp_path, slug)
    done = []

    def fake_run(slug, **kwargs):
        if slug == "PILOT":
            raise ApiSearchesShort("faltan búsquedas de la API", clock.time() + 3600)
        done.append(slug)

    with patch.object(main, "run_one", side_effect=fake_run), patch.object(main, "notify", lambda *a, **k: None):
        failures = main.run_queue(force=set(), until=None, review=False, root=tmp_path, check=False)
    assert done == ["A", "C"] and failures == 0                       # not a failure, and not the end of the queue
    assert "| PILOT | espera cuota |" in (tmp_path / main.QUEUE_REPORT).read_text()
    assert "PILOT" not in main.pending_slugs(tmp_path)                # until the reset
    (tmp_path / "materiales" / "PILOT" / main.QUOTA_WAIT).write_text(f"{clock.time() - 1:.0f}")
    assert "PILOT" in main.pending_slugs(tmp_path)                    # reset passed: back in the queue
    assert not (tmp_path / "materiales" / "PILOT" / main.QUOTA_WAIT).exists()


def test_a_video_waiting_for_the_proxy_says_why_in_the_studio(tmp_path):
    import time as clock

    from pipeline import web
    from pipeline.budget import ProxyDown

    (tmp_path / "config.yaml").write_text("{}\n")
    _materials(tmp_path, "A")
    main.wait_for_quota(tmp_path, "A", ProxyDown("El proxy no responde"))
    folder = tmp_path / "materiales" / "A"
    assert main.quota_wait(folder) and "A" not in main.pending_slugs(tmp_path)
    summary = web.video_summary(tmp_path, folder, {})
    assert summary["quotaWait"].startswith("el proxy no responde · hasta las")
    (folder / main.QUOTA_WAIT).write_text(f"{clock.time() - 1:.0f}\nel proxy no responde")
    assert "A" in main.pending_slugs(tmp_path)


def test_a_video_waiting_for_the_api_quota_is_in_the_queue_not_an_error(tmp_path):
    import json as _json

    from pipeline import web
    from pipeline.budget import ApiSearchesShort

    (tmp_path / "config.yaml").write_text("{}\n")
    _materials(tmp_path, "A")
    (tmp_path / "materiales" / "A" / "voz.mp3").write_bytes(b"0")
    (tmp_path / "work" / "A").mkdir(parents=True)
    (tmp_path / "work" / "A" / "diag.json").write_text(_json.dumps({"error": "ApiSearchesShort: sin búsquedas"}))
    main.wait_for_quota(tmp_path, "A", ApiSearchesShort("La API de YouTube no tiene más búsquedas hoy", 9e9))
    summary = web.video_summary(tmp_path, tmp_path / "materiales" / "A", {})
    assert summary["status"] == "en cola" and summary["quotaWait"] and not summary["lastError"]


def test_with_no_api_searches_left_a_video_that_must_search_does_not_even_start(tmp_path, monkeypatch):
    from unittest.mock import patch

    import pipeline.ytapi as ytapi

    (tmp_path / "config.yaml").write_text("{}\n")
    for slug in ("NEW", "SEARCHED"):
        _materials(tmp_path, slug)
    (tmp_path / "work" / "SEARCHED" / "candidates").mkdir(parents=True)
    (tmp_path / "work" / "SEARCHED" / "candidates" / "_summary.json").write_text("{}")

    class Dry:
        keys = ["k"]

        def __init__(self, ctx):
            pass

        def quota(self):
            return {"searchesLeft": 0}

    monkeypatch.setattr(ytapi, "YouTubeAPI", Dry)
    ran = []
    with patch.object(main, "run_one", side_effect=lambda slug, **k: ran.append(slug)), \
            patch.object(main, "notify", lambda *a, **k: None):
        failures = main.run_queue(force=set(), until=None, review=False, root=tmp_path, check=False)
    assert ran == ["SEARCHED"] and failures == 0                    # the one that searched already goes on
    assert main.quota_wait(tmp_path / "materiales" / "NEW") and "NEW" not in main.pending_slugs(tmp_path)


def test_the_queue_makes_the_priority_channels_first_in_their_order(tmp_path):
    import json as _json
    import os

    from pipeline import web

    (tmp_path / "config.yaml").write_text("canal: aviacion\n")
    (tmp_path / "canales").mkdir()
    for c in ("aviacion", "patinaje", "atletismo", "robots"):
        (tmp_path / "canales" / f"{c}.yaml").write_text("a: 1\n")
    for n, (slug, canal) in enumerate([("avion1", None), ("atlet1", "atletismo"), ("pati1", "patinaje"),
                                       ("robot1", "robots"), ("avion2", None)]):
        _materials(tmp_path, slug)
        if canal:
            (tmp_path / "materiales" / slug / "config.yaml").write_text(f"canal: {canal}\n")
        os.utime(tmp_path / "materiales" / slug, (1000 + n, 1000 + n))           # oldest first, as before
    assert main.pending_slugs(tmp_path) == ["avion1", "atlet1", "pati1", "robot1", "avion2"]
    web.settings(tmp_path, {"channel_priority": ["patinaje", "atletismo", "no-existe", "patinaje"]})
    assert _json.loads((tmp_path / "out" / "_ajustes.json").read_text())["channel_priority"] == ["patinaje", "atletismo"]
    assert main.pending_slugs(tmp_path) == ["pati1", "atlet1", "avion1", "robot1", "avion2"]
