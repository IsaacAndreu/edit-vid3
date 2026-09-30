import threading
import time

from pipeline import locks


def test_turns_only_in_the_queue_and_one_at_a_time(tmp_path, monkeypatch):
    with locks.turn(tmp_path, "render"):                 # a single run never waits nor leaves files
        assert not (tmp_path / "work").exists()
    monkeypatch.setenv(locks.ENV, "1")
    order = []

    def second():
        with locks.turn(tmp_path, "analysis", "B", poll=0.05):
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
