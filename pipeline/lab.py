"""Research lab (TubeLab-style) on the YouTube Data API: outliers, channel analysis, saved videos.

- outliers(query): videos for a search that got many more views than their own channel usually
  gets (views / median of the channel's recent long videos). Filters: age, subscribers, duration.
- channel_report(handle): stats, cadence and each recent video's ratio.
- saved videos (out/_lab/guardados.json): what you mark in the panel; the daily ideas read them.
Used by the panel (`python main.py --panel`) and by `--ideas`.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from typing import Any

from .context import RunContext
from .ytapi import YouTubeAPI

SAVED = "out/_lab/guardados.json"


def _age_days(published: str) -> float:
    try:
        when = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.5, (datetime.now(timezone.utc) - when).total_seconds() / 86400)


def enrich(api: YouTubeAPI, videos: list[dict[str, Any]], *, baselines: bool = True) -> list[dict[str, Any]]:
    """Add channel subscribers, the channel's median views and the outlier ratio to each video."""

    channels = {c["id"]: c for c in api.channels(sorted({v["channelId"] for v in videos}))}
    out = []
    for video in videos:
        channel = channels.get(video["channelId"], {})
        median = api.baseline(channel) if baselines and channel else None
        age = _age_days(video["published"])
        out.append({
            **video,
            "subscribers": channel.get("subscribers"), "channelHandle": channel.get("handle", ""),
            "median": median, "ratio": round(video["views"] / median, 1) if median else None,
            "ageDays": round(age), "viewsPerDay": round(video["views"] / age),
            "viewsPerSub": round(video["views"] / channel["subscribers"], 1) if channel.get("subscribers") else None,
        })
    return out


def outliers(ctx: RunContext, query: str, *, days: int = 365, duration: str = "4plus", min_ratio: float = 0,
             max_subs: int = 0, min_views: int = 0, language: str = "", pages: int = 1,
             api: YouTubeAPI | None = None) -> list[dict[str, Any]]:
    """duration: "4plus" (any video of 4 min or more, the default), "medium" (4–20), "long" (20+), "any"."""

    api = api or YouTubeAPI(ctx)
    ids = api.search(query, days=days, duration=duration, language=language, pages=pages)
    shortest = 0 if duration == "any" else 240
    videos = [v for v in api.videos(ids) if v["views"] >= min_views and v["duration"] >= shortest]
    found = enrich(api, videos)
    found = [v for v in found
             if (not min_ratio or (v["ratio"] or 0) >= min_ratio)
             and (not max_subs or (v["subscribers"] is not None and v["subscribers"] <= max_subs))]
    return sorted(found, key=lambda v: (-(v["ratio"] or 0), -v["views"]))


def channel_report(ctx: RunContext, handle: str, count: int = 50, api: YouTubeAPI | None = None) -> dict[str, Any]:
    api = api or YouTubeAPI(ctx)
    channel = api.channel(handle)
    videos = api.uploads(channel["uploads"], count) if channel.get("uploads") else []
    long = [v for v in videos if v["duration"] >= 240]
    median = statistics.median(v["views"] for v in long) if long else None
    for video in videos:
        age = _age_days(video["published"])
        video.update(ratio=round(video["views"] / median, 1) if median else None, ageDays=round(age),
                     viewsPerDay=round(video["views"] / age), short=video["duration"] < 240)
    dates = sorted(_age_days(v["published"]) for v in long)
    gaps = [b - a for a, b in zip(dates, dates[1:])]
    return {**channel, "median": median, "longVideos": len(long), "shorts": len(videos) - len(long),
            "daysBetweenUploads": round(statistics.median(gaps), 1) if gaps else None,
            "videos": sorted(videos, key=lambda v: -(v["ratio"] or 0))}


def saved(ctx: RunContext) -> list[dict[str, Any]]:
    path = ctx.root / SAVED
    return json.loads(path.read_text("utf-8")) if path.is_file() else []


def save(ctx: RunContext, video: dict[str, Any], note: str = "") -> list[dict[str, Any]]:
    items = [v for v in saved(ctx) if v.get("id") != video.get("id")]
    keep = ("id", "title", "channel", "views", "ratio", "subscribers", "thumbnail", "url", "published", "duration")
    items.insert(0, {**{k: video.get(k) for k in keep}, "note": note[:500],
                     "savedAt": datetime.now().isoformat(timespec="seconds")})
    path = ctx.root / SAVED
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def unsave(ctx: RunContext, video_id: str) -> list[dict[str, Any]]:
    items = [v for v in saved(ctx) if v.get("id") != video_id]
    path = ctx.root / SAVED
    if path.parent.is_dir():
        path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items
