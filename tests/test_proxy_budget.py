"""budget.proxy_gb_per_day: a daily cap on the GB the paid proxy carries; at the cap a video that needs YouTube waits
for the next UTC day and the queue goes on with the rest."""

import json
import time
from datetime import datetime, timezone

import pytest

from pipeline import budget, web
from pipeline.budget import ApiSearchesShort, ProxyBudgetReached


def _rows(root, slug, rows):
    work = root / "work" / slug
    work.mkdir(parents=True, exist_ok=True)
    (work / "youtube_downloads.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_todays_gb_sum_every_videos_requests_of_the_utc_day_only(tmp_path):
    now = time.time()
    midnight = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc).timestamp()
    _rows(tmp_path, "a", [{"ts": now, "action": "metadata", "ok": True, "proxy": "resi", "proxy_bytes": 1_500_000_000},
                          {"ts": midnight - 60, "action": "metadata", "ok": True, "proxy": "resi", "proxy_bytes": 9_000_000_000},
                          {"ts": now, "action": "search", "ok": True}])                      # no proxy: no bytes
    _rows(tmp_path, "b", [{"ts": now, "action": "archivo hd", "ok": True, "proxy": "resi", "proxy_bytes": 500_000_000}])
    assert budget.proxy_gb_today(tmp_path) == 2.0
    assert budget.proxy_gb_today(tmp_path / "nothing") == 0.0


def test_at_the_cap_the_video_waits_for_tomorrow_and_below_it_nothing_happens(tmp_path):
    _rows(tmp_path, "a", [{"ts": time.time(), "action": "metadata", "ok": True, "proxy": "resi", "proxy_bytes": 3_000_000_000}])
    budget.check_proxy(tmp_path, {"budget": {"proxy_gb_per_day": 0}})             # no cap
    budget.check_proxy(tmp_path, {"budget": {"proxy_gb_per_day": 3.5}})           # under it
    with pytest.raises(ProxyBudgetReached) as caught:
        budget.check_proxy(tmp_path, {"budget": {"proxy_gb_per_day": 3}})
    error = caught.value
    assert isinstance(error, ApiSearchesShort) and error.why == "tope diario de GB del proxy"
    assert "3.00 GB de 3 GB" in str(error) and "mañana" in str(error)
    tomorrow = datetime.fromtimestamp(error.until, timezone.utc)
    assert tomorrow.hour == 0 and tomorrow.minute == 0 and 0 < error.until - time.time() <= 86400
    # the studio's setting wins over config.yaml
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "_ajustes.json").write_text(json.dumps({"proxy_gb_per_day": 10}))
    budget.check_proxy(tmp_path, {"budget": {"proxy_gb_per_day": 1}})
    assert budget.proxy_limit(tmp_path, {}) == 10.0


def test_the_studio_saves_the_cap_and_shows_todays_gb(tmp_path):
    _rows(tmp_path, "a", [{"ts": time.time(), "action": "metadata", "ok": True, "proxy": "resi", "proxy_bytes": 250_000_000}])
    (tmp_path / "canales").mkdir()
    (tmp_path / "config.yaml").write_text("budget:\n  daily_usd: 0\n")
    saved = web.settings(tmp_path, {"proxy_gb_per_day": "2.5"})
    assert saved["proxy_gb_per_day"] == 2.5
    assert web.settings(tmp_path, {"proxy_gb_per_day": -4})["proxy_gb_per_day"] == 0.0
    web.settings(tmp_path, {"proxy_gb_per_day": 2.5})
    b = web.overview(tmp_path)["budget"]
    assert b["proxyGbToday"] == 0.25 and b["proxyGbLimit"] == 2.5
