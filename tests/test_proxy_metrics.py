"""Every request through the proxy logs its session and bytes; --youtube-stats sums them up per proxy."""

import json
import time

from pipeline import ytstats
from pipeline.sourcing.youtube import YouTubeSource, error_kind

RESI = "http://user:pass@resi-bridge-eu.rainproxy.io:1111"
VIDEO = "dQw4w9WgXcQ"


def _source(tmp_path, **cfg):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never", **cfg})
    yt.metrics_path = tmp_path / "work" / "v1" / "youtube_downloads.jsonl"
    return yt


def _rows(yt):
    return [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]


def test_timeouts_have_their_own_kind():
    assert error_kind("ERROR: Unable to download webpage: The read operation timed out") == "timeout"
    assert error_kind("HTTP Error 403: Forbidden") == "403" and error_kind("something else") == "other"


class Response:
    def __init__(self, body=b"", length=None):
        self.headers = {"Content-Length": str(length)} if length is not None else {}
        self._body = body

    def read(self, amt=None):
        data, self._body = (self._body, b"") if amt is None else (self._body[:amt], self._body[amt:])
        return data


def test_yt_dlp_responses_through_the_proxy_are_counted_into_the_row(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    yt._local.video_id = VIDEO
    fake = [Response(length=700_000), Response(body=b"x" * 1000)]
    metered = yt._metered(type("Fake", (), {"urlopen": lambda self, req: fake.pop(0)})(), True)
    yt._local.proxy_bytes = 0
    metered.urlopen("req")                                     # Content-Length: counted at once
    metered.urlopen("req").read()                              # no length: what is read
    assert yt._local.proxy_bytes == 701_000
    untouched = yt._metered(type("Fake", (), {"urlopen": lambda self, req: fake})(), False)
    assert untouched.urlopen("req") is fake                    # direct: nothing wrapped
    assert yt._ydl({"skip_download": True}).urlopen.__name__ == "counting"   # a real YoutubeDL through the proxy is metered
    yt._call("metadata", lambda: "ok")                         # a request's row keeps what its try moved (0 here)
    row = _rows(yt)[-1]
    assert row["proxy"] == "resi-bridge-eu.rainproxy.io" and row["session"] and row["proxy_bytes"] == 0
    yt.close()


def test_file_rows_and_gets_carry_their_bytes_and_the_direct_way_carries_none(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    yt._local.video_id = VIDEO
    yt._local.way = 0
    yt._metric("archivo hd", ok=True, seconds=2.0, size=3_000_000, span=(1, 4))
    row = _rows(yt)[-1]
    assert row["proxy_bytes"] == 3_000_000 and row["bytes"] == 3_000_000 and row["session"]

    class Got:
        status_code = 200
        content = b"c" * 4096

        def raise_for_status(self): ...

    monkeypatch.setattr(yt._sessions[0], "get", lambda url, timeout, proxies=None: Got())
    yt._get("https://www.youtube.com/api/timedtext?x=1")
    row = _rows(yt)[-1]
    assert row["action"] == "get" and row["ok"] and row["proxy_bytes"] == 4096

    direct = _source(tmp_path)
    direct._local.video_id = VIDEO
    direct._metric("archivo hd", ok=True, seconds=2.0, size=3_000_000)
    assert "proxy_bytes" not in _rows(direct)[-1] and "proxy" not in _rows(direct)[-1]
    yt.close()


def test_youtube_stats_add_a_proxy_table_with_gb_per_finished_video_and_cost(tmp_path):
    now = time.time()
    done_rows = [
        {"ts": now, "action": "metadata", "ok": True, "proxy": "resi", "session": "a", "proxy_bytes": 1_000_000_000},
        {"ts": now, "action": "download (HLS)", "ok": False, "error": "403", "proxy": "resi", "session": "a", "proxy_bytes": 0},
        {"ts": now, "action": "download (HLS)", "ok": False, "error": "timeout", "proxy": "resi", "session": "b"},
        {"ts": now, "action": "archivo hd", "ok": True, "bytes": 500_000_000, "proxy": "resi", "proxy_bytes": 500_000_000, "seconds": 5},
        {"ts": now, "action": "metadata", "ok": False, "error": "bot", "proxy": "resi", "session": "b"},
    ]
    pending_rows = [{"ts": now, "action": "metadata", "ok": True, "proxy": "resi", "session": "c", "proxy_bytes": 500_000_000},
                    {"ts": now, "action": "metadata", "ok": True}]                      # no proxy: not in the table
    for slug, rows in (("done1", done_rows), ("pending", pending_rows)):
        folder = tmp_path / "work" / slug
        folder.mkdir(parents=True)
        (folder / "youtube_downloads.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "out" / "done1").mkdir(parents=True)
    (tmp_path / "out" / "done1" / "video-final.mp4").write_bytes(b"v")

    table = ytstats.proxy_summary({"done1": done_rows, "pending": pending_rows}, {"done1"}, usd_per_gb=0.62)
    assert table == [{"proxy": "resi", "requests": 5, "ok_share": 40.0, "errors": {"403": 1, "timeout": 1, "bot": 1},
                      "sessions": 3, "gb": 2.0, "videos": 2, "finished": 1, "gb_per_finished": 2.0, "usd": 1.24, "usd_per_gb": 0.62,
                      "details": []}]
    text = ytstats.report(tmp_path, 7).read_text("utf-8")
    assert "## Proxy" in text and "| resi | 5 | 40.0 % | 1 | 1 | 0 | 1 | 0 | 3 | 2.000 | 1/2 | 2.000 | 1.24 |" in text
    assert "0.62 $/GB" in text


def test_failures_keep_their_words_masked_and_the_table_lists_the_most_frequent(tmp_path, monkeypatch):
    from pipeline.sourcing.youtube import error_detail

    assert error_detail("ERROR: ERROR: Unable to connect to proxy http://u:p@resi.example:1 (407)") == \
        "Unable to connect to proxy http://****@resi.example:1 (407)"
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = _source(tmp_path, proxy=RESI)
    yt._local.video_id = VIDEO
    try:
        yt._call("metadata", lambda: (_ for _ in ()).throw(RuntimeError("Unable to connect to proxy http://user:pass@h:1: 407 Proxy Authentication Required")))
    except Exception:
        pass
    rows = _rows(yt)
    assert rows[-1]["error"] == "other" and rows[-1]["detail"].startswith("Unable to connect to proxy http://****@h:1")
    assert "pass" not in yt.metrics_path.read_text()
    table = ytstats.proxy_summary({"v1": rows}, set())
    assert table[0]["details"][0][1] == 1 and "407" in table[0]["details"][0][0]
    text = "\n".join(ytstats.proxy_lines(table))
    assert "Errores más frecuentes por resi-bridge-eu.rainproxy.io" in text and "1× Unable to connect" in text
    yt.close()
