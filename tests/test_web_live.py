"""web.live: slow studio pages answer with their last value and are rebuilt in the background."""

import threading
import time

from pipeline import web


def _counter(delay=0.0):
    calls = []

    def make():
        time.sleep(delay)
        calls.append(1)
        return len(calls)
    return make, calls


def test_the_first_request_waits_then_it_is_served_from_memory():
    make, calls = _counter()
    assert web.live("t1", 60, 600, make) == 1
    assert web.live("t1", 60, 600, make) == 1 and len(calls) == 1


def test_an_old_answer_goes_out_at_once_and_is_rebuilt_behind():
    make, calls = _counter(0.3)
    assert web.live("t2", 0, 600, make) == 1                 # nothing yet: waits
    t0 = time.monotonic()
    assert web.live("t2", 0, 600, make) == 1                 # old: at once…
    assert time.monotonic() - t0 < 0.2
    time.sleep(0.5)
    assert web.live("t2", 60, 600, make) == 2                # …and the new one is there a moment later


def test_after_a_change_the_next_request_waits_for_the_new_value():
    make, calls = _counter(0.2)
    assert web.live("t3", 60, 600, make) == 1
    web.live_changed()
    assert web.live("t3", 60, 600, make) == 2


def test_one_rebuild_at_a_time():
    make, calls = _counter(0.3)
    web.live("t4", 0, 600, make)
    threads = [threading.Thread(target=web.live, args=("t4", 0, 600, make)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    time.sleep(0.5)
    assert len(calls) == 2


def test_a_failed_first_build_raises():
    def boom():
        raise RuntimeError("no")
    try:
        web.live("t5", 60, 600, boom)
    except RuntimeError as e:
        assert str(e) == "no"
    else:
        raise AssertionError("should raise")
