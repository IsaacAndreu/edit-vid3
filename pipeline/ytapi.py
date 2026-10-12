"""YouTube Data API v3 with ONE production project: its daily quota, a search counter and a disk cache.

.env: YOUTUBE_API_KEY=key (the production project). Several projects to add up quota for the same tool is
against YouTube's API policy, so only one key is used: of an old YOUTUBE_API_KEYS=k1,k2,… list only the first,
with a warning. A separate development key (YOUTUBE_API_KEY_DEV) is used instead only when
YOUTUBE_API_ENTORNO=desarrollo — never both. More quota is asked for through Google's official quota form; when
granted, write "key:units" (YOUTUBE_API_KEY=abc:50000) and raise `lab.searches_per_day`.

The quota (10 000 units by default, `lab.units_per_key`) resets at midnight Pacific time. A search costs 100
units and also counts against its own daily limit (`lab.searches_per_day`, 100 by default); video, channel and
playlist lookups cost 1 per 50 items. Both counts are kept in cache/ytapi/quota.json. Answers are cached on disk
(search 12 h, stats 6 h, channel baselines 24 h) so repeating a search in the panel costs nothing.
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


def chosen_key(env: Any) -> tuple[str, str]:
    """(the one key to use, "producción" | "desarrollo"), from the environment: see the module's docstring."""

    if str(env("YOUTUBE_API_ENTORNO", required=False) or "").strip().lower() in ("desarrollo", "dev", "development"):
        return str(env("YOUTUBE_API_KEY_DEV", required=False) or "").strip(), "desarrollo"
    single = str(env("YOUTUBE_API_KEY", required=False) or "").strip()
    many = [k.strip() for k in str(env("YOUTUBE_API_KEYS", required=False) or "").split(",") if k.strip()]
    if single:
        if many and "both" not in _WARNED:
            _WARNED.add("both")
            print("   API de YouTube: uso YOUTUBE_API_KEY; YOUTUBE_API_KEYS se ignora (un solo proyecto)")
        return single, "producción"
    if len(many) > 1 and "many" not in _WARNED:
        _WARNED.add("many")
        print(f"   API de YouTube: solo uso la primera de las {len(many)} claves de YOUTUBE_API_KEYS. Varios proyectos "
              "para sumar cuota van contra la política de la API: deja una en YOUTUBE_API_KEY y pide más cuota a Google")
    return (many[0] if many else ""), "producción"


class YouTubeAPI:
    def __init__(self, ctx: RunContext, session: Any = None) -> None:
        self.ctx = ctx
        entry, self.environment = chosen_key(ctx.env)
        default = int(ctx.section("lab").get("units_per_key", 10000))
        self.searches_per_day = int(ctx.section("lab").get("searches_per_day", 100))
        self.keys, self.limits = [], {}
        if entry:                                    # "key" or "key:units" (a raised quota)
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
        data.setdefault("searches", 0)
        return data

    def _save_ledger(self, data: dict[str, Any]) -> None:
        _write(self.dir / "quota.json", json.dumps(data))

    @staticmethod
    def _key_id(key: str) -> str:   # never store the keys themselves
        return hashlib.sha256(key.encode()).hexdigest()[:10]

    def quota(self) -> dict[str, Any]:
        ledger = self._ledger()
        used = sum(ledger["used"].get(self._key_id(k), 0) for k in self.keys)
        total = sum(self.limits.values())
        left = sum(0 if self._key_id(k) in ledger["exhausted"] else max(0, self.limits[k] - ledger["used"].get(self._key_id(k), 0))
                   for k in self.keys)
        searches_left = max(0, self.searches_per_day - int(ledger.get("searches", 0)))
        return {"day": ledger["day"], "keys": len(self.keys), "used": used, "total": total, "left": left,
                "searches": int(ledger.get("searches", 0)), "searchesPerDay": self.searches_per_day,
                "searchesLeft": min(left // COST["search"], searches_left), "environment": self.environment}

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
                    if ledger["searches"] >= self.searches_per_day:
                        raise NoKeysLeft(f"Límite diario de búsquedas de la API ({self.searches_per_day}) "
                                         "alcanzado (se renueva a las 9:00 en España)")
                    ledger["searches"] += 1
                ledger["used"][kid] = ledger["used"].get(kid, 0) + cost
                self._save_ledger(ledger)
            response = self.session.get(f"{API}/{endpoint}", params={**params, "key": key}, timeout=30)
            if response.status_code == 403:
                reasons = {e.get("reason") for e in _error(response).get("errors", [])}
                if reasons & QUOTA_ERRORS:
                    with _LOCK:
                        ledger = self._ledger()
                        ledger["exhausted"].append(kid)
                        self._save_ledger(ledger)
                    continue
            if response.status_code != 200:
                message = _error(response).get("message") or response.text[:200]
                raise RuntimeError(f"YouTube API {endpoint}: {response.status_code} {message}")
            data = response.json()
            _write(cache, json.dumps(data))
            return data
        raise NoKeysLeft("Cuota diaria de la API agotada (se renueva a las 9:00 en España)")

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
