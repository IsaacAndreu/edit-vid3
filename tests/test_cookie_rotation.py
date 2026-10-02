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


def test_api_failure_falls_back_to_ytdlp_for_the_rest_of_the_run(tmp_path, monkeypatch):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0})
    yt.api = _FakeAPI(fail=True)
    monkeypatch.setattr(yt, "_call", lambda action, fn, **k: {"entries": [{"id": "ccccccccccc", "title": "x"}]})
    assert [e["id"] for e in yt.search("q")] == ["ccccccccccc"] and yt.api is not None   # one hiccup: keep the API
    yt.search("q2")
    yt.search("q3")
    assert yt.api is None                                       # it keeps failing: yt-dlp for the rest


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
