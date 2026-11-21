"""A video cut by systemctl restart is «interrumpido», not «ERROR»: it goes back to the queue as soon as the watcher
starts again, instead of waiting watch.retry_hours (newgym3-haiku: 6 h for a restart after a config change)."""

import inspect

import main


def test_a_restart_is_told_apart_from_a_failure():
    assert main.was_stopped(["[6/16] judge…", "Parado por la señal SIGTERM: alguien o algo lo paró (systemctl stop, kill, "
                                               "reinicio)"])
    assert not main.was_stopped(["Error: 2 validation errors for Timeline"])
    assert not main.was_stopped([])


def test_interrupted_is_not_a_failure_for_the_watcher():
    assert "interrumpido" in main.WAITING            # on_result and the round's end skip it: no 6 h wait
    source = inspect.getsource(main)
    assert '"interrumpido" if not cut and was_stopped(list(tail)) else "ERROR"' in source
