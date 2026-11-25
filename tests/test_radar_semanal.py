"""Weekly radar, step 1: watched English channels → niche-formulas (pipeline/radar_semanal.py), API and model faked."""

from datetime import datetime, timedelta, timezone

import pytest

from pipeline import radar_semanal as rs

NOW = datetime(2026, 11, 30, 3, 0, tzinfo=timezone.utc)          # a Monday night, week 2026-W49


def _iso(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _videos(prefix, views, minutes=15, every=3, title="Why You'd Never Want To Meet a {}", lang="en"):
    return [{"id": f"{prefix}{i}", "title": title.format(i), "channelId": prefix, "channel": prefix,
             "published": _iso(5 + i * every), "duration": minutes * 60, "views": v, "live": "none",
             "audioLanguage": lang} for i, v in enumerate(views)]


class FakeAPI:
    keys = ["k"]

    def __init__(self, left=10_000, chart=True):
        self.used, self.left, self.searched, self.charted, self.chart = 0, left, [], [], chart
        ocean = [800_000, 760_000, 700_000, 650_000, 900_000, 720_000, 680_000, 740_000, 600_000, 1_100_000]
        self.channels_ = {
            "UCfossil0000000000000000": {"created": _iso(200), "subscribers": 120_000, "videos": _videos("UCfossil0000000000000000", ocean)},
            "UCblackwater000000000000": {"created": _iso(120), "subscribers": 90_000, "videos": _videos("UCblackwater000000000000", ocean[:8])},
            "UCdepththeory00000000000": {"created": _iso(60), "subscribers": 70_000,
                                         "videos": _videos("UCdepththeory00000000000", ocean[2:9], title="Would a {} Survive Every Prehistoric Ocean?")},
            "UConehit0000000000000000": {"created": _iso(40), "subscribers": 20_000,
                                         "videos": _videos("UConehit0000000000000000", [7_900_000])},
            "UCold0000000000000000000": {"created": _iso(2000), "subscribers": 150_000, "count": 400, "videos": []},
            "UCbig0000000000000000000": {"created": _iso(100), "subscribers": 2_000_000, "videos": []},
            "UCespanol000000000000000": {"created": _iso(90), "subscribers": 50_000,
                                         "videos": _videos("UCespanol000000000000000", ocean, title="Por qué nunca querrías conocer a {}", lang="es")},
        }

    def _spend(self, units):
        self.used += units
        self.left -= units

    def quota(self):
        return {"used": self.used, "left": self.left}

    def search(self, query, **kw):
        self._spend(100)
        self.searched.append(query)
        return ["UCfossil00000000000000003"[:-1] + "3"] if query else []

    def videos(self, ids):
        self._spend(1)
        rows = [v for c in self.channels_.values() for v in c["videos"]]
        return [{**v, "channelId": "UCfossil0000000000000000"} for v in rows[:1]] + \
               [{"id": "x", "title": "x", "channelId": "UCblackwater000000000000", "views": 900_000, "duration": 900}]

    def popular(self, region):
        self._spend(1)
        self.charted.append(region)
        if not self.chart:
            return []
        return [{"id": "p", "channelId": "UCbig0000000000000000000", "duration": 1200, "views": 5_000_000},
                {"id": "q", "channelId": "UCdepththeory00000000000", "duration": 900, "views": 1_000_000},
                {"id": "s", "channelId": "UCshort00000000000000000", "duration": 50, "views": 9_000_000}]

    def channels(self, ids):
        self._spend(1)
        out = []
        for cid in ids:
            c = self.channels_.get(cid)
            if c:
                out.append({"id": cid, "title": cid[2:10], "handle": "@" + cid[2:10], "created": c["created"],
                            "subscribers": c["subscribers"], "videoCount": c.get("count", len(c["videos"])),
                            "uploads": "UU" + cid[2:]})
        return out

    def channel(self, handle):
        self._spend(1)
        return {"id": "UCespanol000000000000000"} if "espanol" in handle else None

    def uploads(self, playlist, count=30):
        self._spend(2)
        return self.channels_["UC" + playlist[2:]]["videos"][:count]


GROUPS = {"niches": [{"name": "Océano profundo y fauna prehistórica", "topic": "fauna marina prehistórica",
                      "pattern": "Why You'd Never Want To Meet a X", "faceless": "sí",
                      "channels": ["UCfossil0000000000000000", "UCblackwater000000000000", "UCdepththeory00000000000",
                                   "UCinventado00000000000000"]}]}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config.yaml").write_text("radar:\n  semanal: true\n  semanal_busquedas: 2\n  keep_for_queue: 100\n",
                                          encoding="utf-8")
    return tmp_path


def test_a_week_finds_the_ocean_niche_from_three_new_channels(root):
    api = FakeAPI()
    rs.import_text(root, "name,url\nDepth,https://www.youtube.com/@espanol\nFossil,UCfossil0000000000000000\n", now=NOW)
    state = rs.run(root, api=api, ask=lambda **kw: GROUPS, now=NOW)
    assert state["done"] and state["week"] == "2026-W49"
    assert len(api.searched) == 2 and api.charted == ["US", "GB"]
    watch = rs.load_watch(root)["channels"]
    status = {cid: c["status"] for cid, c in watch.items()}
    assert status["UCfossil0000000000000000"] == status["UCblackwater000000000000"] == status["UCdepththeory00000000000"] == "cuenta"
    assert status["UCbig0000000000000000000"] == "grande" and status["UCespanol000000000000000"] == "otro_idioma"
    assert "UCshort00000000000000000" not in status                       # a Short in the chart: not a long video
    [niche] = state["niches"]
    assert niche["channels"] == ["UCfossil0000000000000000", "UCblackwater000000000000", "UCdepththeory00000000000"]
    f = niche["figures"]
    assert f["channelCount"] == 3 and f["strong"] and f["videos"] == 25 and f["minutes"] == 15.0
    assert f["median"] == 730_000                                         # the median of the three channels' medians (730, 730, 700)
    assert niche["trend"]["label"] == "nuevo" and niche["pattern"].startswith("Why You'd")
    assert state["units"] == api.used and api.used < 300


def test_one_video_that_exploded_is_watched_not_a_niche(root):
    api = FakeAPI()
    rs.import_text(root, "UConehit0000000000000000 UCold0000000000000000000", now=NOW)
    state = rs.run(root, api=api, ask=lambda **kw: {"niches": []}, now=NOW)
    watch = rs.load_watch(root)["channels"]
    assert watch["UConehit0000000000000000"]["status"] == "exito_suelto"
    assert watch["UCold0000000000000000000"]["status"] == "viejo"
    assert [s["id"] for s in state["singles"]] == ["UConehit0000000000000000"]
    assert all(n.get("ungrouped") for n in state["niches"])               # the model said nothing: one niche per channel


def test_the_quota_stops_it_and_the_next_night_carries_on(root):
    api = FakeAPI(left=100 + 2 + 1)            # keep_for_queue 100: room for the charts and a little more
    rs.import_text(root, " ".join(c for c in FakeAPI().channels_), now=NOW)
    first = rs.run(root, api=api, ask=lambda **kw: GROUPS, now=NOW)
    assert not first["done"] and first["left"] > 0 and api.searched == []   # no room for a search (101 units)
    api.left = 10_000                                                         # the next day's quota
    second = rs.run(root, api=api, ask=lambda **kw: GROUPS, now=NOW + timedelta(hours=24))
    assert second["done"] and second["left"] == 0 and second["niches"][0]["figures"]["channelCount"] == 3
    assert rs.run(root, api=api, ask=lambda **kw: (_ for _ in ()).throw(AssertionError("done")), now=NOW + timedelta(hours=48))["done"]


def test_the_next_week_says_what_rises(root):
    api = FakeAPI(chart=False)
    rs.import_text(root, "UCfossil0000000000000000 UCblackwater000000000000", now=NOW)
    rs.run(root, api=api, ask=lambda **kw: GROUPS, now=NOW)
    rs.import_text(root, "UCdepththeory00000000000", now=NOW + timedelta(days=7))
    week2 = rs.run(root, api=api, ask=lambda **kw: GROUPS, now=NOW + timedelta(days=7))
    assert week2["week"] == "2026-W50"
    trend = week2["niches"][0]["trend"]
    assert trend["label"] == "sube" and trend["entered"] == ["UCdepththeory00000000000"]


def test_when_it_runs(root):
    from pipeline.context import RunContext

    config = RunContext.create("_radar", root=root).config
    monday_night = datetime(2026, 11, 30, 3, 0)
    assert rs.is_due(root, config, now=monday_night)
    assert not rs.is_due(root, config, now=datetime(2026, 11, 30, 1, 0))   # before semanal_hora (2)
    assert not rs.is_due(root, {"radar": {"semanal": False}}, now=monday_night)   # off by default
    (root / rs.FOLDER).mkdir(parents=True)
    (root / rs.FOLDER / "2026-W49.json").write_text('{"done": true}')
    assert not rs.is_due(root, config, now=datetime(2026, 12, 2, 3, 0))     # this week done


def test_channels_found_in_any_list():
    text = "Fossil,https://www.youtube.com/channel/UCfossil0000000000000000,12\n@BlackWater · youtube.com/@DepthTheory\nfile.csv"
    assert rs.parse_channels(text) == ["UCfossil0000000000000000", "@BlackWater", "@DepthTheory"]


def test_the_studio_page_reads_the_week_and_imports_channels(root):
    from pipeline import web

    empty = web.weekly_radar(root)
    assert empty["week"] is None and empty["settings"]["on"] is True and empty["job"]["running"] is False
    rs.run(root, api=FakeAPI(), ask=lambda **kw: GROUPS, now=NOW)
    page = web.weekly_radar(root)
    assert page["current"]["done"] and page["week"]["niches"][0]["figures"]["channelCount"] == 3
    assert page["watch"]["cuenta"] == 3 and "UCfossil0000000000000000" in page["week"]["channels"]
    got = rs.import_text(root, "https://www.youtube.com/@NuevoCanal y UCfossil0000000000000000")
    assert got == {"found": 2, "added": 1, "watched": got["watched"]}            # the one already watched is not added twice
    assert web.partner_may(root, ["gimnasia"], "GET", "/api/radar-semanal") is False   # the owner's only
