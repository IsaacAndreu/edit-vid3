import threading
import time

import main


def test_footage_videos_never_run_two_at_once_and_drawn_ones_take_the_other_line(monkeypatch, tmp_path):
    nap = time.sleep
    drawn = {"sim1", "sim2"}
    running: set[str] = set()
    most_footage = [0]
    together = []
    guard = threading.Lock()

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.slug = args[args.index("--slug") + 1]
            with guard:
                running.add(self.slug)
                footage = [s for s in running if s not in drawn]
                most_footage[0] = max(most_footage[0], len(footage))
                together.append(frozenset(running))
            self.stdout = iter(())

        def wait(self):
            nap(0.3)
            with guard:
                running.discard(self.slug)
            return 0

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: slug in drawn)
    monkeypatch.setattr(main, "needs_youtube", lambda root, slug: True)
    monkeypatch.setattr(main, "footage_at_once", lambda root: 1)
    monkeypatch.setattr(main, "waits_for_youtube", lambda root, slug: False)
    monkeypatch.setattr(main, "on_hold", lambda root, slug: False)
    monkeypatch.setattr(main, "_write_report", lambda root, results: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.05)))

    results = main.run_parallel(["foot1", "foot2", "sim1", "foot3", "sim2"], 2, force=set(), until=None,
                                review=False, root=tmp_path)
    assert sorted(r[0] for r in results) == ["foot1", "foot2", "foot3", "sim1", "sim2"]
    assert most_footage[0] == 1                                   # never two third-party videos at once
    assert any("sim1" in s and len(s) == 2 for s in together)     # a simulation ran beside a footage video


def test_a_free_line_takes_what_becomes_pending_and_shorts_have_a_line_of_their_own(monkeypatch, tmp_path):
    nap = time.sleep
    drawn = {"sim1", "sim1-short1", "sim2-short1"}
    shorts = {"sim1-short1", "sim2-short1"}
    running: set[str] = set()
    together = []
    guard = threading.Lock()
    lengths = {"foot1": 1.2}

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.slug = args[args.index("--slug") + 1]
            with guard:
                running.add(self.slug)
                together.append(frozenset(running))
            self.stdout = iter(())

        def wait(self):
            nap(lengths.get(self.slug, 0.3))
            with guard:
                running.discard(self.slug)
            return 0

    later = iter([[], ["sim1", "sim1-short1", "sim2-short1"]])
    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: slug in drawn)
    monkeypatch.setattr(main, "needs_youtube", lambda root, slug: True)
    monkeypatch.setattr(main, "is_short_video", lambda root, slug: slug in shorts)
    monkeypatch.setattr(main, "footage_at_once", lambda root: 1)
    monkeypatch.setattr(main, "shorts_at_once", lambda root: 1)
    monkeypatch.setattr(main, "REFILL_EVERY", 0)
    monkeypatch.setattr(main, "waits_for_youtube", lambda root, slug: False)
    monkeypatch.setattr(main, "on_hold", lambda root, slug: False)
    monkeypatch.setattr(main, "_write_report", lambda root, results: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.05)))

    # the round starts with one third-party video only; the sim and two Shorts become pending while it runs
    results = main.run_parallel(["foot1"], 2, force=set(), until=None, review=False, root=tmp_path,
                                refill=lambda: next(later, []))
    assert sorted(r[0] for r in results) == ["foot1", "sim1", "sim1-short1", "sim2-short1"]
    assert any({"foot1", "sim1"} <= s for s in together)               # the sim did not wait for the round
    assert any(len(s) == 3 for s in together)                          # a Short on its own line beside the other two


def test_a_dub_or_a_footage_video_with_its_clips_ready_does_not_take_the_footage_line(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: False)
    monkeypatch.setattr(main, "needs_youtube", lambda root, slug: slug != "foot1-de")
    assert main.is_light(tmp_path, "foot1-de") and not main.is_light(tmp_path, "foot2")


def test_retry_in_the_studio_puts_a_video_that_failed_in_this_round_back_in(monkeypatch, tmp_path):
    nap = time.sleep
    runs = []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.slug = args[args.index("--slug") + 1]
            runs.append(self.slug)
            self.stdout = iter(())

        def wait(self):
            nap(0.2)
            if self.slug == "sim1" and runs.count("sim1") == 1:
                from pipeline.web import ask_retry
                ask_retry(tmp_path, "sim1")          # failed; «Reintentar» pressed right after (a later mtime)
                return 1
            return 0

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: True)
    monkeypatch.setattr(main, "is_short_video", lambda root, slug: False)
    monkeypatch.setattr(main, "shorts_at_once", lambda root: 0)
    monkeypatch.setattr(main, "REFILL_EVERY", 0)
    monkeypatch.setattr(main, "waits_for_youtube", lambda root, slug: False)
    monkeypatch.setattr(main, "on_hold", lambda root, slug: False)
    monkeypatch.setattr(main, "_write_report", lambda root, results: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.05)))
    real_time = main.time.time
    monkeypatch.setattr(main.time, "time", lambda: real_time() - 5)    # the failure is noted before the click

    results = main.run_parallel(["sim1", "foot1"], 2, force=set(), until=None, review=False, root=tmp_path,
                                refill=lambda: [])
    assert runs.count("sim1") == 2 and ("sim1", "OK") in [(r[0], r[1]) for r in results]


def test_hold_and_the_queue_look_at_the_same_folder_when_a_flat_one_only_groups(tmp_path):
    from pipeline import web
    from pipeline.context import find_video

    real = tmp_path / "materiales" / "atleti-pt" / "atleti10-pt"
    real.mkdir(parents=True)
    (real / "guion.txt").write_text("hola", "utf-8")
    stray = tmp_path / "materiales" / "atleti10-pt" / "clips"      # a leftover folder with the video's name
    stray.mkdir(parents=True)
    (stray.parent / main.HOLD).write_text("x", "utf-8")
    assert find_video(tmp_path, "atleti10-pt") == real
    assert not main.on_hold(tmp_path, "atleti10-pt")
    web.hold(tmp_path, "atleti10-pt", True)
    assert (real / main.HOLD).is_file() and main.on_hold(tmp_path, "atleti10-pt")


def test_a_copy_put_away_in_hechos_does_not_hold_the_real_video(tmp_path):
    from pipeline.context import find_video

    for group in ("_hechos", "atleti-pt"):
        folder = tmp_path / "materiales" / group / "atleti10-pt"
        folder.mkdir(parents=True)
        (folder / "guion.txt").write_text("hola", "utf-8")
    (tmp_path / "materiales" / "_hechos" / "atleti10-pt" / main.HOLD).write_text("x", "utf-8")
    assert find_video(tmp_path, "atleti10-pt") == tmp_path / "materiales" / "atleti-pt" / "atleti10-pt"
    assert not main.on_hold(tmp_path, "atleti10-pt")


def test_a_new_video_or_its_uploaded_voice_wakes_the_watcher(tmp_path):
    from pipeline import web

    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "crimen.yaml").write_text("format: historia\n")
    wake = tmp_path / main.WAKE
    web.create_video(tmp_path, {"name": "pazos", "channel": "crimen", "script": "Hola. " * 60})
    assert wake.is_file()
    wake.unlink()
    web.save_voice(tmp_path, "pazos", b"ID3" + b"\0" * 20_000)
    assert wake.is_file()


def test_a_video_whose_voice_is_still_being_made_does_not_take_a_line(monkeypatch, tmp_path):
    """17-11, 19:22: gta2 and gym3 waited for their voice on two of the three footage lines; newgym1/2 sat behind."""

    nap = time.sleep
    voiced = {"newgym1": True, "newgym2": True, "gta2": False, "gym3": False}
    order: list[str] = []
    guard = threading.Lock()

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.slug = args[args.index("--slug") + 1]
            with guard:
                order.append(self.slug)
            self.stdout = iter(())

        def wait(self):
            nap(0.2)
            with guard:
                if self.slug == "newgym2":           # meanwhile the voice thread finishes their voices
                    voiced["gta2"] = voiced["gym3"] = True
            return 0

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: False)
    monkeypatch.setattr(main, "needs_youtube", lambda root, slug: True)
    monkeypatch.setattr(main, "footage_at_once", lambda root: 2)
    monkeypatch.setattr(main, "waits_for_youtube", lambda root, slug: False)
    monkeypatch.setattr(main, "on_hold", lambda root, slug: False)
    monkeypatch.setattr(main, "voice_in_background", lambda root, slug, folders=None: not voiced[slug])
    monkeypatch.setattr(main, "_write_report", lambda root, results: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.05)))

    results = main.run_parallel(["gta2", "gym3", "newgym1", "newgym2"], 2, force=set(), until=None,
                                review=False, root=tmp_path)
    assert sorted(r[0] for r in results) == ["gta2", "gym3", "newgym1", "newgym2"]
    assert set(order[:2]) == {"newgym1", "newgym2"}          # the ones ready went first; the others once voiced


def test_voice_in_background_looks_at_the_lock(tmp_path):
    import os

    folder = tmp_path / "materiales" / "v1"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("Hola.")
    assert not main.voice_in_background(tmp_path, "v1")
    from pipeline import tts

    (folder / tts.LOCK).write_text(f"{os.getpid()} x")
    assert main.voice_in_background(tmp_path, "v1")
    (folder / "voz.mp3").write_bytes(b"x")
    assert not main.voice_in_background(tmp_path, "v1")


def test_a_free_line_goes_to_the_person_with_fewer_videos_running(monkeypatch, tmp_path):
    """17-11: antonio's videos came in during the round and queued behind three of yours."""

    nap = time.sleep
    order: list[str] = []
    guard = threading.Lock()

    class FakeProcess:
        def __init__(self, args, **kwargs):
            with guard:
                order.append(args[args.index("--slug") + 1])
            self.stdout = iter(())

        def wait(self):
            nap(0.2)
            return 0

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: False)
    monkeypatch.setattr(main, "needs_youtube", lambda root, slug: True)
    monkeypatch.setattr(main, "footage_at_once", lambda root: 2)
    monkeypatch.setattr(main, "waits_for_youtube", lambda root, slug: False)
    monkeypatch.setattr(main, "on_hold", lambda root, slug: False)
    monkeypatch.setattr(main, "voice_in_background", lambda root, slug, folders=None: False)
    monkeypatch.setattr(main, "_write_report", lambda root, results: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.05)))
    monkeypatch.setattr("pipeline.budget.owner_of_work", lambda root, slug: "antonio" if slug.startswith("gta") else "")

    main.run_parallel(["mio1", "mio2", "mio3", "gtamapa"], 2, force=set(), until=None, review=False, root=tmp_path)
    assert "gtamapa" in order[:2]                  # not last: the second line went to the partner


def test_the_same_bug_in_two_videos_pauses_the_queue_and_says_so(monkeypatch, tmp_path):
    """17-11: a NameError stopped every footage video, one after another, for a whole night."""

    nap = time.sleep
    started: list[str] = []
    told: list[str] = []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.slug = args[args.index("--slug") + 1]
            started.append(self.slug)
            self.stdout = iter(["Traceback (most recent call last):\n", "NameError: name 'official' is not defined\n"])

        def wait(self):
            nap(0.05)
            return 1

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: False)
    monkeypatch.setattr(main, "needs_youtube", lambda root, slug: True)
    monkeypatch.setattr(main, "footage_at_once", lambda root: 1)
    monkeypatch.setattr(main, "waits_for_youtube", lambda root, slug: False)
    monkeypatch.setattr(main, "on_hold", lambda root, slug: False)
    monkeypatch.setattr(main, "voice_in_background", lambda root, slug, folders=None: False)
    monkeypatch.setattr(main, "_write_report", lambda root, results: None)
    monkeypatch.setattr(main, "notify", lambda root, text: told.append(text))
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.02)))

    main.run_parallel(["v1", "v2", "v3", "v4", "v5"], 1, force=set(), until=None, review=False, root=tmp_path)
    assert started == ["v1", "v2"]                                   # the third never starts
    assert (tmp_path / "out" / "_pausa").is_file() and "NameError" in told[0] and "v1, v2" in told[0]


def test_a_video_error_is_not_a_bug():
    assert main.code_bug("YouTube rechazó las descargas") is None
    assert main.code_bug("AttributeError: 'NoneType' object has no attribute 'x'")
