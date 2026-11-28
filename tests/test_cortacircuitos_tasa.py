"""The breaker sees what it missed: the same failure in many videos at alternating stages, any kind of exception,
one video failing again and again, a success in between, and a new round that forgot everything."""

from __future__ import annotations

import json

from pipeline import cortacircuitos
from tests.test_cortacircuitos import _stage


def _fail(root, slug, stage, detail, lines=None, **kw):
    _stage(root, slug, stage)
    return cortacircuitos.Breaker(root, **kw).failed(slug, detail, lines)    # a new breaker each round


def test_eight_videos_failing_alike_at_alternating_stages_trip_it(tmp_path):
    tail = ['  File "/srv/edit-vid3/pipeline/sourcing.py", line 300, in run',
            "SystemExit: YouTube pide confirmar que no eres un bot"]
    got = None
    for n in range(8):
        stage = "sourcing" if n % 2 else "ingest"
        got = got or _fail(tmp_path, f"v{n}", stage, "SystemExit: YouTube pide confirmar que no eres un bot", tail)
    assert got is not None and "SystemExit en pipeline/sourcing.py:300" in got[0]


def test_any_exception_by_its_kind_and_place(tmp_path):
    tail = ['  File "/srv/edit-vid3/pipeline/planner.py", line 88, in outline',
            "pydantic_core._pydantic_core.ValidationError: 1 validation error for Scene"]
    assert _fail(tmp_path, "a", "planner", tail[-1], tail) is None
    assert _fail(tmp_path, "b", "planner", tail[-1].replace("Scene", "Shot"), tail) is None
    why, videos = _fail(tmp_path, "c", "planner", tail[-1], tail)
    assert why.startswith("ValidationError en pipeline/planner.py:88") and videos == ["a", "b", "c"]


def test_one_video_failing_with_a_program_bug_again_and_again(tmp_path):
    tail = ['  File "/srv/edit-vid3/pipeline/coldopen.py", line 212, in run', "KeyError: 'x'"]
    assert _fail(tmp_path, "solo", "coldopen", "KeyError: 'x'", tail) is None
    assert _fail(tmp_path, "solo", "coldopen", "KeyError: 'x'", tail) is None
    why, videos = _fail(tmp_path, "solo", "coldopen", "KeyError: 'x'", tail)
    assert "KeyError en pipeline/coldopen.py:212" in why and videos == ["solo"]


def test_a_success_in_between_does_not_hide_a_bad_night(tmp_path):
    got = None
    for n in range(10):
        breaker = cortacircuitos.Breaker(tmp_path, same_stage=0)
        if n % 5 == 4:
            breaker.succeeded(f"dibujado{n}")             # a drawn video comes out fine now and then
            continue
        _stage(tmp_path, f"v{n}", "render")
        got = got or breaker.failed(f"v{n}", f"algo distinto {n}")
    assert got is not None and "fallaron" in got[0]


def test_a_broken_state_file_never_stops_the_queue_and_a_trip_starts_afresh(tmp_path):
    path = tmp_path / cortacircuitos.STATE
    path.parent.mkdir(parents=True)
    path.write_text('{"events": [{"t": "ayer"}, 7, {"slug": "x"}]')        # half written
    assert _fail(tmp_path, "a", "render", "nada") is None
    path.write_text(json.dumps({"events": [{"t": "x", "ok": "?"}, None]}))
    assert _fail(tmp_path, "b", "render", "nada") is None
    tail = ['  File "/srv/edit-vid3/pipeline/qa.py", line 9, in run', "NameError: name 'q' is not defined"]
    _fail(tmp_path, "c", "qa", tail[-1], tail)
    assert _fail(tmp_path, "d", "qa", tail[-1], tail) is not None
    assert _fail(tmp_path, "e", "qa", tail[-1], tail) is None              # after the pause, counted from zero


def test_network_failures_and_few_attempts_never_trip_it(tmp_path):
    for n in range(10):
        assert _fail(tmp_path, f"n{n}", "planner", "RemoteProtocolError: peer closed connection") is None
    assert _fail(tmp_path, "a", "render", "uno") is None and _fail(tmp_path, "b", "voz", "dos") is None
