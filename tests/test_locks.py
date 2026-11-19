import threading
import time

from pipeline import locks


def test_turns_only_in_the_queue_and_one_at_a_time(tmp_path, monkeypatch):
    with locks.turn(tmp_path, "render"):                 # a single run never waits nor leaves files
        assert not (tmp_path / "work").exists()
    monkeypatch.setenv(locks.ENV, "1")
    order = []

    def second():
        with locks.turn(tmp_path, "fallback", "B", poll=0.05):
            order.append("B")

    with locks.turn(tmp_path, "render", "A"):
        assert (tmp_path / "work" / ".turno-cpu").is_file()
        worker = threading.Thread(target=second)
        worker.start()
        time.sleep(0.2)
        order.append("A")
    worker.join(2)
    assert order == ["A", "B"] and not (tmp_path / "work" / ".turno-cpu").exists()
    with locks.turn(tmp_path, "judge"):                  # stages outside the groups run freely
        pass


def test_a_dead_owner_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv(locks.ENV, "1")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / ".turno-red").write_text("999999 viejo")
    with locks.turn(tmp_path, "ingest", "nuevo", poll=0.05):
        assert "nuevo" in (tmp_path / "work" / ".turno-red").read_text()


def test_the_fill_in_never_overlaps_a_render():
    from pipeline.locks import GROUPS

    assert GROUPS["fallback"] == GROUPS["render"] == "cpu" and GROUPS["sourcing"] == "red"
    assert "analysis" not in GROUPS          # it mostly waits for YouTube: no CPU place held meanwhile


def test_a_bigger_machine_gives_a_group_more_places(tmp_path, monkeypatch):
    import threading
    import time

    monkeypatch.setenv(locks.ENV, "1")
    (tmp_path / "config.yaml").write_text("queue:\n  slots:\n    red: 2\n")
    assert locks.slots(tmp_path, "red") == 2 and locks.slots(tmp_path, "cpu") == 1
    inside, most, done = [], [0], []

    def video(name):
        with locks.turn(tmp_path, "sourcing", name, poll=0.02):
            inside.append(name)
            most[0] = max(most[0], len(inside))
            deadline = time.monotonic() + 2           # hold the place until a second video is in (never a race)
            while len(inside) < 2 and time.monotonic() < deadline and len(inside) + len(done) < 3:
                time.sleep(0.01)
            most[0] = max(most[0], len(inside))
            time.sleep(0.05)
            inside.remove(name)
            done.append(name)

    workers = [threading.Thread(target=video, args=(f"v{i}",)) for i in range(3)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(3)
    assert most[0] == 2 and not list((tmp_path / "work").glob(".turno-*"))


def test_align_has_a_turn_of_its_own(tmp_path, monkeypatch):
    """5.5: Whisper no longer waits behind renders, and two alignments still wait for each other."""

    monkeypatch.setenv(locks.ENV, "1")
    with locks.turn(tmp_path, "render", "R"):
        with locks.turn(tmp_path, "align", "A", poll=0.05):           # beside the render, at once
            assert (tmp_path / "work" / ".turno-align").is_file()
            order = []

            def second():
                with locks.turn(tmp_path, "align", "B", poll=0.05):
                    order.append("B")

            worker = threading.Thread(target=second)
            worker.start()
            time.sleep(0.2)
            order.append("A")
    worker.join(2)
    assert order == ["A", "B"]


def test_whisper_uses_half_the_cores_unless_told(monkeypatch):
    from pipeline import whisper_local

    monkeypatch.setattr("os.cpu_count", lambda: 8)
    assert whisper_local.cpu_threads() == 4 and whisper_local.cpu_threads(6) == 6
    monkeypatch.setattr("os.cpu_count", lambda: 2)
    assert whisper_local.cpu_threads() == 2


def test_whisper_threads_are_a_speed_knob():
    from pipeline.runner import SPEED_KEYS

    assert "cpu_threads" in SPEED_KEYS                                  # changing it never re-runs align


def test_the_network_turn_is_lent_during_local_work_only_when_asked(tmp_path, monkeypatch):
    """3.7: queue.release_red_turn (off by default) gives the network turn back while sourcing only computes CLIP,
    and takes it again afterwards."""

    monkeypatch.setenv(locks.ENV, "1")
    place = tmp_path / "work" / ".turno-red"
    monkeypatch.setattr(locks, "release_red_turn", lambda root: False)
    with locks.turn(tmp_path, "sourcing", "A"):
        with locks.lend(tmp_path, "sourcing"):
            assert place.is_file()                                   # off: kept, as always
    monkeypatch.setattr(locks, "release_red_turn", lambda root: True)
    with locks.turn(tmp_path, "sourcing", "A", poll=0.05):
        with locks.lend(tmp_path, "sourcing"):
            assert not place.exists()                                # another video may search now
            with locks.turn(tmp_path, "ingest", "B", poll=0.05):     # …and does
                assert "B" in place.read_text()
        assert "A" in place.read_text()                              # taken back before going on
    assert not place.exists()
    with locks.lend(tmp_path, "render"):                             # not the network turn: nothing to lend
        pass


def test_release_red_turn_is_off_by_default(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    assert locks.release_red_turn(tmp_path) is False
