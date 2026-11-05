"""The studio's proxy report: what the paid proxy carried, per finished video, for the server and spending pages."""

import json
import shutil
import time
from pathlib import Path

from pipeline import web

REPO = Path(__file__).resolve().parent.parent


def test_proxy_report_sums_gb_success_and_cost_per_finished_video(tmp_path):
    shutil.copy(REPO / "config.yaml", tmp_path / "config.yaml")
    (tmp_path / "canales").mkdir()
    now = time.time()
    for slug, done, rows in (
        ("v1", True, [{"ts": now, "action": "metadata", "ok": True, "proxy": "resi", "session": "a", "proxy_bytes": 2_000_000_000},
                      {"ts": now, "action": "download (HLS)", "ok": False, "error": "bot", "proxy": "resi", "session": "b", "detail": "Sign in to confirm you’re not a bot"}]),
        ("v2", False, [{"ts": now - 86400, "action": "archivo hd", "ok": True, "proxy": "resi", "proxy_bytes": 1_000_000_000, "bytes": 1},
                       {"ts": now - 30 * 86400, "action": "metadata", "ok": True, "proxy": "resi", "proxy_bytes": 9_000_000_000}])):   # too old
        work = tmp_path / "work" / slug
        work.mkdir(parents=True)
        (work / "youtube_downloads.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        if done:
            (tmp_path / "out" / slug).mkdir(parents=True)
            (tmp_path / "out" / slug / "video-final.mp4").write_bytes(b"v")
    r = web.proxy_report(tmp_path, 7)
    assert r["totalGb"] == 3.0 and r["finished"] == 1 and r["videos"] == 2 and r["gbPerFinished"] == 3.0
    assert r["usd"] == round(3.0 * r["usdPerGb"], 2) and r["usdPerGb"] > 0
    p = r["proxies"][0]
    assert p["proxy"] == "resi" and p["requests"] == 2 and p["ok_share"] == 50.0 and p["errors"] == {"bot": 1}
    assert [list(d) for d in p["details"]] == [["Sign in to confirm you’re not a bot", 1]] and p["sessions"] == 2
    assert len(r["perDay"]) == 2 and sum(d["gb"] for d in r["perDay"]) == 3.0
    assert web.proxy_report(tmp_path / "nothing", 7)["proxies"] == []
