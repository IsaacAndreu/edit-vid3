"""Fase 2.2: the circuit breaker in both queue modes — the same bug by type and file:line, N failures in a row at one
stage, and (parallel) an API without balance or the spend cap stop new videos instead of failing them one by one."""

from __future__ import annotations

import json
import time

import main
from pipeline import cortacircuitos


def _stage(root, slug, stage):
    folder = root / "work" / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "current.json").write_text(json.dumps({"stage": stage, "ended": "x"}))


def test_the_same_bug_is_the_same_type_and_line_whatever_the_values(tmp_path):
    breaker = cortacircuitos.Breaker(tmp_path, same_stage=0)
    tail = ['  File "/srv/edit-vid3/pipeline/coldopen.py", line 212, in run', "KeyError: 'abc123'"]
    assert breaker.failed("v1", "KeyError: 'abc123'", tail) is None
    why, videos = breaker.failed("v2", "KeyError: 'zzz999'", [tail[0], "KeyError: 'zzz999'"])
    assert why == "KeyError en pipeline/coldopen.py:212" and videos == ["v1", "v2"]
    assert cortacircuitos.bug_key("YouTube rechazó las descargas") is None


def test_an_exception_object_gives_its_own_frame():
    def boom():
        return {}["x"]

    try:
        boom()
    except KeyError as error:
        key = cortacircuitos.bug_key(str(error), error=error)
    assert key == "KeyError en 'x'"                       # no frame of pipeline/ or main.py: its text instead


def test_failures_in_a_row_at_one_stage(tmp_path):
    breaker = cortacircuitos.Breaker(tmp_path, same_stage=3)
    for slug in ("a", "b"):
        _stage(tmp_path, slug, "sourcing")
        assert breaker.failed(slug, "ProxyDown") is None
    breaker.succeeded()                                   # a success in between: the count starts again
    for slug in ("c", "d"):
        _stage(tmp_path, slug, "sourcing")
        assert breaker.failed(slug, "ProxyDown") is None
    _stage(tmp_path, "e", "sourcing")
    why, videos = breaker.failed("e", "ProxyDown")
    assert "etapa sourcing" in why and videos == ["c", "d", "e"]


def test_the_sequential_queue_pauses_on_the_same_bug(monkeypatch, tmp_path):
    ran, told = [], []

    def run_one(slug, **kw):
        ran.append(slug)
        raise NameError("name 'official' is not defined")

    monkeypatch.setattr(main, "pending_slugs", lambda root: ["v1", "v2", "v3"])
    monkeypatch.setattr(main, "parallel_videos", lambda root: 1)
    monkeypatch.setattr(main, "run_one", run_one)
    monkeypatch.setattr(main, "waits_for_youtube", lambda root, slug: False)
    monkeypatch.setattr(main, "on_hold", lambda root, slug: False)
    monkeypatch.setattr(main, "api_dry", lambda root, slug: None)
    monkeypatch.setattr(main, "_write_report", lambda root, results: None)
    monkeypatch.setattr(main, "notify", lambda root, text: told.append(text))
    from pipeline import dub

    monkeypatch.setattr(dub, "pending", lambda root: [])
    main.run_queue(force=set(), until=None, review=False, root=tmp_path, check=False)
    assert ran == ["v1", "v2"] and (tmp_path / "out" / "_pausa").is_file()
    assert any("NameError en" in t for t in told)


def test_the_parallel_queue_stops_on_an_api_without_balance(monkeypatch, tmp_path):
    nap = time.sleep
    started, told = [], []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            started.append(args[args.index("--slug") + 1])
            self.stdout = iter(["⏸ DeepSeek se ha quedado sin saldo: la cola espera\n"])

        def wait(self):
            nap(0.05)
            return main.CREDIT_EXIT

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    for name, value in (("is_drawn", lambda root, slug: False), ("needs_youtube", lambda root, slug: True),
                        ("footage_at_once", lambda root: 1), ("waits_for_youtube", lambda root, slug: False),
                        ("on_hold", lambda root, slug: False),
                        ("voice_in_background", lambda root, slug, folders=None: False),
                        ("_write_report", lambda root, results: None), ("notify", lambda root, text: told.append(text))):
        monkeypatch.setattr(main, name, value)
    monkeypatch.setattr(main.time, "sleep", lambda s: nap(min(s, 0.02)))
    results = main.run_parallel(["v1", "v2", "v3"], 1, force=set(), until=None, review=False, root=tmp_path)
    assert started == ["v1"] and results[0][1] == "en espera" and "sin saldo" in told[0]
