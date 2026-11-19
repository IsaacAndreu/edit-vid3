"""«Lo que dicen estos datos» 4 and fase 1.6: long waits before taking a connection slot, and (opt-in) the pace of a
residential proxy per sticky session, with a machine-wide cap on connections to the proxy."""

from __future__ import annotations

import multiprocessing
import threading
import time

from pipeline.sourcing.common import ProcessSlots
from pipeline.sourcing.youtube import YouTubeSource

RESI = "http://u:p@resi.rainproxy.io:1111"


def _hold(folder, seconds, out):
    with ProcessSlots(folder, 2):
        out.put(time.time())
        time.sleep(seconds)


def test_process_slots_cap_the_whole_machine(tmp_path):
    ctx = multiprocessing.get_context("fork")
    out = ctx.Queue()
    procs = [ctx.Process(target=_hold, args=(tmp_path, 0.6, out)) for _ in range(3)]
    began = time.time()
    for p in procs:
        p.start()
    for p in procs:
        p.join(10)
    starts = sorted(out.get() - began for _ in range(3))
    assert starts[1] < 0.4 and starts[2] >= 0.5             # two at once, the third waits for a place


def _source(tmp_path, monkeypatch, **cfg):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                         config={"min_interval": 0.5, "cookies": "never", "proxy": RESI, "requests_per_hour": 0, **cfg})


def _timed(yt, video):
    yt._local.video_id = video
    began = time.monotonic()
    yt._call("metadata", lambda: None)
    return time.monotonic() - began


def test_per_session_two_videos_do_not_wait_for_each_other(tmp_path, monkeypatch):
    yt = _source(tmp_path, monkeypatch, pace_per_session=True, session_min_interval=0.5, concurrency=1)
    results = {}

    def run(video):
        results[video] = [_timed(yt, video) for _ in range(2)]

    threads = [threading.Thread(target=run, args=(v,)) for v in ("aaaaaaaaaaa", "bbbbbbbbbbb")]
    began = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert time.monotonic() - began < 0.9           # each video its own 0.5 s pace: in parallel
    assert all(r[1] >= 0.4 for r in results.values())   # but the same video keeps its pace
    yt.close()


def test_off_by_default_one_pace_for_the_proxy(tmp_path, monkeypatch):
    yt = _source(tmp_path, monkeypatch, concurrency=2)
    threads = [threading.Thread(target=_timed, args=(yt, v)) for v in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc")]
    began = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert time.monotonic() - began >= 0.9          # 3 requests, 0.5 s apart through the one shared pacer
    yt.close()


def test_the_hourly_budget_is_waited_without_holding_a_slot(tmp_path, monkeypatch):
    yt = _source(tmp_path, monkeypatch, concurrency=1, min_interval=0)
    release = threading.Event()
    calls = []

    def take(way, units):
        if not calls:
            calls.append("slow")
            release.wait(5)                      # the first request waits for the hour…
        return 0.0

    monkeypatch.setattr(yt, "_budget_take", take)
    slow = threading.Thread(target=_timed, args=(yt, "aaaaaaaaaaa"))
    slow.start()
    time.sleep(0.1)
    assert _timed(yt, "bbbbbbbbbbb") < 1.0        # …and the second one is not stuck behind its slot
    release.set()
    slow.join()
    yt.close()
