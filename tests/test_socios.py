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
    health = json.loads(call("/api/canales")[1])["channels"]                  # «Canales»: theirs only
    assert [c["channel"] for c in health] == ["atletismo"] and len(health[0]["next"]) == 14 and len(health[0]["weeks"]) == 8


def test_nothing_of_yours_opens_for_a_partner(studio):
    root, call, login = studio
    login("contraseña-amigo")
    for path in ("/api/video/mio1", "/files/mio1/video-final.mp4", "/api/review/mio1", "/api/decisions/mio1",
                 "/api/video/mio1/repeticion", "/api/settings", "/api/users", "/api/servidor",
                 "/api/library", "/api/errors", "/api/proxy", "/api/piloto", "/api/voices/credits",
                 "/api/mychannel/aviacion", "/api/video/suyo1/pilot", "/api/copia", "/editor/mio1/", "/editor/mio1/api/state"):
        assert call(path)[0] == 403, path
    assert call("/editor/suyo1/api/state")[0] == 404              # theirs, but it has no edit yet: nothing to open
    for path, body in (("/api/video/mio1/hold", {}), ("/api/video/mio1/retry", {}), ("/api/settings", {"daily_usd": 9}),
                       ("/api/users", {"name": "amigo", "channels": ["aviacion"]}), ("/api/update", {}),
                       ("/api/videos", {"name": "nuevo", "channel": "aviacion", "script": SCRIPT}),
                       ("/api/video/suyo1/channel", {"channel": "aviacion"}), ("/api/review/mio1/s001", {"verdict": "mala"})):
        assert call(path, body)[0] == 403, path
    assert call("/editor/mio1/api/edits", {"edits": {}})[0] == 403
    assert call("/api/videos", {"name": "nuevo", "channel": "atletismo", "script": SCRIPT})[0] == 200


def test_you_still_see_everything_and_manage_partners(studio):
    root, call, login = studio
    assert login("clave") == 200
    data = json.loads(call("/api/overview")[1])
    assert {v["slug"] for v in data["videos"]} == {"mio1", "suyo1"} and "partner" not in data
    assert {"aviacion", "atletismo"} <= {c["channel"] for c in json.loads(call("/api/canales")[1])["channels"]}
    listed = json.loads(call("/api/users")[1])["users"]
    assert [(u["name"], u["channels"], u["telegram"]) for u in listed] == [("amigo", ["atletismo"], False)]
    assert "hash" not in json.dumps(listed) and "salt" not in json.dumps(listed)
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
    assert people[""]["server"] == 10.0 and people["amigo"]["server"] == 10.0             # half each, whatever the hours
    assert people["amigo"]["hours"] == 1.0 and people[""]["hours"] == 3.0
    assert people["amigo"]["api"] == 0.1 and people["amigo"]["voice"] == 0.22
    assert people["amigo"]["proxyUsd"] == round(2.0 * rate, 2)
    assert people["amigo"]["total"] == round(0.1 + 0.22 + 2.0 * rate + 10.0, 2)
    login("contraseña-amigo")
    mine = json.loads(call("/api/gasto")[1])["invoices"][0]
    assert [p["who"] for p in mine["people"]] == ["amigo"] and mine["hours"] is None
    code, body, headers = call(f"/api/factura.csv?month={month}&who=")                    # never another's
    assert code == 200 and "suyo1" in body.decode("utf-8-sig") and "mio1" not in body.decode("utf-8-sig")
    assert "servidor (20 / 2)" in body.decode("utf-8-sig")
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


def test_a_partner_changes_their_password_and_anyone_can_log_out(studio):
    root, call, login = studio
    login("contraseña-amigo")
    with patch("pipeline.web.time.sleep"):
        assert call("/api/password", {"current": "mala", "new": "nueva-clave-1"})[0] == 403
    assert call("/api/password", {"current": "contraseña-amigo", "new": "corta"})[0] == 400
    code, _, headers = call("/api/password", {"current": "contraseña-amigo", "new": "nueva-clave-1"})
    assert code == 200
    root_cookie = headers["Set-Cookie"].split(";")[0]
    assert usuarios.find(root, "nueva-clave-1") == "amigo"
    code, _, headers = call("/api/logout", {})
    assert code == 200 and "Max-Age=0" in headers["Set-Cookie"]
    login("clave")
    assert call("/api/password", {"current": "clave", "new": "otra-cosa-1"})[0] == 400       # yours lives in .env
    assert root_cookie.startswith("studio=u.amigo.")


def test_a_partners_video_messages_go_to_their_telegram(studio, monkeypatch):
    from pipeline import notify
    from pipeline.bot import Bot
    from pipeline.context import RunContext

    root, call, login = studio
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:" + "x" * 30)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    sent = []
    monkeypatch.setattr(notify.requests, "post", lambda url, **kw: sent.append((kw.get("json") or kw.get("data"))["chat_id"]) or
                        type("R", (), {"status_code": 200})())
    assert notify.target(RunContext.create("suyo1", root=root))[1] == "111"        # not connected yet: to you
    login("contraseña-amigo")
    monkeypatch.setattr("pipeline.web._bot_name", lambda token: "MiBot")
    link = json.loads(call("/api/telegram/link", {})[1])
    assert link["url"] == f"https://t.me/MiBot?start={link['code']}"

    class Http:
        def post(self, url, **kw):
            sent.append(kw["data"]["chat_id"])

    bot = Bot(root, session=Http())
    bot.handle({"message": {"chat": {"id": 999}, "text": "/start mal"}})
    assert usuarios.telegram_of(root, "amigo") == ""
    bot.handle({"message": {"chat": {"id": 999}, "text": f"/start {link['code']}"}})
    assert usuarios.telegram_of(root, "amigo") == "999" and sent[-1] == "999"
    assert json.loads(call("/api/cuenta")[1])["telegram"] is True
    sent.clear()
    notify.telegram(RunContext.create("suyo1", root=root), "terminado")
    notify.telegram(RunContext.create("mio1", root=root), "terminado")
    notify.telegram(RunContext.create("_subidos", root=root), "disco")
    assert sent == ["999", "111", "111"]
    assert notify.email(RunContext.create("suyo1", root=root), "x", "y") is False


def test_each_person_has_their_own_daily_caps(studio):
    from datetime import datetime, timezone

    from pipeline import budget

    root, call, login = studio
    today = datetime.now(timezone.utc).date().isoformat()
    for slug, usd in (("mio1", 3.0), ("suyo1", 0.4)):
        (root / "work" / slug / "costs.json").write_text(json.dumps({"entries": [{"usd": usd, "at": today + "T01:00:00"}]}))
    (root / "out" / "_ajustes.json").write_text(json.dumps({"daily_usd": 2.0}))
    with pytest.raises(budget.BudgetReached):
        budget.check(root, {}, "mio1")                              # you: 3 $ of your 2 $
    budget.check(root, {}, "suyo1")                                 # him: no cap of his own, your 3 $ do not count
    login("clave")
    assert call("/api/users", {"name": "amigo", "channels": ["atletismo"], "limits": {"daily_usd": 0.3}})[0] == 200
    with pytest.raises(budget.BudgetReached):
        budget.check(root, {}, "suyo1")
    assert budget.spent_today(root, "") == 3.0 and budget.spent_today(root, "amigo") == 0.4
    login("contraseña-amigo")
    account = json.loads(call("/api/cuenta")[1])
    assert account["limits"]["daily_usd"] == 0.3 and account["spentToday"] == 0.4


def test_a_partners_calendar_scripts_and_board_are_only_theirs(studio):
    from pipeline import agenda

    root, call, login = studio
    agenda.add_idea(root, "Idea mía", "aviacion")
    agenda.add_idea(root, "Idea suya", "atletismo")
    agenda.add_idea(root, "Idea sin canal", "")
    login("contraseña-amigo")
    cal = json.loads(call("/api/agenda")[1])
    assert set(cal["settings"]["schedule"]) == {"atletismo"} and {v["slug"] for v in cal["videos"]} == {"suyo1"}
    assert {s["channel"] for s in cal["plan"]} <= {"atletismo"} and [i["title"] for i in cal["settings"]["ideas"]] == ["Idea suya"]
    assert {c["channel"] for c in json.loads(call("/api/scripts")[1])["channels"]} <= {"atletismo"}
    board = json.loads(call("/api/board")[1])
    assert [i["title"] for i in board["columns"]["idea"]] == ["Idea suya"] and board["channels"] == ["atletismo"]
    assert all(x["channel"] == "atletismo" for items in board["columns"].values() for x in items)
    assert call("/api/agenda", {"channel": "atletismo", "time": "19:00"})[0] == 200
    assert call("/api/agenda", {"channel": "aviacion", "time": "19:00"})[0] == 403
    assert call("/api/agenda", {"buffer": 9})[0] == 403
    assert call("/api/agenda", {"assign": "mio1", "date": "2030-01-01"})[0] == 403
    assert call("/api/board/idea", {"title": "x", "channel": "aviacion"})[0] == 403
    assert call("/api/board/idea", {"title": "x", "channel": ""})[0] == 403
    mine_id = next(i["id"] for i in agenda.settings(root)["ideas"] if i["channel"] == "aviacion")
    assert call("/api/board/idea", {"delete": mine_id})[0] == 403
    assert call("/api/scripts/draft", {"channel": "aviacion", "idea": {"title": "t"}})[0] == 403
    assert call("/api/scripts/similar", {"slug": "mio1"})[0] == 403
    assert agenda.settings(root)["schedule"]["atletismo"]["time"] == "19:00"


def test_a_partners_radar_is_their_channels_only(studio):
    from pipeline import niche_ideas, radar

    root, call, login = studio
    (root / radar.FOLDER).mkdir(parents=True, exist_ok=True)
    (root / radar.FOLDER / "2026-11-09.json").write_text(json.dumps({"date": "2026-11-09", "channels": {
        "aviacion": {"top": [{"id": "A"}], "errors": []}, "atletismo": {"top": [{"id": "B"}], "errors": []}},
        "rising": [{"id": "R"}], "gaps": [{"name": "g"}]}))
    niche_ideas.save(root, {"id": "i1", "title": "Mía"}, "aviacion")
    login("contraseña-amigo")
    state = json.loads(call("/api/radar")[1])
    assert set(state["latest"]["channels"]) == {"atletismo"} and state["latest"]["rising"] == [] and state["niches"] == []
    assert state["saved"] == [] and state["channels"] == ["atletismo"]
    assert call("/api/ideas/save", {"idea": {"id": "i1", "title": "Pisada"}, "channel": "atletismo"})[0] == 403
    assert call("/api/ideas/save", {"remove": "i1"})[0] == 403
    saved = json.loads(call("/api/ideas/save", {"idea": {"id": "i2", "title": "Suya"}, "channel": "atletismo"})[1])
    assert [i["title"] for i in saved] == ["Suya"]
    for path in ("/api/radar", "/api/news", "/api/radar/gap"):
        assert call(path, {"topic": "x"})[0] == 403, path


def test_a_partners_channel_page_and_stats_are_theirs(studio, monkeypatch):
    from pipeline import estadisticas

    root, call, login = studio
    monkeypatch.setattr(estadisticas, "report", lambda root, refresh=False: {
        "videos": [{"slug": "mio1", "channel": "aviacion"}, {"slug": "suyo1", "channel": "atletismo"}],
        "channels": [{"channel": "aviacion", "views": 900, "watchHours": 9, "published": 1, "made": 1, "usd": 1.0},
                     {"channel": "atletismo", "views": 100, "watchHours": 1, "published": 1, "made": 1, "usd": 0.2}],
        "totals": {"views": 1000}, "fetched": None, "retention": 0.35})
    login("contraseña-amigo")
    st = json.loads(call("/api/stats")[1])
    assert [v["slug"] for v in st["videos"]] == ["suyo1"] and st["totals"]["views"] == 100
    assert call("/api/mychannel/atletismo")[0] == 200 and call("/api/mychannel/aviacion")[0] == 403
    assert call("/api/mychannel/aviacion", {})[0] == 403
    assert call("/api/mychannel/aviacion/handle", {"handle": "@x"})[0] == 403
    assert call("/api/mychannel/atletismo/handle", {"handle": "@SuCanal"})[0] == 200
    from pipeline import mychannel
    assert mychannel.handle_for(root, "atletismo") == "@SuCanal"
    assert sum(d["usd"] for d in json.loads(call("/api/spending")[1])) == 0.2


def test_the_queue_takes_turns_between_people(studio):
    import time as _time

    import main

    root, call, login = studio
    for name, channel in (("mio2", "aviacion"), ("mio3", "aviacion"), ("suyo2", "atletismo")):
        web.create_video(root, {"name": name, "channel": channel, "script": SCRIPT})
    order = ["mio1", "mio2", "mio3", "suyo1", "suyo2"]
    assert main.take_turns(root, order) == ["mio1", "suyo1", "mio2", "suyo2", "mio3"]
    stages = root / "work" / "mio1" / ".stages"                     # you used the server today: he goes first
    stages.mkdir(parents=True)
    (stages / "render.json").write_text(json.dumps({"seconds": 3600, "completedAt": _time.strftime("%Y-%m-%dT%H:%M:%S", _time.gmtime())}))
    assert main.take_turns(root, order) == ["suyo1", "mio1", "suyo2", "mio2", "mio3"]
    usuarios.remove(root, "amigo")
    assert main.take_turns(root, order) == order                    # alone: as before
