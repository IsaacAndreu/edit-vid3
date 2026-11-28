"""A lock whose PID now belongs to another process (a reboot reuses PIDs) never blocks for ever, and a long wait
for a turn says so."""

from __future__ import annotations

import os
import time

import pytest

import main
from pipeline import locks, web

OTHER = 1          # always alive (init), and never the process that wrote these locks


def _old(path, hours):
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


def test_a_turn_held_by_a_reused_pid_is_taken_over(tmp_path):
    place = tmp_path / ".turno-red"
    place.write_text(f"{OTHER}:12345 gym4.0")              # pid alive, but it started at another time
    assert locks._take(place, "yo")
    assert place.read_text().split()[0] == locks.stamp()


def test_a_live_owner_keeps_its_turn_and_an_old_lock_without_start_time_expires(tmp_path):
    place = tmp_path / ".turno-red"
    place.write_text(f"{locks.stamp()} otro")             # really alive (this very process): kept
    assert not locks._take(place, "yo")
    place.write_text(f"{OTHER} gym4.0")                   # the old format: only the pid
    assert not locks._take(place, "yo")                   # recent: respected
    _old(place, 30)
    assert locks._take(place, "yo")                       # 30 h: no stage takes that long, it is stale


def test_the_queue_and_video_locks_see_a_reused_pid(tmp_path):
    lock = tmp_path / "work" / ".cola.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(f"{OTHER}:999 2026-11-27T03:00:00\n")
    assert web._lock_alive(lock) is False
    main._clear_stale_lock(lock)
    assert not lock.exists()
    lock.write_text("garbage")                            # unreadable: not alive either
    assert web._lock_alive(lock) is False
    from types import SimpleNamespace

    work = tmp_path / "work" / "v1"
    work.mkdir(parents=True)
    (work / ".proceso").write_text(f"{OTHER}:999 2026-11-27T03:00:00\n")
    with main._one_process(SimpleNamespace(work_dir=work)):         # taken over, no «ya se está haciendo»
        assert (work / ".proceso").read_text().split()[0] == locks.stamp()
    (work / ".proceso").write_text(f"{OTHER}:{locks.process_start(OTHER)} x\n")     # init, really it
    with pytest.raises(SystemExit):                        # the real owner, alive: refused
        with main._one_process(SimpleNamespace(work_dir=work)):
            pass


def test_a_long_wait_for_a_turn_is_told(tmp_path, monkeypatch, capsys):
    (tmp_path / "work").mkdir()
    place = tmp_path / "work" / ".turno-red"
    place.write_text(f"{locks.stamp()} gym4.0")           # a live owner that does not let go
    told = []
    monkeypatch.setattr(locks, "_tell", lambda root, text: told.append(text))
    rounds = []

    def fake_sleep(seconds):
        rounds.append(seconds)
        if len(rounds) == 4:
            place.unlink()

    monkeypatch.setattr(locks.time, "sleep", fake_sleep)
    monkeypatch.setattr(locks, "warn_minutes", lambda root: 90)
    got = locks._acquire(tmp_path, "red", "yo", poll=3600)
    assert got == place and len(told) == 1               # once, not every round
    assert "2 h" in told[0] and "gym4.0" in told[0]
