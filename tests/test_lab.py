from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from pipeline import lab
from pipeline.context import RunContext
from pipeline.ytapi import NoKeysLeft, YouTubeAPI, parse_channel, parse_duration


class Response:
    def __init__(self, status: int, data: dict) -> None:
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self) -> dict:
        return self._data


def _published(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _video(vid: str, channel: str, views: int, seconds: int = 600, days: int = 30) -> dict:
    return {"id": vid, "snippet": {"title": f"T{vid}", "channelId": channel, "channelTitle": channel,
                                   "publishedAt": _published(days), "thumbnails": {}},
            "statistics": {"viewCount": str(views)}, "contentDetails": {"duration": f"PT{seconds // 60}M{seconds % 60}S"}}


class FakeYouTube:
    """search → v1 (big hit on channel A), v2 (normal on B); uploads give each channel's baseline."""

    def __init__(self, quota_fail_keys: set[str] = frozenset()) -> None:
        self.calls: list[tuple[str, str]] = []
        self.quota_fail_keys = quota_fail_keys
        self.videos = {"v1": _video("v1", "A", 50_000), "v2": _video("v2", "B", 1_000), "s1": _video("s1", "A", 10**7, 30),
                       "a1": _video("a1", "A", 1_000), "a2": _video("a2", "A", 3_000),
                       "b1": _video("b1", "B", 1_000), "b2": _video("b2", "B", 1_000)}

    def get(self, url: str, params: dict, timeout: int = 0) -> Response:
        endpoint = url.rsplit("/", 1)[-1]
        self.calls.append((endpoint, params["key"]))
        if params["key"] in self.quota_fail_keys:
            return Response(403, {"error": {"errors": [{"reason": "quotaExceeded"}], "message": "quota"}})
        if endpoint == "search":
            return Response(200, {"items": [{"id": {"videoId": v}} for v in ("v1", "v2", "s1")]})
        if endpoint == "videos":
            return Response(200, {"items": [self.videos[i] for i in params["id"].split(",")]})
        if endpoint == "channels":
            ids = params.get("id", "A").split(",")
            return Response(200, {"items": [{"id": c, "snippet": {"title": c}, "statistics": {"subscriberCount": "5000"},
                                             "contentDetails": {"relatedPlaylists": {"uploads": "UU" + c}}} for c in ids]})
        if endpoint == "playlistItems":
            ids = {"UUA": ["a1", "a2", "v1", "s1"], "UUB": ["b1", "b2", "v2"]}[params["playlistId"]]
            return Response(200, {"items": [{"contentDetails": {"videoId": i}} for i in ids]})
        raise AssertionError(endpoint)


def _api(tmp_path, fake: FakeYouTube, keys: str = "k1,k2") -> YouTubeAPI:
    ctx = RunContext.create("_t", root=tmp_path, config={"lab": {"units_per_key": 10000}})
    ctx._env_loaded = True
    import os
    os.environ["YOUTUBE_API_KEYS"] = keys
    try:
        return YouTubeAPI(ctx, session=fake)
    finally:
        del os.environ["YOUTUBE_API_KEYS"]


def test_parsers():
    assert parse_duration("PT1H2M3S") == 3723
    assert parse_duration("PT45S") == 45
    assert parse_duration("P1DT1M") == 86460
    assert parse_duration("") == 0
    assert parse_channel("@GymnastIcons") == {"forHandle": "@GymnastIcons"}
    assert parse_channel("https://www.youtube.com/@GymnastIcons/videos") == {"forHandle": "@GymnastIcons"}
    assert parse_channel("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv") == {"id": "UCabcdefghijklmnopqrstuv"}
    assert parse_channel("GymnastIcons") == {"forHandle": "@GymnastIcons"}


def test_outliers_ratio_against_channel_median(tmp_path):
    fake = FakeYouTube()
    api = _api(tmp_path, fake)
    found = lab.outliers(api.ctx, "gimnasta", api=api)
    ratios = {v["id"]: v["ratio"] for v in found}
    # A's long uploads: 1000, 3000, 50000 → median 3000; B's: 1000, 1000, 1000. Shorts ignored.
    assert ratios == {"v1": round(50_000 / 3000, 1), "v2": 1.0}
    assert found[0]["id"] == "v1" and found[0]["subscribers"] == 5000
    assert [v["id"] for v in lab.outliers(api.ctx, "gimnasta", min_ratio=2, api=api)] == ["v1"]


def test_cache_and_quota_ledger(tmp_path):
    fake = FakeYouTube()
    api = _api(tmp_path, fake)
    api.search("x")
    api.search("x")                      # cached: no second call
    assert [c[0] for c in fake.calls] == ["search"]
    quota = api.quota()
    assert quota["used"] == 100 and quota["left"] == 9_900 and quota["keys"] == 1 and quota["searchesLeft"] == 99
    assert "k1" not in (tmp_path / "cache" / "ytapi" / "quota.json").read_text()   # keys never written


def test_one_project_only_and_its_own_search_limit(tmp_path, monkeypatch):
    import pytest
    from pipeline.ytapi import NoKeysLeft, chosen_key

    fake = FakeYouTube(quota_fail_keys={"k1"})
    api = _api(tmp_path, fake)                       # an old list of keys: only the first is used, never rotated
    assert api.keys == ["k1"]
    with pytest.raises(NoKeysLeft):
        api.search("y")
    assert [c[1] for c in fake.calls] == ["k1"]
    with pytest.raises(NoKeysLeft):                  # parked for the day: nothing else goes out
        api.search("z")
    assert len(fake.calls) == 1

    env = {"YOUTUBE_API_KEY": "prod", "YOUTUBE_API_KEYS": "a,b", "YOUTUBE_API_KEY_DEV": "dev"}
    get = lambda name, required=False: env.get(name, "")     # noqa: E731
    assert chosen_key(get) == ("prod", "producción")
    env["YOUTUBE_API_ENTORNO"] = "desarrollo"
    assert chosen_key(get) == ("dev", "desarrollo")

    ctx = RunContext.create("_t", root=tmp_path / "b", config={"lab": {"searches_per_day": 2}})
    monkeypatch.setenv("YOUTUBE_API_KEY", "k9")
    ctx._env_loaded = True
    limited = YouTubeAPI(ctx, session=FakeYouTube())
    limited.search("uno")
    limited.search("dos")
    with pytest.raises(NoKeysLeft, match="búsquedas"):
        limited.search("tres")
    assert limited.quota()["searchesLeft"] == 0 and limited.quota()["searches"] == 2

def test_no_keys_left(tmp_path):
    fake = FakeYouTube(quota_fail_keys={"k1"})
    api = _api(tmp_path, fake, keys="k1")
    try:
        api.search("q")
    except NoKeysLeft:
        pass
    else:
        raise AssertionError("expected NoKeysLeft")


def test_saved_roundtrip(tmp_path):
    ctx = RunContext.create("_t", root=tmp_path, config={})
    lab.save(ctx, {"id": "v1", "title": "Uno", "views": 5}, "buena miniatura")
    lab.save(ctx, {"id": "v2", "title": "Dos"})
    lab.save(ctx, {"id": "v1", "title": "Uno"})
    assert [v["id"] for v in lab.saved(ctx)] == ["v1", "v2"]
    assert [v["id"] for v in lab.unsave(ctx, "v1")] == ["v2"]


def test_raised_quota_of_the_one_key(tmp_path):
    api = _api(tmp_path, FakeYouTube(), keys="k1:50000")
    assert api.keys == ["k1"] and api.quota()["total"] == 50_000
