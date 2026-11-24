"""A failed video is retried at once (the owner), and only waits hours when it keeps failing the same way."""

from pipeline import reintentos


def test_the_first_failures_wait_a_minute_then_hours():
    watch = {}
    first = {"sig": "a", "at": 1000.0, "tries": 1}
    assert reintentos.wait_seconds(watch, first) == 60
    assert reintentos.held(watch, first, "a", now=1030) and not reintentos.held(watch, first, "a", now=1061)
    third = {**first, "tries": 3}
    assert reintentos.wait_seconds(watch, third) == 6 * 3600 and reintentos.held(watch, third, "a", now=1000 + 3600)
    assert not reintentos.held(watch, third, "otros-materiales", now=1001)     # changed files: at once
    assert reintentos.wait_seconds({}, {"sig": "a", "at": 1}) == 60             # an old entry without tries


def test_tries_count_in_a_row_for_the_same_materials():
    assert reintentos.failed_again(None, "a") == 1
    assert reintentos.failed_again({"sig": "a", "tries": 2}, "a") == 3
    assert reintentos.failed_again({"sig": "a", "tries": 2}, "b") == 1          # new materials start over
    assert reintentos.wait_seconds({"retry_now": 0, "retry_hours": 2}, {"tries": 1}) == 7200
