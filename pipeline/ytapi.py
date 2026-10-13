"""YouTube Data API v3 with several keys: one after another, per-key daily quota, a search counter and a disk cache.

.env: YOUTUBE_API_KEYS=key1,key2,… (or a single YOUTUBE_API_KEY). Each key has its own daily quota (10 000 units,
`lab.units_per_key`; "key:50000" for a raised one) and its own search counter (`lab.searches_per_day`, 100); when
one runs out (or Google answers quotaExceeded) the next one is used. YOUTUBE_API_KEY_DEV is used alone with
YOUTUBE_API_ENTORNO=desarrollo. Quotas reset at midnight in Los Angeles. A search costs 100 units; video, channel and
playlist lookups cost 1 per 50 items. Counts are kept in cache/ytapi/quota.json (never the keys) and every call is
written down in cache/ytapi/registro-<day>.jsonl. Answers are cached on disk (search 12 h, stats 6 h, baselines 24 h).
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .context import RunContext

API = "https://www.googleapis.com/youtube/v3"
COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1}
TTL = {"search": 12 * 3600, "videos": 6 * 3600, "channels": 24 * 3600, "playlistItems": 6 * 3600}
QUOTA_ERRORS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}


class NoKeysLeft(RuntimeError):
    pass


_LOCK = threading.Lock()      # the quota ledger is read and rewritten by parallel searches


def _write(path: Path, text: str) -> None:
    """Whole or nothing: a parallel reader never sees a half-written file."""

    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def quota_day(now: datetime | None = None) -> str:
    """The quota day (Google resets at midnight America/Los_Angeles)."""

    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:  # no tz database (bare Windows Python): PST is close enough
        return (now - timedelta(hours=8)).date().isoformat()


def next_reset(now: datetime | None = None) -> datetime:
    """When the daily quota comes back: the next midnight in America/Los_Angeles (Google's rule), as UTC. Usually
    9:00 in Spain, 8:00 in the weeks when only one side has changed the clocks."""

    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        pacific = now.astimezone(ZoneInfo("America/Los_Angeles"))
        midnight = datetime.combine(pacific.date() + timedelta(days=1), datetime.min.time(), ZoneInfo("America/Los_Angeles"))
        return midnight.astimezone(timezone.utc)
    except Exception:  # no tz database: PST
        shifted = now - timedelta(hours=8)
        return datetime.combine(shifted.date() + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=8)


def reset_text(now: datetime | None = None, zone: str = "Europe/Madrid") -> str:
    """«a las 09:00 del 13/10 (hora de España)»: the next reset in the user's own time."""

    moment = next_reset(now)
    try:
        from zoneinfo import ZoneInfo

        local = moment.astimezone(ZoneInfo(zone))
        return f"a las {local:%H:%M} del {local:%d/%m} (hora de España)"
    except Exception:
        return f"a las {moment:%H:%M} UTC del {moment:%d/%m}"


def parse_duration(value: str | None) -> int:
    """ISO 8601 (PT1H2M3S, P1DT2H) → seconds."""

    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value or "")
    if not match:
        return 0
    d, h, m, s = (int(x or 0) for x in match.groups())
    return ((d * 24 + h) * 60 + m) * 60 + s


def parse_channel(value: str) -> dict[str, str]:
    """'@handle', 'handle', a channel URL or a UC… id → the channels.list filter."""

    value = value.strip()
    if found := re.search(r"(UC[\w-]{22})", value):
        return {"id": found.group(1)}
    if found := re.search(r"@([\w.-]+)", value):
        return {"forHandle": "@" + found.group(1)}
    return {"forHandle": "@" + value.rstrip("/").split("/")[-1]}


def _error(response: Any) -> dict[str, Any]:
    try:
        return response.json().get("error", {}) or {}
    except ValueError:
        return {}


_WARNED: set[str] = set()


def chosen_keys(env: Any) -> tuple[list[str], str]:
    """(the keys to use, in order, "producción" | "desarrollo"): YOUTUBE_API_KEYS (one after another: when one runs
    out of quota the next one is used), else YOUTUBE_API_KEY; YOUTUBE_API_KEY_DEV alone with YOUTUBE_API_ENTORNO=desarrollo."""

    if str(env("YOUTUBE_API_ENTORNO", required=False) or "").strip().lower() in ("desarrollo", "dev", "development"):
        dev = str(env("YOUTUBE_API_KEY_DEV", required=False) or "").strip()
        return ([dev] if dev else []), "desarrollo"
    many = [k.strip() for k in str(env("YOUTUBE_API_KEYS", required=False) or "").split(",") if k.strip()]
    single = str(env("YOUTUBE_API_KEY", required=False) or "").strip()
    return list(dict.fromkeys([*many, *([single] if single else [])])), "producción"


class YouTubeAPI:
    def __init__(self, ctx: RunContext, session: Any = None) -> None:
        self.ctx = ctx
        entries, self.environment = chosen_keys(ctx.env)
        default = int(ctx.section("lab").get("units_per_key", 10000))
        self.searches_per_day = int(ctx.section("lab").get("searches_per_day", 100))     # per key
        self.keys, self.limits = [], {}
        for entry in entries:                        # "key" or "key:units" (a raised quota)
            key, _, units = entry.partition(":")
            self.keys.append(key)
            self.limits[key] = int(units) if units.isdigit() else default
        self.dir = ctx.cache_dir / "ytapi"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()

    # ---- quota ---------------------------------------------------------------------------------
    def _ledger(self) -> dict[str, Any]:
        path = self.dir / "quota.json"
        try:
            data = json.loads(path.read_text("utf-8")) if path.is_file() else {}
        except ValueError:          # a ledger cut short by an old crash: start the count again
            data = {}
        if data.get("day") != quota_day():
            data = {"day": quota_day(), "used": {}, "exhausted": []}
        if not isinstance(data.get("searches"), dict):        # per key (an older ledger had one number)
            data["searches"] = {}
        return data

    def _save_ledger(self, data: dict[str, Any]) -> None:
        _write(self.dir / "quota.json", json.dumps(data))

    def _journal(self, row: dict[str, Any]) -> None:
        """Every call is written down before it goes out (cache/ytapi/registro-<quota day>.jsonl, never the key):
        what was spent, by whom, against which count."""

        try:
            with open(self.dir / f"registro-{quota_day()}.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "slug": self.ctx.slug, **row}) + "\n")
        except OSError:
            pass

    @staticmethod
    def _key_id(key: str) -> str:   # never store the keys themselves
        return hashlib.sha256(key.encode()).hexdigest()[:10]

    def quota(self) -> dict[str, Any]:
        ledger = self._ledger()
        used = sum(ledger["used"].get(self._key_id(k), 0) for k in self.keys)
        total = sum(self.limits.values())
        left = sum(0 if self._key_id(k) in ledger["exhausted"] else max(0, self.limits[k] - ledger["used"].get(self._key_id(k), 0))
                   for k in self.keys)
        searches_left = 0
        for k in self.keys:
            kid = self._key_id(k)
            if kid in ledger["exhausted"]:
                continue
            units_left = max(0, self.limits[k] - ledger["used"].get(kid, 0))
            searches_left += min(units_left // COST["search"],
                                 max(0, self.searches_per_day - int(ledger["searches"].get(kid, 0))))
        return {"day": ledger["day"], "keys": len(self.keys), "used": used, "total": total, "left": left,
                "searches": sum(int(n) for n in ledger["searches"].values()),
                "searchesPerDay": self.searches_per_day * len(self.keys),
                "searchesLeft": searches_left, "environment": self.environment}

    # ---- requests ------------------------------------------------------------------------------
    def get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.keys:
            raise NoKeysLeft("Añade YOUTUBE_API_KEY=tu_clave a .env (un solo proyecto de Google Cloud)")
        cache = self.dir / f"{endpoint}-{hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]}.json"
        if cache.is_file() and time.time() - cache.stat().st_mtime < TTL.get(endpoint, 3600):
            try:
                return json.loads(cache.read_text("utf-8"))
            except ValueError:
                pass
        cost = COST.get(endpoint, 1)
        for key in self.keys:
            kid = self._key_id(key)
            with _LOCK:
                ledger = self._ledger()
                if kid in ledger["exhausted"] or ledger["used"].get(kid, 0) + cost > self.limits[key]:
                    continue
                if endpoint == "search":
                    if int(ledger["searches"].get(kid, 0)) >= self.searches_per_day:
                        continue                         # this key's searches are spent: the next key
                    ledger["searches"][kid] = int(ledger["searches"].get(kid, 0)) + 1
                ledger["used"][kid] = ledger["used"].get(kid, 0) + cost
                self._save_ledger(ledger)
                self._journal({"endpoint": endpoint, "units": cost, "unitsUsed": ledger["used"][kid],
                               "searches": ledger["searches"].get(kid, 0), "searchesPerDay": self.searches_per_day})
            response = self.session.get(f"{API}/{endpoint}", params={**params, "key": key}, timeout=30)
            if response.status_code == 403:
                reasons = {e.get("reason") for e in _error(response).get("errors", [])}
                if reasons & QUOTA_ERRORS:
                    with _LOCK:
                        ledger = self._ledger()
                        ledger["exhausted"].append(kid)
                        self._save_ledger(ledger)
                    # Google says no while our count still had room: the project's real quota is lower than
                    # lab.units_per_key / searches_per_day (or someone else uses the key). Never raise them to fit.
                    self._journal({"endpoint": endpoint, "quotaExceeded": sorted(r for r in reasons if r),
                                   "localSearches": ledger["searches"].get(kid, 0), "localUnits": ledger["used"].get(kid, 0),
                                   "mismatch": True})
                    print(f"   API de YouTube: Google dice que no queda cuota ({', '.join(sorted(r for r in reasons if r))}) "
                          f"con {ledger['searches'].get(kid, 0)} búsquedas y {ledger['used'].get(kid, 0)} unidades contadas "
                          "aquí en esa clave: paso a la siguiente")
                    continue
            if response.status_code != 200:
                message = _error(response).get("message") or response.text[:200]
                raise RuntimeError(f"YouTube API {endpoint}: {response.status_code} {message}")
            data = response.json()
            _write(cache, json.dumps(data))
            return data
        raise NoKeysLeft(f"Cuota diaria de la API agotada en las {len(self.keys)} claves (se renueva {reset_text()})")

    # ---- building blocks -----------------------------------------------------------------------
    def search(self, query: str, *, days: int = 0, duration: str = "any", order: str = "viewCount",
               language: str = "", region: str = "", pages: int = 1, max_results: int = 50) -> list[str]:
        """Video ids for a query (up to 50 per page, 100 units per page whatever the size)."""

        params: dict[str, Any] = {"part": "id", "type": "video", "q": query, "maxResults": max(1, min(50, max_results)),
                                  "order": order}
        if days:
            after = datetime.now(timezone.utc) - timedelta(days=days)
            params["publishedAfter"] = after.strftime("%Y-%m-%dT%H:%M:%SZ")
        if duration in ("short", "medium", "long"):
            params["videoDuration"] = duration
        if language:
            params["relevanceLanguage"] = language
        if region:
            params["regionCode"] = region
        ids: list[str] = []
        for _ in range(max(1, pages)):
            data = self.get("search", params)
            ids += [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]
            if not data.get("nextPageToken"):
                break
            params = {**params, "pageToken": data["nextPageToken"]}
        return list(dict.fromkeys(ids))

    def videos(self, ids: list[str]) -> list[dict[str, Any]]:
        out = []
        for start in range(0, len(ids), 50):
            data = self.get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[start:start + 50])})
            for item in data.get("items", []):
                snippet, stats = item.get("snippet", {}), item.get("statistics", {})
                thumbs = snippet.get("thumbnails", {})
                out.append({
                    "id": item["id"], "title": snippet.get("title", ""), "channelId": snippet.get("channelId", ""),
                    "channel": snippet.get("channelTitle", ""), "published": snippet.get("publishedAt", ""),
                    "duration": parse_duration(item.get("contentDetails", {}).get("duration")),
                    "definition": item.get("contentDetails", {}).get("definition", ""),   # "hd" = 720p or more
                    "live": snippet.get("liveBroadcastContent", "none"),
                    "views": int(stats.get("viewCount", 0)), "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                    "thumbnail": (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url", ""),
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                    "description": str(snippet.get("description") or "")[:700],
                })
        return out

    def channels(self, ids: list[str] | None = None, *, lookup: dict[str, str] | None = None) -> list[dict[str, Any]]:
        batches = [{"id": ",".join(ids[s:s + 50])} for s in range(0, len(ids or []), 50)] if ids else [lookup or {}]
        out = []
        for batch in batches:
            data = self.get("channels", {"part": "snippet,statistics,contentDetails", **batch})
            for item in data.get("items", []):
                snippet, stats = item.get("snippet", {}), item.get("statistics", {})
                out.append({
                    "id": item["id"], "title": snippet.get("title", ""), "handle": snippet.get("customUrl", ""),
                    "created": snippet.get("publishedAt", ""),
                    "subscribers": int(stats.get("subscriberCount", 0)) if not stats.get("hiddenSubscriberCount") else None,
                    "videoCount": int(stats.get("videoCount", 0)), "viewCount": int(stats.get("viewCount", 0)),
                    "uploads": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
                    "thumbnail": (snippet.get("thumbnails", {}).get("default") or {}).get("url", ""),
                })
        return out

    def channel(self, handle_or_url: str) -> dict[str, Any]:
        found = self.channels(lookup=parse_channel(handle_or_url))
        if not found:
            raise ValueError(f"No encuentro el canal {handle_or_url}")
        return found[0]

    def uploads(self, playlist: str, count: int = 30) -> list[dict[str, Any]]:
        """Latest videos of a channel (uploads playlist → video details): ~2 units per 50."""

        ids: list[str] = []
        params: dict[str, Any] = {"part": "contentDetails", "playlistId": playlist, "maxResults": min(50, count)}
        while len(ids) < count:
            data = self.get("playlistItems", params)
            ids += [i["contentDetails"]["videoId"] for i in data.get("items", [])]
            if not data.get("nextPageToken"):
                break
            params = {**params, "pageToken": data["nextPageToken"]}
        return self.videos(ids[:count])

    def baseline(self, channel: dict[str, Any], count: int = 30, min_duration: int = 240) -> float | None:
        """Median views of the channel's recent long videos (cached a day)."""

        path = self.dir / "baselines.json"
        data = json.loads(path.read_text("utf-8")) if path.is_file() else {}
        cached = data.get(channel["id"])
        if cached and time.time() - cached["at"] < 24 * 3600:
            return cached["median"]
        long = [v["views"] for v in self.uploads(channel["uploads"], count) if v["duration"] >= min_duration] if channel.get("uploads") else []
        median = statistics.median(long) if long else None
        data[channel["id"]] = {"median": median, "at": time.time()}
        path.write_text(json.dumps(data), encoding="utf-8")
        return median
