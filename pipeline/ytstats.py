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
          "unavailable": "vídeo no disponible", "other": "otros"}


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
    }


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
    target = root / "out" / "_youtube_stats.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(text) + "\n", encoding="utf-8")
    return target
