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
