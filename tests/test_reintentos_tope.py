"""27-11 [A1]: a video that always failed was tried every round (8 times in 77 min): the end of the round dropped
`tries`, and every attempt wrote files into its folder, which counted as new material."""

import os
import time
from datetime import datetime, timedelta

from pipeline import reintentos


def test_the_wait_grows_and_five_failures_a_day_stop_it():
    watch = {"retry_now": 2, "retry_minutes": 1, "retry_hours": 6, "max_failures_per_day": 5}
    now = datetime(2026, 11, 27, 10, 0).timestamp()
    entry = None
    for n in range(1, 6):
        entry = reintentos.record(entry, "sig", "ERROR", "abc", now=now)
        assert entry["tries"] == n and entry["dayFails"] == n
    # 6 h after the last one the in-a-row wait is over, but five today: not again until tomorrow
    later = now + 6 * 3600 + 60
    assert reintentos.held(watch, entry, "sig", now=later)
    tomorrow = (datetime(2026, 11, 28, 9, 0)).timestamp()
    assert not reintentos.held(watch, entry, "sig", now=tomorrow)
    assert not reintentos.held(watch, entry, "otra", now=later)          # new materials: at once
    assert reintentos.record(entry, "sig", "ERROR", "abc", now=tomorrow)["dayFails"] == 1


def test_failures_with_new_materials_still_count_for_the_day():
    now = datetime(2026, 11, 27, 10, 0).timestamp()
    entry = reintentos.record(None, "a", "ERROR", "x", now=now)
    entry = reintentos.record(entry, "b", "ERROR", "x", now=now + 60)
    assert entry["tries"] == 1 and entry["dayFails"] == 2


def test_what_the_program_writes_is_not_new_material(tmp_path):
    import main

    folder = tmp_path / "materiales" / "v1"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("hola")
    old = time.time() - 3600
    os.utime(folder / "guion.txt", (old, old))
    before = main._materials_signature(tmp_path, "v1")
    for name in ("voz.genaipro.json", "imagen_guion.json", "voz.palabras.json", ".proceso", "voz.mp3",
                 "voz.original.mp3"):
        (folder / name).write_text("x")
    os.utime(folder / "voz.original.mp3", (old, old))                   # the voice you gave, cut here since
    assert main._materials_signature(tmp_path, "v1") == before
    (folder / "guion.txt").write_text("hola de nuevo")                   # you changed the script: new material
    assert main._materials_signature(tmp_path, "v1") > before


def test_the_end_of_the_round_no_longer_rewrites_the_queue_state():
    import inspect

    import main

    source = inspect.getsource(main.watch)
    assert "atomic_write_text(state_path, json.dumps(state" not in source       # never rewritten from a stale copy
