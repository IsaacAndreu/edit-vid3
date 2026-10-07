"""The studio's «Estadísticas»: how each video does on YouTube and what it took to make it.

- YouTube (the videos marked as uploaded with their link, or found on your channel): views, views per day, likes and
  comments per 1,000 views, views at 48 h and 7 days (pipeline/agenda.py records them) and how it compares with the
  median of the same channel. Fresh from the YouTube Data API (1 quota unit per 50 videos), cached for an hour.
- Production (every finished video): API cost, machine time, length, shots and cuts per minute, what is on screen
  (YouTube clips, photos, stock, generated images, graphics) and your «Errores» labels.
- Per channel: videos out, total and median views, the best one, average cost and cost per 1,000 views.

Retention, CTR and impressions are not in the public API: they need YouTube Analytics with your channel's login.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

CACHE = "out/_estadisticas.json"
CACHE_SECONDS = 3600


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _youtube(root: Path, ids: list[str], refresh: bool) -> dict[str, dict[str, Any]]:
    cache = _read(root / CACHE) or {}
    if not refresh and time.time() - float(cache.get("at") or 0) < CACHE_SECONDS and set(ids) <= set(cache.get("videos", {})):
        return cache["videos"]
    try:
        from .context import RunContext
        from .ytapi import YouTubeAPI

        api = YouTubeAPI(RunContext.create("_estadisticas", root=root))
        if not api.keys or not ids:
            return cache.get("videos", {})
        found = {v["id"]: {k: v.get(k) for k in ("views", "likes", "comments", "thumbnail", "title", "published", "duration")}
                 for v in api.videos(ids)}
    except Exception as error:
        print(f"(Estadísticas de YouTube no consultadas: {str(error)[:120]})")
        return cache.get("videos", {})
    path = root / CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": time.time(), "videos": found}, ensure_ascii=False), encoding="utf-8")
    return found


CATEGORY = {"youtube": "youtube", "wikimedia": "fotos", "openverse": "fotos", "pixabay": "stock", "pexels": "stock",
            "web": "fotos", "generated": "generadas"}


def production(root: Path, slug: str) -> dict[str, Any]:
    work, out = root / "work" / slug, root / "out" / slug
    costs = _read(work / "costs.json") or {}
    stages = sorted((work / ".stages").glob("*.json")) if (work / ".stages").is_dir() else []
    seconds = sum(float((_read(p) or {}).get("seconds") or 0) for p in stages)
    timeline = _read(work / "timeline.json") or {}
    fps = float(timeline.get("fps") or 30)
    duration = float(timeline.get("durationInFrames") or 0) / fps
    manifest = (_read(out / "manifest.json") or {}).get("shots", [])
    mix: dict[str, int] = {}
    for shot in manifest:
        kind = CATEGORY.get(str(shot.get("source") or ""), "gráficos" if not shot.get("media") else "otros")
        mix[kind] = mix.get(kind, 0) + 1
    labels = {"correcta": 0, "incorrecta": 0, "dudosa": 0}
    try:
        from .feedback import labels as all_labels

        for key, entry in all_labels(root).items():
            if key.startswith(f"{slug}/") and entry.get("verdict") in labels:
                labels[entry["verdict"]] += 1
    except Exception:
        pass
    shots = len(manifest) or len(timeline.get("shots", []))
    return {"usd": round(float(costs.get("totalUsd") or 0), 2), "minutes": round(seconds / 60),
            "duration": round(duration), "shots": shots, "cutsPerMin": round(shots / (duration / 60), 1) if duration else 0,
            "mix": mix, "labels": labels}


def _age_days(published: str) -> float:
    try:
        return max(0.1, (time.time() - datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()) / 86400)
    except (ValueError, AttributeError):
        return 0.0


def report(root: Path, refresh: bool = False) -> dict[str, Any]:
    from . import agenda

    listed = agenda.videos(root)
    history = (agenda.load(root).get("views") or {})
    ids = {v["slug"]: agenda._video_id(v["url"]) for v in listed if v["status"] == "subido" and v["url"]}
    stats = _youtube(root, sorted({i for i in ids.values() if i}), refresh)
    rows = []
    for video in listed:
        if video["status"] not in ("hecho", "subido"):
            continue
        row = {"slug": video["slug"], "channel": video["channel"], "title": video["title"] or video["slug"],
               "status": video["status"], "publishedDay": video["published"], "url": video["url"],
               "production": production(root, video["slug"])}
        yt = stats.get(ids.get(video["slug"]) or "")
        if yt:
            age = _age_days(yt.get("published") or "")
            views = int(yt.get("views") or 0)
            row["youtube"] = {
                "views": views, "likes": int(yt.get("likes") or 0), "comments": int(yt.get("comments") or 0),
                "ageDays": round(age, 1), "perDay": round(views / age) if age else 0,
                "likesPer1k": round(1000 * int(yt.get("likes") or 0) / views, 1) if views else 0,
                "commentsPer1k": round(1000 * int(yt.get("comments") or 0) / views, 1) if views else 0,
                "at48h": (history.get(video["slug"]) or {}).get("48h"), "at7d": (history.get(video["slug"]) or {}).get("7d"),
                "thumbnail": yt.get("thumbnail") or "", "title": yt.get("title") or ""}
        rows.append(row)
    channels: dict[str, dict[str, Any]] = {}
    for row in rows:
        c = channels.setdefault(row["channel"], {"channel": row["channel"], "made": 0, "published": 0, "views": 0,
                                                 "usd": 0.0, "_views": []})
        c["made"] += 1
        c["usd"] += row["production"]["usd"]
        if row.get("youtube"):
            c["published"] += 1
            c["views"] += row["youtube"]["views"]
            c["_views"].append(row["youtube"]["views"])
    for c in channels.values():
        median = statistics.median(c["_views"]) if c["_views"] else 0
        c["median"] = int(median)
        c["usdPerVideo"] = round(c["usd"] / c["made"], 2) if c["made"] else 0
        c["usdPer1kViews"] = round(1000 * c["usd"] / c["views"], 3) if c["views"] else None
        best = max((r for r in rows if r["channel"] == c["channel"] and r.get("youtube")),
                   key=lambda r: r["youtube"]["views"], default=None)
        c["best"] = {"title": best["title"], "views": best["youtube"]["views"]} if best else None
        c["usd"] = round(c["usd"], 2)
        del c["_views"]
        for row in rows:
            if row["channel"] == c["channel"] and row.get("youtube") and median:
                row["youtube"]["vsChannel"] = round(row["youtube"]["views"] / median, 2)
    return {"videos": rows, "channels": sorted(channels.values(), key=lambda c: -c["views"]),
            "fetched": (_read(root / CACHE) or {}).get("at")}
