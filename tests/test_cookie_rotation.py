import pytest

from pipeline.sourcing.common import SourceUnavailable
from pipeline.sourcing.youtube import YouTubeSource


def _source(tmp_path, n):
    sets = [(f"# account {i}\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tx{i}\n", tmp_path / f"a{i}.txt") for i in range(n)]
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "account_switch_pause": 0},
                         cookie_sets=sets)


def test_requests_take_turns_between_accounts(tmp_path):
    yt = _source(tmp_path, 3)
    used = [yt._call("search", lambda: yt._local.account) for _ in range(6)]
    assert used == [0, 1, 2, 0, 1, 2]
    yt.close()


def test_a_blocked_account_is_set_aside_and_the_others_carry_on(tmp_path):
    yt = _source(tmp_path, 3)

    def fetch():
        if yt._local.account == 1:
            raise RuntimeError("ERROR: Sign in to confirm you're not a bot")
        return yt._local.account

    results = [yt._call("search", fetch) for _ in range(5)]
    assert 1 not in results and yt._bad == {1} and not yt.blocked


def test_blocked_everywhere_when_every_account_is_blocked(tmp_path):
    yt = _source(tmp_path, 2)

    def fetch():
        raise RuntimeError("Sign in to confirm you're not a bot")

    with pytest.raises(SourceUnavailable):
        yt._call("search", fetch)
    assert yt._bad == {0, 1} and "2 cuentas" in yt.blocked


def test_without_cookies_a_block_stops_youtube(tmp_path):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0})
    with pytest.raises(SourceUnavailable):
        yt._call("search", lambda: (_ for _ in ()).throw(RuntimeError("not a bot")))


def test_json_cookies_become_netscape(tmp_path):
    import json
    from pipeline.context import RunContext
    from pipeline.sourcing import cookie_sets, netscape_from_json

    raw = json.dumps([{"domain": ".youtube.com", "hostOnly": False, "path": "/", "secure": True,
                       "expirationDate": 1893456000.5, "name": "SID", "value": "abc"}])
    assert netscape_from_json(raw).splitlines()[1] == ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tabc"
    folder = tmp_path / "cookies"
    folder.mkdir()
    (folder / "cuenta1.json").write_text(raw)
    (folder / "cuenta2.txt").write_text(raw)            # JSON pasted into a .txt
    ctx = RunContext.create("x", root=tmp_path, config={})
    sets = cookie_sets(ctx, {"cookies_dir": str(folder)})
    assert len(sets) == 1                                  # same account twice → once
    assert sets[0][0].startswith("# Netscape") and (folder / "cuenta1.txt").is_file()


class _FakeAPI:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def search(self, query, order, max_results):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Cuota diaria agotada")
        return ["abcdefghijk", "bbbbbbbbbbb"][:max_results]

    def videos(self, ids):
        return [{"id": i, "title": f"T {i}", "channel": "Olympics", "duration": 300, "views": 1000} for i in ids]


def test_search_goes_through_the_api_when_there_are_keys(tmp_path):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "results_per_query": 2})
    yt.api = _FakeAPI()
    found = yt.search("carlos yulo floor")
    assert [e["id"] for e in found] == ["abcdefghijk", "bbbbbbbbbbb"] and found[0]["channel"] == "Olympics"
    assert found[0]["duration"] == 300 and "search-api" in yt.stats and "search" not in yt.stats
    yt.search("carlos yulo floor")                               # cached: no second API call
    assert yt.api.calls == 1


def test_an_api_error_never_turns_into_yt_dlp_searches(tmp_path, monkeypatch):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0})
    yt.api = _FakeAPI(fail=True)
    scraped = []
    monkeypatch.setattr(yt, "_call", lambda action, fn, **k: scraped.append(action))
    for query in ("q", "q2", "q3"):
        with pytest.raises(RuntimeError, match="API de YouTube"):
            yt.search(query)
    assert scraped == [] and yt.api is not None                 # the default (api_overflow: esperar): no scraping
    old = YouTubeSource(root=tmp_path, cache_dir=tmp_path / "b", config={"min_interval": 0, "api_overflow": "ytdlp"})
    old.api = _FakeAPI(fail=True)
    monkeypatch.setattr(old, "_call", lambda action, fn, **k: {"entries": [{"id": "ccccccccccc", "title": "x"}]})
    assert [e["id"] for e in old.search("q")] == ["ccccccccccc"]   # only when asked for: api_overflow: ytdlp


def test_two_processes_share_one_hourly_budget_that_survives_a_restart(tmp_path):
    import json

    from pipeline.sourcing.common import HourlyBudget

    path = tmp_path / ".ritmo-x.presupuesto"
    first, second = HourlyBudget(path, 10), HourlyBudget(path, 10)          # two processes, one file
    assert first.take(6) == 0 and second.take(4) == 0 and first.used() == 10
    rows = json.loads(path.read_text())
    rows[0][0] -= 3599.5                                                   # the first 6 units leave the hour soon
    path.write_text(json.dumps(rows))
    import time

    began = time.monotonic()
    assert HourlyBudget(path, 10).take(3) >= 1                            # a restarted one: it waits, no burst
    assert time.monotonic() - began >= 0.9 and HourlyBudget(path, 10).used() == 7


def test_parallel_searches_never_read_a_half_written_quota_ledger(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from pipeline.context import RunContext
    from pipeline.ytapi import YouTubeAPI

    class Answer:
        status_code = 200

        def json(self):
            return {"items": []}

    class Session:
        def get(self, *a, **k):
            return Answer()

    ctx = RunContext.create("v", root=tmp_path, config={"paths": {}})
    ctx.env = lambda name, required=True: "k1,k2" if name == "YOUTUBE_API_KEYS" else ""
    api = YouTubeAPI(ctx, session=Session())
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda n: api.get("videos", {"id": str(n)}), range(200)))
    assert api.quota()["used"] == 200


def test_browser_accounts_keep_only_youtube_cookies(monkeypatch):
    import http.cookiejar
    import yt_dlp.cookies
    from pipeline.sourcing import browser_cookies

    def fake(browser, profile=None, logger=None, *, keyring=None, container=None):
        assert (browser, profile, container) == ("firefox", None, "Cuenta1")
        jar = http.cookiejar.CookieJar()
        for domain, name in ((".youtube.com", "SID"), (".bank.com", "SECRET")):
            jar.set_cookie(http.cookiejar.Cookie(0, name, "v", None, False, domain, True, True, "/", True, True,
                                                 1893456000, False, None, None, {}))
        return jar

    monkeypatch.setattr(yt_dlp.cookies, "extract_cookies_from_browser", fake)
    text = browser_cookies("firefox::Cuenta1")
    assert ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tv" in text and "bank" not in text


def test_whole_downloads_keep_video_and_audio_pairs():
    from pipeline.coldopen import AUDIO_FORMAT
    from pipeline.sourcing.youtube import whole_format

    fmt = whole_format(AUDIO_FORMAT)
    assert fmt.split("/")[0] == "bv*[height<=1080][vcodec^=avc1][protocol=https]+ba[protocol=https]"
    assert whole_format("bv*[height<=1080]") == "bv*[height<=1080][protocol=https]"


def test_three_accounts_allow_more_downloads_until_youtube_asks_for_calm(tmp_path):
    import time

    sets = [(f"# cookies {n}", None) for n in range(3)]
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0}, cookie_sets=sets)
    assert yt.concurrency == 5
    yt._calm_down()
    time.sleep(0.2)
    assert yt._slots._value == 3 and yt._extra_slots == 0
    assert YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={}, cookie_sets=sets[:1]).concurrency == 3


def test_without_an_account_cookies_are_only_a_fallback_for_videos_that_need_one(tmp_path):
    import json

    sets = [(f"# cookies {n}", None) for n in range(2)]
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": False}, cookie_sets=sets)
    yt.metrics_path = tmp_path / "youtube_downloads.jsonl"
    assert yt.cookies_mode == "fallback" and yt.concurrency == 3
    used = []

    def public():
        used.append(yt._local.account)
        return "ok"

    assert yt._call("metadata", public) == "ok" and used == [None]          # public video: no account
    calls = []

    def age_restricted():
        calls.append(yt._local.account)
        if yt._local.account is None:
            raise RuntimeError("ERROR: Sign in to confirm your age. This video may be inappropriate for some users.")
        return "ok"

    assert yt._call("metadata", age_restricted) == "ok" and calls[0] is None and calls[1] is not None
    rows = [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]
    assert [(r["ok"], r["error"], r["cookies"]) for r in rows] == [(True, "", False), (False, "auth", False), (True, "", True)]
    never = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"cookies": "never"}, cookie_sets=sets)
    assert never._sets == []


def test_youtube_stats_sum_up_requests_errors_and_speed(tmp_path):
    import json
    import time

    from pipeline import ytstats

    rows = [{"ts": time.time(), "action": "metadata", "ok": True, "attempt": 1, "pot": True, "clients": ["default", "mweb"]},
            {"ts": time.time(), "action": "download (HLS)", "ok": False, "error": "403", "attempt": 1},
            {"ts": time.time(), "action": "archivo hd", "ok": True, "bytes": 20_000_000, "seconds": 4.0}]
    folder = tmp_path / "work" / "v1"
    folder.mkdir(parents=True)
    (folder / "youtube_downloads.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    s = ytstats.summary(rows)
    assert (s["requests"], s["failed"], s["errors"], s["files_ok"], s["mbps"], s["pot"]) == (2, 1, {"403": 1}, 1, 5.0, True)
    text = ytstats.report(tmp_path, 7).read_text("utf-8")
    assert "| v1 | 2 | 1 | 1 | 0 | 0 | 1/1 | 5.0 | 0 |" in text


def test_po_token_needs_the_plugin_and_its_server(tmp_path, monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"po_token": "auto"})
    assert yt.pot is False and "youtubepot-bgutilhttp" not in (yt.base_options.get("extractor_args") or {})

    class Ok:
        ok = True

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr("requests.Session.get", lambda self, url, timeout=3: Ok())
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"po_token": "auto", "player_client": ["default", "web_safari"]})
    args = yt.base_options["extractor_args"]
    assert yt.pot and args["youtube"]["player_client"] == ["default", "web_safari", "mweb"]
    assert args["youtubepot-bgutilhttp"] == {"base_url": ["http://127.0.0.1:4416"]}


def test_a_servers_bot_check_is_not_taken_for_a_video_that_needs_an_account(tmp_path):
    from pipeline.sourcing.youtube import error_kind

    bot = ("ERROR: [youtube] aqz-KE-bpKQ: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies "
           "for the authentication.")
    assert error_kind(bot) == "bot"
    assert error_kind("ERROR: Sign in to confirm your age. Use --cookies") == "auth"
    sets = [(f"# cookies {n}", None) for n in range(2)]
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "fallback", "cookies_on_bot": True},
                       cookie_sets=sets)
    calls = []

    def flagged_ip():
        calls.append(yt._local.account)
        if yt._local.account is None:
            raise RuntimeError(bot)
        return "ok"

    assert yt._call("metadata", flagged_ip) == "ok" and calls[0] is None and calls[1] is not None   # again with an account


def test_home_proxy_lets_only_youtube_through_and_the_server_uses_it(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("proxy_youtube", "scripts/casa/proxy_youtube.py")
    proxy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proxy)
    assert proxy.allowed("rr3---sn-h5q7rne6.googlevideo.com") and proxy.allowed("www.youtube.com")
    assert not proxy.allowed("example.com") and not proxy.allowed("evilyoutube.com")
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"proxy": "http://100.64.0.2:8899", "po_token": "on"})
    assert yt.base_options["proxy"] == "http://100.64.0.2:8899" and yt.http.proxies["https"] == "http://100.64.0.2:8899"
    assert yt.pot is False                       # home IP: no PO Token made for the server's IP
    assert "source_address" not in yt.base_options


def test_several_proxies_share_the_work_and_one_that_fails_rests(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    home, laptop = "http://100.64.0.2:8899", "http://100.64.0.3:8899"
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                       config={"proxies": [home, laptop], "min_interval": 0, "cookies": "never"})
    assert yt.proxies == [home, laptop] and yt._slots._value == 6           # 3 at a time through each
    assert yt._pacers[0]._path != yt._pacers[1]._path                     # each IP keeps its own pace
    used = [yt._call("search", lambda: yt._ydl().params["proxy"]) for _ in range(4)]
    assert set(used) == {home, laptop}                                    # both ways out get work

    def laptop_off():
        if yt._ydl().params["proxy"] == laptop:
            raise RuntimeError("Unable to download: ('Unable to connect to proxy', ConnectionRefusedError(111))")
        return "ok"

    assert all(yt._call("metadata", laptop_off) == "ok" for _ in range(4))
    assert yt._resting[1] > 0 and yt._pick_way() == 0                    # the laptop rests, home carries on



def test_a_bot_check_quarantines_that_way_and_never_hops(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    home, work = "http://100.64.0.2:8899", "http://100.64.0.3:8899"
    config = {"proxies": [home, work], "min_interval": 0, "cookies": "never"}
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config=config)
    seen = []

    def wary_home():
        seen.append(yt._ydl().params["proxy"])
        if seen[-1] == home:
            raise RuntimeError("Sign in to confirm you're not a bot")
        return "ok"

    yt._busy = [0, 1]                                                     # home is the least busy: tried first
    with pytest.raises(RuntimeError, match="cuarentena"):                # dropped, not sent again through work
        yt._call("metadata", wary_home)
    assert seen == [home] and yt.blocked is None
    assert [yt._call("metadata", wary_home) for _ in range(3)] == ["ok"] * 3 and set(seen[1:]) == {work}
    again = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config=config)   # the next video remembers it
    assert again._in_quarantine(0) and not again._in_quarantine(1) and again._pick_way() == 1


def test_every_way_in_quarantine_stops_youtube(tmp_path, monkeypatch):
    from pipeline.sourcing.youtube import all_quarantined

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    ways = ["http://100.64.0.2:8899", "http://100.64.0.3:8899"]
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                       config={"proxies": ways, "min_interval": 0, "cookies": "never"})
    calls = []

    def bot():
        calls.append(1)
        raise RuntimeError("Sign in to confirm you're not a bot")

    with pytest.raises(RuntimeError, match="cuarentena"):
        yt._call("search", bot)
    with pytest.raises(SourceUnavailable):                                # the second way too: the fuse
        yt._call("search", bot)
    with pytest.raises(SourceUnavailable):                                # and nothing else goes out
        yt._call("search", bot)
    assert len(calls) == 2 and all_quarantined(tmp_path, ways)


def test_one_way_shares_no_load_of_one_in_quarantine(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                       config={"proxies": ["http://a:1", "http://b:2"], "min_interval": 0, "concurrency": 3})
    assert yt._slots._value == 6 and [s._value for s in yt._way_slots] == [3, 3]


def test_proxy_list_from_env_or_config():
    from pipeline.sourcing.youtube import pacer_name, proxy_list

    assert proxy_list("http://a:1, http://b:2", ["http://c:3"], None) == ["http://a:1", "http://b:2"]
    assert proxy_list(None, ["http://c:3"], "http://c:3") == ["http://c:3"]
    assert proxy_list("", None, "http://d:4") == ["http://d:4"] and proxy_list(None, None, "") == []
    assert pacer_name("") == ".ritmo" and pacer_name("http://a:1") != pacer_name("http://b:2")


def test_after_a_bot_check_searches_wait_for_the_api_instead_of_yt_dlp(tmp_path, monkeypatch):
    import time

    from pipeline.budget import ApiSearchesShort
    from pipeline.sourcing.youtube import LAST_BLOCK

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "fallback"},
                       cookie_sets=[("# cookies", None)])
    with pytest.raises(SourceUnavailable) as blocked:                     # the only connection: quarantine, stop
        yt._call("metadata", lambda: (_ for _ in ()).throw(RuntimeError("Sign in to confirm you're not a bot")))
    assert "cuentas de cookies" not in str(blocked.value) and "No se usan cuentas" in str(blocked.value)
    asked = []
    fresh = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0})   # the next video, no API left
    fresh._call = lambda action, fn, **k: asked.append(action) or {"entries": []}
    assert fresh.recovering()
    with pytest.raises(ApiSearchesShort):
        fresh.search("a query")
    assert asked == []                                                    # not one yt-dlp search
    (tmp_path / "videos" / LAST_BLOCK).write_text(f"{time.time() - 73 * 3600:.0f}")
    assert not fresh.recovering() and fresh.search("a query") == [] and asked == ["search"]


def test_startup_says_the_reserve_account_is_never_for_a_bot_check(tmp_path, capsys):
    from pipeline.context import RunContext
    from pipeline.sourcing import youtube_source

    (tmp_path / "cookies").mkdir()
    (tmp_path / "cookies" / "cuenta.txt").write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tx\n")
    ctx = RunContext.create("v", root=tmp_path, config={"sourcing": {"youtube": {"cookies": "fallback", "api_search": False}}})
    youtube_source(ctx).close()
    out = capsys.readouterr().out
    assert "nunca ante «no eres un bot»" in out


def test_protection_report_names_keys_but_never_shows_them(tmp_path, monkeypatch):
    from pipeline import proteccion

    (tmp_path / "config.yaml").write_text("sourcing:\n  youtube: {cookies: fallback}\n")
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEYS", "secretA,secretB")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    text = "\n".join(proteccion.report(tmp_path))
    assert "secretA" not in text and "YOUTUBE_API_KEYS: 2 claves" in text
    assert "ante «no eres un bot»: nunca" in text and "libre" in text


def test_one_video_asking_bot_is_dropped_three_different_ones_quarantine(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr(YouTubeSource, "_extract", lambda self, url, extra: _raise_bot())   # the canary too: a block
    config = {"min_interval": 0, "cookies": "never"}
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config=config)
    asked = []

    def bot():
        asked.append(yt._local.video_id)
        raise RuntimeError("Sign in to confirm you're not a bot")

    for video in ("XKOukqWTbKs", "XKOukqWTbKs", "BBBBBBBBBBB"):    # the same one twice + another: 2 different
        yt._local.video_id = video
        with pytest.raises(RuntimeError, match="se descarta"):
            yt._call("metadata", bot)
    assert yt.blocked is None and not yt._in_quarantine(0) and not yt.recovering()
    again = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config=config)   # a restart remembers the strikes
    again._local.video_id = "CCCCCCCCCCC"
    with pytest.raises(SourceUnavailable):                              # the third different video: the connection
        again._call("metadata", bot)
    assert again._in_quarantine(0) and again.recovering()
    strict = YouTubeSource(root=tmp_path / "s", cache_dir=tmp_path / "s", config={**config, "bot_breaker_videos": 1})
    strict._local.video_id = "XKOukqWTbKs"
    with pytest.raises(SourceUnavailable):                              # bot_breaker_videos: 1 = the old rule
        strict._call("metadata", bot)


def test_a_stopped_proxy_is_said_and_the_video_waits_a_few_minutes(tmp_path, monkeypatch):
    import socket

    from pipeline.budget import ProxyDown
    from pipeline.context import RunContext
    from pipeline.sourcing import youtube_source
    from pipeline.sourcing.youtube import proxy_reachable

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()                                                      # nothing listens there
    assert not proxy_reachable(f"http://127.0.0.1:{port}", timeout=1) and proxy_reachable("")
    ctx = RunContext.create("v", root=tmp_path, config={"sourcing": {"youtube": {
        "proxies": [f"http://127.0.0.1:{port}"], "cookies": "never", "api_search": False}}})
    with pytest.raises(ProxyDown) as down:
        youtube_source(ctx)
    assert "no responde" in str(down.value) and down.value.until > 0 and down.value.why == "el proxy no responde"


def test_a_refused_video_is_never_asked_for_again(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    asked = []
    monkeypatch.setattr(yt, "_extract", lambda url, extra: asked.append(url) or
                        (_ for _ in ()).throw(RuntimeError("Sign in to confirm you're not a bot")))
    for _ in range(3):                                          # three shots with the same candidate
        with pytest.raises(RuntimeError):
            yt.info("XKOukqWTbKs")
    assert len(asked) == 1                                      # asked once
    other = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    assert other.refused("XKOukqWTbKs") and not other.refused("dQw4w9WgXcQ")   # another process knows it too


def test_with_an_account_one_refused_video_does_not_burn_the_account(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr(YouTubeSource, "_extract", lambda self, url, extra: _raise_bot())   # the canary too: a block
    yt = _source(tmp_path, 1)                                   # rotate: every request with the account
    yt.cfg["min_interval"] = 0

    def bot():
        raise RuntimeError("Sign in to confirm you're not a bot")

    for video in ("XKOukqWTbKs", "BBBBBBBBBBB"):
        yt._local.video_id = video
        with pytest.raises(RuntimeError, match="se descarta"):
            yt._call("metadata", bot)
    assert yt._bad == set() and yt.blocked is None              # two videos: dropped, the account is fine
    yt._local.video_id = "CCCCCCCCCCC"
    with pytest.raises(SourceUnavailable):                      # a third different one: the account is blocked
        yt._call("metadata", bot)
    assert yt._bad == {0}


def test_pause_probe_says_when_the_proxy_is_down_instead_of_testing(tmp_path, monkeypatch, capsys):
    from pipeline import ytpause
    import pipeline.ytcheck as ytcheck

    (tmp_path / "config.yaml").write_text("sourcing:\n  youtube: {min_interval: 0, proxy: 'http://127.0.0.1:9'}\n")
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    monkeypatch.setattr("pipeline.sourcing.youtube.proxy_reachable", lambda proxy, timeout=5.0: False)
    monkeypatch.setattr(ytcheck, "_try", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no test download")))
    assert ytpause.probe(tmp_path) is False
    assert "el proxy no responde" in capsys.readouterr().out


def test_refusals_with_successes_in_between_are_those_videos_not_the_connection(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})

    def bot():
        raise RuntimeError("Sign in to confirm you're not a bot")

    for video in ("AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC", "DDDDDDDDDDD"):
        yt._local.video_id = video
        with pytest.raises(RuntimeError, match="se descarta"):
            yt._call("metadata", bot)
        yt._local.video_id = "dQw4w9WgXcQ"
        assert yt._call("metadata", lambda: {"id": "ok"}) == {"id": "ok"}   # another video answers
    assert yt.blocked is None and not yt._in_quarantine(0)


def _raise_bot():
    raise RuntimeError("Sign in to confirm you're not a bot")


def test_refused_videos_in_a_row_with_a_canary_that_passes_burn_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    canaries = []
    monkeypatch.setattr(YouTubeSource, "_extract", lambda self, url, extra: canaries.append(url) or {"id": "ok"})
    yt = _source(tmp_path, 1)                                   # rotate: every request with the account
    yt.cfg["min_interval"] = 0
    for video in ("AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC", "DDDDDDDDDDD"):   # only the refused ones are left
        yt._local.video_id = video
        with pytest.raises(RuntimeError, match="se descarta"):
            yt._call("metadata", _raise_bot)
    assert yt._bad == set() and yt.blocked is None and not yt._in_quarantine(0)
    assert len(canaries) == 1 and "dQw4w9WgXcQ" in canaries[0]       # one control request, not one per video
    assert "eran esos vídeos" in capsys.readouterr().out
    plain = YouTubeSource(root=tmp_path / "p", cache_dir=tmp_path / "p", config={"min_interval": 0, "cookies": "never"})
    for video in ("AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"):        # without an account: the same
        plain._local.video_id = video
        with pytest.raises(RuntimeError, match="se descarta"):
            plain._call("metadata", _raise_bot)
    assert not plain._in_quarantine(0)
