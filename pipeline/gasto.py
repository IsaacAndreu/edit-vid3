"""The studio's «Gasto de API» (Crecer ▾): what the APIs cost, per channel and per video.

Every paid call is in work/<slug>/costs.json (pipeline/costs.py). Averages count only finished videos (a video still
being made, or one that failed half way, would pull the average down); their spend shows apart as «en curso».
Work folders that are not videos (_radar, _ideas, _web…) go under «Otros» and never into a channel's average.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OTHERS = "Otros (radar, ideas, guiones…)"
NAMES = {"deepseek": "DeepSeek (guion y planos)", "openai": "OpenAI (juez)", "genaipro": "GenAIPro (voz)",
         "elevenlabs": "ElevenLabs (voz)", "anthropic": "Anthropic", "gemini": "Gemini", "serper": "Búsqueda web"}


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _seconds(root: Path, slug: str) -> float:
    timeline = _read(root / "work" / slug / "timeline.json") or {}
    return float(timeline.get("durationInFrames") or 0) / float(timeline.get("fps") or 30)


def youtube_quota(root: Path) -> dict[str, dict[str, Any]]:
    """YouTube Data API quota per video: every call is journaled (cache/ytapi/registro-<day>.jsonl, with the video and
    its units; search.list is 100 units). Videos made before the journal existed: the API searches their sourcing
    counted (candidates/_summary.json), at 101 units each (the search + its videos.list) — marked as estimated."""

    out: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "cache" / "ytapi").glob("registro-*.jsonl")):
        try:
            lines = path.read_text("utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not row.get("units"):
                continue
            entry = out.setdefault(str(row.get("slug") or "?"), {"searches": 0, "units": 0, "estimated": False})
            entry["units"] += int(row.get("units") or 0)
            entry["searches"] += row.get("endpoint") == "search"
    for summary in (root / "work").glob("*/candidates/_summary.json"):
        slug = summary.parent.parent.name
        if slug in out:
            continue
        searches = int(((_read(summary) or {}).get("youtubeRequests") or {}).get("search-api") or 0)
        if searches:
            out[slug] = {"searches": searches, "units": searches * 101, "estimated": True}
    return out


def report(root: Path, days: int = 30) -> dict[str, Any]:
    from .context import find_video
    from .housekeeping import is_done
    from .web import _channel_of

    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).date().isoformat()
    week = (now - timedelta(days=7)).date().isoformat()
    month = now.strftime("%Y-%m")
    per_day: dict[str, float] = {}
    providers: dict[str, float] = {}
    stages: dict[str, float] = {}
    videos = []
    quota = youtube_quota(root)
    for path in sorted((root / "work").glob("*/costs.json")):
        slug = path.parent.name
        entries = (_read(path) or {}).get("entries") or []
        if not entries:
            continue
        own: dict[str, float] = {}
        total = 0.0
        last = ""
        for entry in entries:
            usd = float(entry.get("usd") or 0)
            day = str(entry.get("at") or "")[:10]
            name = NAMES.get(str(entry.get("provider") or ""), str(entry.get("provider") or "otro"))
            total += usd
            own[name] = own.get(name, 0.0) + usd
            providers[name] = providers.get(name, 0.0) + usd
            stages[str(entry.get("stage") or "otro")] = stages.get(str(entry.get("stage") or "otro"), 0.0) + usd
            if day >= since:
                per_day[day] = per_day.get(day, 0.0) + usd
            last = max(last, day)
        is_video = not slug.startswith("_") and (find_video(root, slug).is_dir() or (root / "out" / slug).is_dir())
        channel = (_channel_of(root, find_video(root, slug)) or "sin canal") if is_video else OTHERS
        seconds = _seconds(root, slug) if is_video else 0.0
        videos.append({"slug": slug, "channel": channel, "usd": round(total, 4), "done": bool(is_video and is_done(root, slug)),
                       "minutes": round(seconds / 60, 1), "last": last,
                       "ytSearches": (quota.get(slug) or {}).get("searches"), "ytUnits": (quota.get(slug) or {}).get("units"),
                       "ytEstimated": bool((quota.get(slug) or {}).get("estimated")),
                       "providers": {k: round(v, 4) for k, v in sorted(own.items(), key=lambda kv: -kv[1])},
                       "week": round(sum(float(e.get("usd") or 0) for e in entries if str(e.get("at") or "")[:10] >= week), 4),
                       "month": round(sum(float(e.get("usd") or 0) for e in entries if str(e.get("at") or "")[:7] == month), 4)})

    def summary(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
        done = [r for r in rows if r["done"]]
        costs = [r["usd"] for r in done]
        minutes = sum(r["minutes"] for r in done)
        mix: dict[str, float] = {}
        for r in rows:
            for k, v in r["providers"].items():
                mix[k] = mix.get(k, 0.0) + v
        dearest = max(done, key=lambda r: r["usd"], default=None)
        units = [r["ytUnits"] for r in done if r.get("ytUnits")]
        searches = [r["ytSearches"] for r in done if r.get("ytSearches")]
        return {"channel": name, "total": round(sum(r["usd"] for r in rows), 2), "videos": len(rows), "done": len(done),
                "average": round(statistics.mean(costs), 3) if costs else None,
                "median": round(statistics.median(costs), 3) if costs else None,
                "perMinute": round(sum(costs) / minutes, 3) if minutes else None,
                "inProgress": round(sum(r["usd"] for r in rows if not r["done"]), 2),
                "week": round(sum(r["week"] for r in rows), 2), "month": round(sum(r["month"] for r in rows), 2),
                "dearest": {"slug": dearest["slug"], "usd": dearest["usd"]} if dearest else None,
                "providers": {k: round(v, 3) for k, v in sorted(mix.items(), key=lambda kv: -kv[1])},
                "ytUnits": round(statistics.mean(units)) if units else None,          # per finished video
                "ytSearches": round(statistics.mean(searches)) if searches else None,
                "ytKeys": round(statistics.mean(units) / 10000, 1) if units else None}

    by_channel: dict[str, list[dict[str, Any]]] = {}
    for row in videos:
        by_channel.setdefault(row["channel"], []).append(row)
    channels = [summary(rows, name) for name, rows in by_channel.items() if name != OTHERS]
    channels.sort(key=lambda c: -c["total"])
    made = [r for r in videos if r["channel"] != OTHERS]
    start = now.date() - timedelta(days=days - 1)
    return {"overall": summary(made, "Todos"), "channels": channels,
            "others": summary(by_channel.get(OTHERS, []), OTHERS) if OTHERS in by_channel else None,
            "total": round(sum(r["usd"] for r in videos), 2),
            "days": [{"day": (start + timedelta(days=i)).isoformat(),
                      "usd": round(per_day.get((start + timedelta(days=i)).isoformat(), 0.0), 3)} for i in range(days)],
            "providers": {k: round(v, 3) for k, v in sorted(providers.items(), key=lambda kv: -kv[1])},
            "stages": {k: round(v, 3) for k, v in sorted(stages.items(), key=lambda kv: -kv[1])},
            "videos": sorted(made, key=lambda r: r["last"], reverse=True),
            "ytToday": _quota_today(root)}


def _quota_today(root: Path) -> dict[str, Any] | None:
    try:
        from .context import RunContext
        from .ytapi import YouTubeAPI, reset_text

        api = YouTubeAPI(RunContext.create("_gasto", root=root))
        if not api.keys:
            return None
        q = api.quota()
        return {"used": q["used"], "total": q["total"], "searches": q["searches"], "searchesPerDay": q["searchesPerDay"],
                "keys": q["keys"], "reset": reset_text()}
    except Exception:
        return None
