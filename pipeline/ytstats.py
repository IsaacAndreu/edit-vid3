"""How YouTube treated us: sums up work/<slug>/youtube_downloads.jsonl (one line per request).

Per video it goes into diagnostico.md; across videos, `python main.py --youtube-stats [días]` prints and saves
out/_youtube_stats.md: requests, how many failed and why (403, bot check, 429, needs an account), retries, files
downloaded and their speed, with or without an account and with or without PO Token. A week of this on a server
says whether its IP works for this volume.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

ERRORS = {"403": "403 (rechazo)", "bot": "«no eres un bot»", "429": "429 (demasiadas)", "auth": "necesita cuenta",
          "unavailable": "vídeo no disponible", "timeout": "timeout", "other": "otros"}
DEFAULT_USD_PER_GB = 0.62        # sourcing.youtube.proxy_usd_per_gb: what the residential proxy charges per GB


def read(path: Path, since: float = 0.0) -> list[dict[str, Any]]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text("utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if float(row.get("ts") or 0) >= since:
            rows.append(row)
    return rows


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [r for r in rows if not str(r.get("action", "")).startswith("archivo ")]
    files = [r for r in rows if str(r.get("action", "")).startswith("archivo ")]
    done = [r for r in files if r.get("ok") and r.get("bytes")]
    errors: dict[str, int] = {}
    for r in calls:
        if not r.get("ok"):
            errors[r.get("error") or "other"] = errors.get(r.get("error") or "other", 0) + 1
    megabytes = sum(r["bytes"] for r in done) / 1e6
    seconds = sum(float(r.get("seconds") or 0) for r in done)
    return {
        "requests": len(calls),
        "ok": sum(1 for r in calls if r.get("ok")),
        "failed": sum(1 for r in calls if not r.get("ok")),
        "errors": errors,
        "retried": sum(1 for r in calls if r.get("ok") and int(r.get("attempt") or 1) > 1),
        "with_cookies": sum(1 for r in calls if r.get("cookies")),
        "pot": any(r.get("pot") for r in calls),
        "clients": sorted({c for r in calls for c in (r.get("clients") or [])}),
        "files": len(files),
        "files_ok": len(done),
        "files_failed": sum(1 for r in files if not r.get("ok")),
        "megabytes": round(megabytes, 1),
        "seconds_per_file": round(seconds / len(done), 1) if done else 0.0,
        "mbps": round(megabytes / seconds, 2) if seconds else 0.0,
        # our own queue before asking (slots + 1 req/s per proxy) vs the time YouTube took to answer
        "wait_avg": round(sum(float(r.get("wait") or 0) for r in calls) / len(calls), 2) if calls else 0.0,
        "answer_avg": round(sum(float(r.get("seconds") or 0) for r in calls) / len(calls), 2) if calls else 0.0,
    }


def by_proxy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How each way out to YouTube is doing (the server itself, or each home PC/laptop proxy)."""

    ways = sorted({str(r.get("proxy") or "") for r in rows})
    if ways == [""]:
        return []
    import re

    return [{"proxy": re.sub(r"//[^@/]*@", "//", way) or "servidor (directo)",          # never a password on screen
             **summary([r for r in rows if str(r.get("proxy") or "") == way])} for way in ways]


def lines(s: dict[str, Any]) -> list[str]:
    if not s["requests"] and not s["files"]:
        return []
    share = (100 * s["failed"] / s["requests"]) if s["requests"] else 0.0
    out = [
        f"- Peticiones a YouTube: {s['requests']} · bien {s['ok']} · fallidas {s['failed']} ({share:.1f} %)"
        + (f" · reintentadas con éxito {s['retried']}" if s["retried"] else ""),
        f"- Archivos descargados: {s['files_ok']} de {s['files']} ({s['megabytes']} MB · {s['seconds_per_file']} s de media · "
        f"{s['mbps']} MB/s)",
        f"- Con cuenta (cookies): {s['with_cookies']} peticiones · PO Token: {'sí' if s['pot'] else 'no'} · "
        f"clientes: {', '.join(s['clients']) or '—'}",
    ]
    if s["errors"]:
        out.append("- Errores: " + ", ".join(f"{ERRORS.get(k, k)} {n}" for k, n in sorted(s["errors"].items(), key=lambda kv: -kv[1])))
    return out


def proxy_summary(per_video: dict[str, list[dict[str, Any]]], finished: set[str],
                  usd_per_gb: float = DEFAULT_USD_PER_GB) -> list[dict[str, Any]]:
    """What each proxy carried: requests (≈ connections) and how many YouTube answered, the errors by kind, the GB
    (proxy_bytes of every row: yt-dlp's responses plus the ranges ffmpeg moved), the GB per finished video and what
    that cost at `usd_per_gb`. Only rows that name their proxy (written since the sticky sessions) count."""

    by_proxy: dict[str, dict[str, Any]] = {}
    for slug, rows in per_video.items():
        for row in rows:
            name = str(row.get("proxy") or "")
            if not name:
                continue
            entry = by_proxy.setdefault(name, {"proxy": name, "requests": 0, "ok": 0, "errors": {}, "bytes": 0,
                                               "videos": set(), "finished": set(), "sessions": set()})
            if row.get("session"):
                entry["sessions"].add(row["session"])
            entry["videos"].add(slug)
            if slug in finished:
                entry["finished"].add(slug)
            entry["bytes"] += int(row.get("proxy_bytes") or 0)
            if str(row.get("action", "")).startswith("archivo "):
                continue                                      # the file row repeats a download request
            entry["requests"] += 1
            if row.get("ok"):
                entry["ok"] += 1
            else:
                kind = row.get("error") or "other"
                entry["errors"][kind] = entry["errors"].get(kind, 0) + 1
    out = []
    for name, entry in sorted(by_proxy.items()):
        gb = entry["bytes"] / 1e9
        done = len(entry["finished"])
        out.append({
            "proxy": name,
            "requests": entry["requests"],
            "ok_share": round(100 * entry["ok"] / entry["requests"], 1) if entry["requests"] else 0.0,
            "errors": entry["errors"],
            "sessions": len(entry["sessions"]),
            "gb": round(gb, 3),
            "videos": len(entry["videos"]),
            "finished": done,
            "gb_per_finished": round(gb / done, 3) if done else None,
            "usd": round(gb * usd_per_gb, 2),
            "usd_per_gb": usd_per_gb,
        })
    return out


def proxy_lines(table: list[dict[str, Any]]) -> list[str]:
    if not table:
        return []
    out = ["## Proxy", "",
           f"Coste estimado a {table[0]['usd_per_gb']:.2f} $/GB (sourcing.youtube.proxy_usd_per_gb). «Peticiones» ≈ conexiones.", "",
           "| Proxy | Peticiones | Éxito | 403 | Bot | 429 | Timeout | Otros | Sesiones | GB | Vídeos terminados | GB por vídeo | $ |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in table:
        e = t["errors"]
        per_video = f"{t['gb_per_finished']:.3f}" if t["gb_per_finished"] is not None else "—"
        out.append(f"| {t['proxy']} | {t['requests']} | {t['ok_share']:.1f} % | {e.get('403', 0)} | {e.get('bot', 0)} | "
                   f"{e.get('429', 0)} | {e.get('timeout', 0)} | {e.get('other', 0) + e.get('unavailable', 0) + e.get('auth', 0)} | "
                   f"{t['sessions']} | {t['gb']:.3f} | {t['finished']}/{t['videos']} | {per_video} | {t['usd']:.2f} |")
    return out


def _usd_per_gb(root: Path) -> float:
    try:
        from .context import RunContext

        cfg = RunContext.create("_ytstats", root=root).section("sourcing").get("youtube") or {}
        return float(cfg.get("proxy_usd_per_gb", DEFAULT_USD_PER_GB))
    except Exception:
        return DEFAULT_USD_PER_GB


def report(root: Path, days: float = 7.0) -> Path:
    """Every video's requests of the last `days`, together and per video → out/_youtube_stats.md."""

    since = time.time() - days * 86400
    per_video = {path.parent.name: read(path, since) for path in sorted((root / "work").glob("*/youtube_downloads.jsonl"))}
    per_video = {slug: rows for slug, rows in per_video.items() if rows}
    everything = [row for rows in per_video.values() for row in rows]
    text = [f"# YouTube en los últimos {days:g} días", "", f"{len(per_video)} vídeos", "", *lines(summary(everything)), "",
            "| Vídeo | Peticiones | Fallidas | 403 | Bot | 429 | Archivos | MB/s | Con cuenta |", "|---|---|---|---|---|---|---|---|---|"]
    for slug, rows in per_video.items():
        s = summary(rows)
        e = s["errors"]
        text.append(f"| {slug} | {s['requests']} | {s['failed']} | {e.get('403', 0)} | {e.get('bot', 0)} | {e.get('429', 0)} | "
                     f"{s['files_ok']}/{s['files']} | {s['mbps']} | {s['with_cookies']} |")
    try:
        from .housekeeping import is_done

        finished = {slug for slug in per_video if is_done(root, slug)}
    except Exception:
        finished = set()
    proxies = proxy_summary(per_video, finished, _usd_per_gb(root))
    if proxies:
        text += ["", *proxy_lines(proxies)]
    ways = sorted({str(r["proxy"]) for r in everything if r.get("proxy")})
    if ways:                                       # several proxies: how each way out is doing
        text += ["", "## Por proxy", "", "| Proxy | Peticiones | Fallidas | Bot | Archivos | MB/s | s por archivo |",
                 "|---|---|---|---|---|---|---|"]
        for way in ways:
            s = summary([r for r in everything if r.get("proxy") == way])
            text.append(f"| {way} | {s['requests']} | {s['failed']} | {s['errors'].get('bot', 0)} | {s['files_ok']}/{s['files']} | "
                        f"{s['mbps']} | {s['seconds_per_file']} |")
    target = root / "out" / "_youtube_stats.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(text) + "\n", encoding="utf-8")
    return target
