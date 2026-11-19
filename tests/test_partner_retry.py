"""19-11: a partner's «Reintentar los 2» did nothing — it called /api/queue/retry-all, which partners may not use
(and which would retry everybody's videos). Their button retries their own videos one by one."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import web

ROOT = Path(__file__).resolve().parents[1]


def test_a_partner_may_retry_their_videos_but_not_everybodys(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "video_channel", lambda root, slug: "gtaviprueba" if slug.startswith("gta") else "otro")
    assert web.partner_may(tmp_path, ["gtaviprueba"], "POST", "/api/video/gta6jugadasconfirmadas/retry")
    assert not web.partner_may(tmp_path, ["gtaviprueba"], "POST", "/api/video/patinaje1/retry")
    assert not web.partner_may(tmp_path, ["gtaviprueba"], "POST", "/api/queue/retry-all")


def test_the_studio_gives_partners_the_per_video_retry():
    home = (ROOT / "pipeline" / "web_static" / "js" / "home.js").read_text("utf-8")
    assert "window.partner ? `retryMany(${esc(JSON.stringify(failedSlugs))}, this)` : \"retryAll()\"" in home


def test_retry_keeps_the_rest_of_the_queue_state(tmp_path, monkeypatch):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "_vigilar.json").write_text(json.dumps({"a": {"status": "ERROR"}, "b": {"status": "ERROR"}}))
    monkeypatch.setattr(web, "find_video", lambda root, slug: tmp_path)
    monkeypatch.setattr(web, "watcher_alive", lambda root: True)
    web.retry(tmp_path, "a")
    assert json.loads((tmp_path / "out" / "_vigilar.json").read_text()) == {"b": {"status": "ERROR"}}
    assert (tmp_path / web.RETRY_DIR / "a").is_file()
