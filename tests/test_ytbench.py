from pipeline import ytbench


def test_the_summary_puts_the_fastest_working_client_first():
    rows = [
        {"way": "casa", "client": "mweb", "video": "a", "ok": True, "details_s": 5.0, "storyboard": True,
         "p360": {"mbps": 0.1, "protocol": "https", "seconds": 8}, "p1080": {"mbps": 0.2, "seconds": 9}},
        {"way": "casa", "client": "web_safari", "video": "a", "ok": True, "details_s": 3.0, "storyboard": True,
         "p360": {"mbps": 2.5, "protocol": "m3u8_native", "seconds": 1}, "p1080": {"mbps": 3.0, "seconds": 2}},
        {"way": "casa", "client": "android_vr", "video": "a", "ok": False, "error": "Sign in to confirm"},
    ]
    summary = ytbench.summary(rows)
    assert [s["client"] for s in summary] == ["web_safari", "mweb", "android_vr"]
    assert summary[0]["mbps360"] == 2.5 and summary[0]["protocol"] == "m3u8_native"
    assert summary[-1]["ok"] == 0 and "Sign in" in summary[-1]["error"]


def test_single_flight_asks_once_for_the_same_thing(tmp_path):
    import threading
    import time

    from pipeline.sourcing.common import cached_json

    calls = []

    def produce():
        calls.append(1)
        time.sleep(0.2)
        return {"ok": True}

    threads = [threading.Thread(target=cached_json, args=(tmp_path / "x.json", produce)) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(calls) == 1
