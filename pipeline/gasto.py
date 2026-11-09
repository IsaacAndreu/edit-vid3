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


_PROXY_CACHE: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}


def _proxy_of(path: Path, mb_per_request: float) -> dict[str, Any]:
    """One video's request log, added up per proxy kind: the bytes the proxy really carried («proxy_bytes», written
    since the residential proxy), and the old metadata-proxy requests that have no size (estimated with
    `mb_per_request`). Kept by the file's size and time: the logs are long and the page is opened often."""

    try:
        stat = path.stat()
    except OSError:
        return {}
    key = (stat.st_size, stat.st_mtime_ns)
    hit = _PROXY_CACHE.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    out = {"requests": 0, "metadataBytes": 0, "paidBytes": 0, "estimatedMb": 0.0, "since": None, "months": {}}
    try:
        lines = path.read_text("utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        if '"proxy"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        name = row.get("proxy")
        if not name:
            continue
        if not str(row.get("action", "")).startswith("archivo "):   # the file row repeats a download request
            out["requests"] += 1
        ts = row.get("ts") or 0
        out["since"] = min(out["since"] or ts, ts)
        month = datetime.fromtimestamp(float(ts or 0), timezone.utc).strftime("%Y-%m")
        per = out["months"].setdefault(month, {"metadataBytes": 0, "paidBytes": 0, "estimatedMb": 0.0})
        if "proxy_bytes" in row:
            kind = "metadataBytes" if name == "metadatos" else "paidBytes"
            out[kind] += int(row.get("proxy_bytes") or 0)
            per[kind] += int(row.get("proxy_bytes") or 0)
        elif name == "metadatos":
            out["estimatedMb"] += mb_per_request
            per["estimatedMb"] += mb_per_request
    _PROXY_CACHE[str(path)] = (key, out)
    return out


def proxy_usage(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    """What the proxies cost each video, from its request log (work/<slug>/youtube_downloads.jsonl). Rows that carry
    «proxy_bytes» are measured: GB × `proxy_usd_per_gb` (the residential proxy) or × `metadata_proxy_usd_per_gb`
    (the old metadata proxy). The old metadata-proxy rows have no size: GB ≈ requests × `metadata_proxy_mb_per_request`
    («estimated»: the page marks those with ≈)."""

    from .context import RunContext
    from .ytstats import DEFAULT_USD_PER_GB

    try:
        cfg = (RunContext.create("_gasto", root=root).section("sourcing").get("youtube") or {})
    except Exception:
        cfg = {}
    mb = float(cfg.get("metadata_proxy_mb_per_request", 0.6))
    per_gb = float(cfg.get("metadata_proxy_usd_per_gb", 4.5))
    paid_gb = float(cfg.get("proxy_usd_per_gb", DEFAULT_USD_PER_GB))
    out: dict[str, dict[str, Any]] = {}
    for path in (root / "work").glob("*/youtube_downloads.jsonl"):
        got = _proxy_of(path, mb)
        if not got or not got["requests"]:
            continue
        metadata_gb = got["metadataBytes"] / 1e9 + got["estimatedMb"] / 1024
        gb = metadata_gb + got["paidBytes"] / 1e9
        out[path.parent.name] = {"requests": got["requests"], "mb": round(gb * 1024, 1), "gb": round(gb, 3),
                                 "usd": round(metadata_gb * per_gb + got["paidBytes"] / 1e9 * paid_gb, 3),
                                 "estimated": bool(got["estimatedMb"]), "since": got["since"]}
    return out, {"mbPerRequest": mb, "usdPerGb": paid_gb, "metadataUsdPerGb": per_gb}


def _voice_rate(root: Path) -> float:
    from .context import RunContext
    from .tts import USD_PER_1K_CHARS

    try:
        return float(RunContext.create("_gasto", root=root).section("tts").get("usd_per_1k_chars", USD_PER_1K_CHARS))
    except Exception:
        return USD_PER_1K_CHARS


def report(root: Path, days: int = 30, channels: set[str] | None = None) -> dict[str, Any]:
    """The whole spend page; with `channels`, only those channels' videos (a partner's own page: nothing of the
    others', no «Otros», no server-wide quota)."""
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
    judge_calls = judge_usd = voice_chars = voice_usd = 0.0     # what the reused things cost when paid
    stage_time: dict[str, float] = {}
    from . import ahorro, tiempos

    quota = youtube_quota(root)
    proxy, proxy_rates = proxy_usage(root)
    if channels is not None:
        from .context import find_video as _find
        from .web import _channel_of as _of

        def _mine(slug: str) -> bool:
            try:
                return _of(root, _find(root, slug)) in channels
            except Exception:
                return False

        proxy = {k: v for k, v in proxy.items() if _mine(k)}
    voice_rate = _voice_rate(root)
    for path in sorted((root / "work").glob("*/costs.json")):
        slug = path.parent.name
        entries = (_read(path) or {}).get("entries") or []
        if not entries:
            continue
        is_video = not slug.startswith("_") and (find_video(root, slug).is_dir() or (root / "out" / slug).is_dir())
        channel = (_channel_of(root, find_video(root, slug)) or "sin canal") if is_video else OTHERS
        if channels is not None and channel not in channels:
            continue
        own: dict[str, float] = {}
        total = 0.0
        last = ""
        for entry in entries:
            usd = float(entry.get("usd") or 0)
            chars = float((entry.get("details") or {}).get("chars") or 0)
            if entry.get("provider") == "genaipro" and not usd and chars:
                usd = chars / 1000 * voice_rate       # written at 0.00 $ before the voice had a price
            day = str(entry.get("at") or "")[:10]
            name = NAMES.get(str(entry.get("provider") or ""), str(entry.get("provider") or "otro"))
            total += usd
            own[name] = own.get(name, 0.0) + usd
            providers[name] = providers.get(name, 0.0) + usd
            stages[str(entry.get("stage") or "otro")] = stages.get(str(entry.get("stage") or "otro"), 0.0) + usd
            if day >= since:
                per_day[day] = per_day.get(day, 0.0) + usd
            last = max(last, day)
            if entry.get("stage") == "judge" and entry.get("provider") == "openai":
                judge_calls += 1
                judge_usd += usd
            if entry.get("provider") == "genaipro" and chars:
                voice_chars += chars
                voice_usd += usd
        seconds = _seconds(root, slug) if is_video else 0.0
        stages_here = tiempos.stage_seconds(path.parent)
        done_here = bool(is_video and is_done(root, slug))
        if done_here:
            for name, secs in stages_here.items():
                stage_time[name] = stage_time.get(name, 0.0) + secs
        videos.append({"slug": slug, "workSeconds": round(sum(stages_here.values())), "reused": ahorro.totals(path.parent), "channel": channel, "usd": round(total, 4), "done": bool(is_video and is_done(root, slug)),
                       "minutes": round(seconds / 60, 1), "last": last,
                       "ytSearches": (quota.get(slug) or {}).get("searches"), "ytUnits": (quota.get(slug) or {}).get("units"),
                       "ytEstimated": bool((quota.get(slug) or {}).get("estimated")),
                       "proxyRequests": (proxy.get(slug) or {}).get("requests"), "proxyUsd": (proxy.get(slug) or {}).get("usd"),
                       "proxyGb": (proxy.get(slug) or {}).get("gb"), "proxyEstimated": bool((proxy.get(slug) or {}).get("estimated")),
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
        proxied = [r["proxyUsd"] for r in done if r.get("proxyUsd")]
        proxied_gb = [r["proxyGb"] for r in done if r.get("proxyUsd")]
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
                "ytKeys": round(statistics.mean(units) / 10000, 1) if units else None,
                "proxyUsd": round(statistics.mean(proxied), 3) if proxied else None,
                "proxyGb": round(statistics.mean(proxied_gb), 3) if proxied_gb else None}

    by_channel: dict[str, list[dict[str, Any]]] = {}
    for row in videos:
        by_channel.setdefault(row["channel"], []).append(row)
    channels = [summary(rows, name) for name, rows in by_channel.items() if name != OTHERS]
    channels.sort(key=lambda c: -c["total"])
    made = [r for r in videos if r["channel"] != OTHERS]
    start = now.date() - timedelta(days=days - 1)
    # what reusing saved, priced with what the same thing really cost here
    per_verdict = judge_usd / judge_calls if judge_calls else 0.0
    per_char = voice_usd / voice_chars if voice_chars else 0.0
    verdicts = sum(r["reused"].get("judge", 0) for r in videos)
    reused_chars = sum(r["reused"].get("voice", 0) for r in videos)
    for r in videos:
        r["savedUsd"] = round(r["reused"].get("judge", 0) * per_verdict + r["reused"].get("voice", 0) * per_char, 4)
    saved = verdicts * per_verdict + reused_chars * per_char
    spent = sum(r["usd"] for r in videos)
    finished = [r for r in made if r["done"] and r["workSeconds"]]
    savings = {"usd": round(saved, 2), "share": round(saved / (saved + spent), 3) if saved + spent else 0.0,
               "verdicts": int(verdicts), "verdictsUsd": round(verdicts * per_verdict, 2),
               "perVerdict": round(per_verdict, 5), "voiceChars": int(reused_chars),
               "voiceUsd": round(reused_chars * per_char, 3), "perKChars": round(per_char * 1000, 4)}
    pipeline = {"videos": len(finished), "seconds": sum(r["workSeconds"] for r in finished),
                "usd": round(sum(r["usd"] for r in finished), 2),
                "averageSeconds": round(statistics.mean(r["workSeconds"] for r in finished)) if finished else None,
                "averageUsd": round(statistics.mean(r["usd"] for r in finished), 3) if finished else None,
                "stages": [{"stage": k, "name": tiempos.NAMES.get(k, k), "seconds": round(v)}
                           for k, v in sorted(stage_time.items(), key=lambda kv: -kv[1]) if v >= 1]}
    today = now.date().isoformat()
    return {"overall": summary(made, "Todos"), "channels": channels, "today": round(per_day.get(today, 0.0), 2),
            "savings": savings, "pipeline": pipeline,
            "others": summary(by_channel.get(OTHERS, []), OTHERS) if OTHERS in by_channel else None,
            "total": round(sum(r["usd"] for r in videos), 2),
            "days": [{"day": (start + timedelta(days=i)).isoformat(),
                      "usd": round(per_day.get((start + timedelta(days=i)).isoformat(), 0.0), 3)} for i in range(days)],
            "providers": {k: round(v, 3) for k, v in sorted(providers.items(), key=lambda kv: -kv[1])},
            "stages": {k: round(v, 3) for k, v in sorted(stages.items(), key=lambda kv: -kv[1])},
            "videos": sorted(made, key=lambda r: r["last"], reverse=True),
            "ytToday": _quota_today(root) if channels is None else None,
            "proxy": {**proxy_rates, "videos": len(proxy), "requests": sum(p["requests"] for p in proxy.values()),
                      "mb": round(sum(p["mb"] for p in proxy.values()), 1),
                      "gb": round(sum(p["gb"] for p in proxy.values()), 2),
                      "estimatedVideos": sum(1 for p in proxy.values() if p["estimated"]),
                      "usd": round(sum(p["usd"] for p in proxy.values()), 2),
                      "since": min((p["since"] for p in proxy.values() if p["since"]), default=None)} if proxy else None}


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


def invoices(root: Path, months: int = 3) -> list[dict[str, Any]]:
    """What each person owes per month: API and voice (costs.json, by the day of each call), the proxy (the GB each
    of their videos carried that month × its price) and their share of the server (`server_usd_month` in Ajustes)
    by hours of work: the stages each of their videos ran that month over every video's. A channel is a partner's
    when usuarios.py says so; everything else (and «Otros»: radar, ideas…) is yours ("")."""

    from .budget import settings as _settings
    from .context import find_video
    from .usuarios import owners
    from .web import _channel_of

    now = datetime.now(timezone.utc)
    wanted: list[str] = []
    year, month = now.year, now.month
    for _ in range(months):
        wanted.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    whose = owners(root)
    server_usd = float(_settings(root).get("server_usd_month") or 0)
    voice_rate = _voice_rate(root)
    _, rates = proxy_usage(root)
    mb = rates["mbPerRequest"]
    table: dict[str, dict[str, dict[str, Any]]] = {m: {} for m in wanted}
    hours: dict[str, float] = {m: 0.0 for m in wanted}

    def person(m: str, who: str) -> dict[str, Any]:
        return table[m].setdefault(who, {"who": who, "api": 0.0, "voice": 0.0, "proxyGb": 0.0, "proxyUsd": 0.0,
                                         "hours": 0.0, "videos": {}})

    def video_row(entry: dict[str, Any], slug: str, channel: str) -> dict[str, Any]:
        return entry["videos"].setdefault(slug, {"slug": slug, "channel": channel, "api": 0.0, "voice": 0.0,
                                                 "proxyGb": 0.0, "proxyUsd": 0.0, "hours": 0.0})

    slugs = {p.parent.name for p in (root / "work").glob("*/costs.json")} | \
            {p.parent.name for p in (root / "work").glob("*/youtube_downloads.jsonl")} | \
            {p.parent.parent.name for p in (root / "work").glob("*/.stages")}
    for slug in sorted(slugs):
        work = root / "work" / slug
        is_video = not slug.startswith("_") and (find_video(root, slug).is_dir() or (root / "out" / slug).is_dir())
        channel = (_channel_of(root, find_video(root, slug)) or "sin canal") if is_video else OTHERS
        who = whose.get(channel, "")
        last = ""
        for entry in (_read(work / "costs.json") or {}).get("entries") or []:
            m = str(entry.get("at") or "")[:7]
            last = max(last, m)
            if m not in table:
                continue
            usd = float(entry.get("usd") or 0)
            chars = float((entry.get("details") or {}).get("chars") or 0)
            voice = entry.get("provider") == "genaipro"
            if voice and not usd and chars:
                usd = chars / 1000 * voice_rate
            row = person(m, who)
            row["voice" if voice else "api"] += usd
            video_row(row, slug, channel)["voice" if voice else "api"] += usd
        got = _proxy_of(work / "youtube_downloads.jsonl", mb) if (work / "youtube_downloads.jsonl").is_file() else {}
        for m, part in (got.get("months") or {}).items():
            if m not in table:
                continue
            metadata_gb = part["metadataBytes"] / 1e9 + part["estimatedMb"] / 1024
            gb = metadata_gb + part["paidBytes"] / 1e9
            usd = metadata_gb * rates["metadataUsdPerGb"] + part["paidBytes"] / 1e9 * rates["usdPerGb"]
            row = person(m, who)
            row["proxyGb"] += gb
            row["proxyUsd"] += usd
            v = video_row(row, slug, channel)
            v["proxyGb"] += gb
            v["proxyUsd"] += usd
        stages = work / ".stages"
        for path in (stages.glob("*.json") if stages.is_dir() else []):
            info = _read(path) or {}
            m = str(info.get("completedAt") or "")[:7] or last
            if m not in table:
                continue
            h = float(info.get("seconds") or 0) / 3600
            hours[m] += h
            row = person(m, who)
            row["hours"] += h
            video_row(row, slug, channel)["hours"] += h
    out = []
    for m in wanted:
        people = []
        for entry in sorted(table[m].values(), key=lambda e: (e["who"] != "", e["who"])):
            share = server_usd * entry["hours"] / hours[m] if hours[m] else 0.0
            videos = sorted(entry["videos"].values(), key=lambda v: v["slug"])
            for v in videos:
                v["server"] = server_usd * v["hours"] / hours[m] if hours[m] else 0.0
                v["total"] = v["api"] + v["voice"] + v["proxyUsd"] + v["server"]
                for k in ("api", "voice", "proxyUsd", "server", "total"):
                    v[k] = round(v[k], 3)
                v["proxyGb"], v["hours"] = round(v["proxyGb"], 3), round(v["hours"], 2)
            people.append({"who": entry["who"], "api": round(entry["api"], 2), "voice": round(entry["voice"], 2),
                           "proxyGb": round(entry["proxyGb"], 2), "proxyUsd": round(entry["proxyUsd"], 2),
                           "hours": round(entry["hours"], 1), "server": round(share, 2),
                           "total": round(entry["api"] + entry["voice"] + entry["proxyUsd"] + share, 2),
                           "videos": videos})
        out.append({"month": m, "serverUsd": server_usd, "hours": round(hours[m], 1), "people": people})
    return out


def invoice_csv(month: dict[str, Any], who: str) -> str:
    """One person's month as a spreadsheet: a line per video, then the server share and the total."""

    import csv
    import io

    entry = next((p for p in month["people"] if p["who"] == who), None)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["mes", "vídeo", "canal", "API $", "voz $", "proxy GB", "proxy $", "horas", "servidor $", "total $"])
    if entry:
        for v in entry["videos"]:
            writer.writerow([month["month"], v["slug"], v["channel"], v["api"], v["voice"], v["proxyGb"], v["proxyUsd"],
                             v["hours"], v["server"], v["total"]])
        writer.writerow([month["month"], "TOTAL", "", entry["api"], entry["voice"], entry["proxyGb"], entry["proxyUsd"],
                         entry["hours"], entry["server"], entry["total"]])
    return buffer.getvalue()
