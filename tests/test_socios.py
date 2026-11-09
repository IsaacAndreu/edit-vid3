"""A partner shares the studio and sees only their channels: nothing of yours, not even by typing a URL."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

from pipeline import usuarios, web
from tests.test_web import SCRIPT, _project


@pytest.fixture
def studio(tmp_path):
    _project(tmp_path)
    web.create_video(tmp_path, {"name": "mio1", "channel": "aviacion", "script": SCRIPT})
    web.create_video(tmp_path, {"name": "suyo1", "channel": "atletismo", "script": SCRIPT})
    for slug in ("mio1", "suyo1"):
        (tmp_path / "out" / slug).mkdir(parents=True)
        (tmp_path / "out" / slug / "video-final.mp4").write_bytes(b"0123456789")
        (tmp_path / "work" / slug).mkdir(parents=True)
        (tmp_path / "work" / slug / "costs.json").write_text(json.dumps({"entries": [
            {"stage": "judge", "provider": "openai", "usd": 0.5 if slug == "mio1" else 0.2, "at": "2026-11-05T10:00:00"}]}))
    usuarios.save(tmp_path, "amigo", ["atletismo"], "contraseña-amigo", "clave")
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(tmp_path, "clave"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    jar = {"cookie": ""}

    def call(path, body=None):
        request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json",
                                                  **({"Cookie": jar["cookie"]} if jar["cookie"] else {})})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def login(password):
        code, _, headers = call("/api/login", {"password": password})
        jar["cookie"] = headers["Set-Cookie"].split(";")[0] if code == 200 else ""
        return code

    yield tmp_path, call, login
    server.shutdown()
    server.server_close()


def test_a_partner_sees_only_their_channels(studio):
    root, call, login = studio
    assert login("contraseña-amigo") == 200
    session = json.loads(call("/api/session")[1])
    assert session["partner"] == "amigo" and session["channels"] == ["atletismo"]
    data = json.loads(call("/api/overview")[1])
    assert [v["slug"] for v in data["videos"]] == ["suyo1"] and data["channels"] == ["atletismo"]
    assert data["youtube"] is None and data["service"]["code"] is None
    assert call("/api/video/suyo1")[0] == 200
    assert call("/files/suyo1/video-final.mp4")[0] == 200
    spend = json.loads(call("/api/gasto")[1])
    assert [v["slug"] for v in spend["videos"]] == ["suyo1"] and spend["total"] == 0.2 and spend["others"] is None
    hits = json.loads(call("/api/search?q=texto%20guion")[1])
    assert [r["slug"] for r in hits["results"]] == ["suyo1"]
    voices = json.loads(call("/api/voices")[1])
    assert voices["channels"] == ["atletismo"] and set(voices["speaks"]) == {"atletismo"}
    assert call("/api/voices", {"channel": "aviacion", "voice_id": "x"})[0] == 403
    assert call("/api/voices/credits")[0] == 403 and call("/api/dubbing", {"channel": "atletismo"})[0] == 403


def test_nothing_of_yours_opens_for_a_partner(studio):
    root, call, login = studio
    login("contraseña-amigo")
    for path in ("/api/video/mio1", "/files/mio1/video-final.mp4", "/api/review/mio1", "/api/decisions/mio1",
                 "/api/video/mio1/repeticion", "/api/stats", "/api/settings", "/api/users", "/api/servidor", "/api/radar",
                 "/api/library", "/api/errors", "/api/proxy", "/api/piloto", "/api/agenda", "/api/voices/credits", "/api/board",
                 "/api/mychannel/aviacion", "/api/video/suyo1/pilot", "/api/copia", "/api/scripts"):
        assert call(path)[0] == 403, path
    for path, body in (("/api/video/mio1/hold", {}), ("/api/video/mio1/retry", {}), ("/api/settings", {"daily_usd": 9}),
                       ("/api/users", {"name": "amigo", "channels": ["aviacion"]}), ("/api/update", {}),
                       ("/api/videos", {"name": "nuevo", "channel": "aviacion", "script": SCRIPT}),
                       ("/api/video/suyo1/channel", {"channel": "aviacion"}), ("/api/review/mio1/s001", {"verdict": "mala"})):
        assert call(path, body)[0] == 403, path
    assert call("/api/videos", {"name": "nuevo", "channel": "atletismo", "script": SCRIPT})[0] == 200


def test_you_still_see_everything_and_manage_partners(studio):
    root, call, login = studio
    assert login("clave") == 200
    data = json.loads(call("/api/overview")[1])
    assert {v["slug"] for v in data["videos"]} == {"mio1", "suyo1"} and "partner" not in data
    assert json.loads(call("/api/users")[1])["users"] == [{"name": "amigo", "channels": ["atletismo"], "created": usuarios._read(root)["amigo"]["created"]}]
    assert call("/api/users", {"name": "otro", "channels": ["atletismo"], "password": "otra-clave-larga"})[0] == 400   # one owner
    assert call("/api/users", {"name": "otro", "channels": ["aviacion"], "password": "clave"})[0] == 400              # yours
    assert call("/api/users", {"name": "otro", "channels": ["nada"], "password": "otra-clave-larga"})[0] == 400
    assert call("/api/users", {"name": "amigo", "channels": ["atletismo", "aviacion"]})[0] == 200
    assert usuarios.owner_of(root, "aviacion") == "amigo" and usuarios.owner_of(root, "megaproyectos") == ""


def test_a_new_password_closes_the_partners_sessions(studio):
    root, call, login = studio
    login("contraseña-amigo")
    assert call("/api/overview")[0] == 200
    usuarios.save(root, "amigo", ["atletismo"], "otra-contraseña", "clave")
    assert call("/api/overview")[0] == 401
    with patch("pipeline.web.time.sleep"):
        assert login("contraseña-amigo") == 403
    assert login("otra-contraseña") == 200
    usuarios.remove(root, "amigo")
    assert call("/api/overview")[0] == 401
    assert "contraseña" not in (root / usuarios.FILE).read_text() or "otra-contraseña" not in (root / usuarios.FILE).read_text()


def test_each_person_pays_their_month_and_their_hours_of_the_server(studio):
    import time as _time

    from pipeline import gasto

    root, call, login = studio
    month = _time.strftime("%Y-%m", _time.gmtime())
    (root / "out" / "_ajustes.json").write_text(json.dumps({"server_usd_month": 20}))
    for slug, cost, seconds, gb in (("mio1", 0.3, 3 * 3600, 1.0), ("suyo1", 0.1, 3600, 2.0)):
        (root / "work" / slug / "costs.json").write_text(json.dumps({"entries": [
            {"stage": "judge", "provider": "openai", "usd": cost, "at": f"{month}-02T10:00:00"},
            {"stage": "voz", "provider": "genaipro", "usd": 0, "at": f"{month}-02T11:00:00", "details": {"chars": 10000}}]}))
        (root / "work" / slug / ".stages").mkdir()
        (root / "work" / slug / ".stages" / "render.json").write_text(json.dumps({"seconds": seconds, "completedAt": f"{month}-02T12:00:00"}))
        (root / "work" / slug / "youtube_downloads.jsonl").write_text(json.dumps(
            {"ts": _time.time(), "action": "metadata", "proxy": "resi", "proxy_bytes": int(gb * 1e9)}))
    rate = gasto.proxy_usage(root)[1]["usdPerGb"]
    people = {p["who"]: p for p in gasto.invoices(root)[0]["people"]}
    assert people[""]["server"] == 15.0 and people["amigo"]["server"] == 5.0              # 3 h and 1 h of 4
    assert people["amigo"]["api"] == 0.1 and people["amigo"]["voice"] == 0.22
    assert people["amigo"]["proxyUsd"] == round(2.0 * rate, 2)
    assert people["amigo"]["total"] == round(0.1 + 0.22 + 2.0 * rate + 5.0, 2)
    login("contraseña-amigo")
    mine = json.loads(call("/api/gasto")[1])["invoices"][0]
    assert [p["who"] for p in mine["people"]] == ["amigo"] and mine["hours"] is None
    code, body, headers = call(f"/api/factura.csv?month={month}&who=")                    # never another's
    assert code == 200 and "suyo1" in body.decode("utf-8-sig") and "mio1" not in body.decode("utf-8-sig")
    login("clave")
    code, body, _ = call(f"/api/factura.csv?month={month}&who=")
    assert "mio1" in body.decode("utf-8-sig") and "suyo1" not in body.decode("utf-8-sig")


def test_a_partner_makes_a_channel_and_it_is_theirs(studio):
    root, call, login = studio
    login("contraseña-amigo")
    about = "documentales sobre la historia del atletismo"
    assert call("/api/channels", {"name": "atletas-x", "about": about, "base": "aviacion"})[0] == 403   # not your look
    assert call("/api/channels", {"name": "atletas-x", "about": about, "base": "atletismo"})[0] == 200
    assert usuarios.channels_of(root, "amigo") == ["atletas-x", "atletismo"]
    assert "atletas-x" in json.loads(call("/api/overview")[1])["channels"]
    assert call("/api/videos", {"name": "nuevo2", "channel": "atletas-x", "script": SCRIPT})[0] == 200
