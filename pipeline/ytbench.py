"""Speed test of the ways to YouTube, from the studio (Estadísticas → «Probar velocidad de YouTube»).

For each way out (each home proxy, or the server itself) and each yt-dlp client (default, mweb, web_safari,
android_vr): how long the video details take, whether they bring the storyboard, the best height offered, and
how fast 10 s at 360p and 5 s at 1080p download — the same kind of piece the pipeline downloads. The answer says
which client to use and whether a proxy is the slow part. ~2 videos × 4 clients × each proxy: 5-15 minutes.

    python main.py --velocidad-youtube
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from .context import RunContext

CLIENTS = ["default", "mweb", "web_safari", "android_vr"]
VIDEOS = ["aqz-KE-bpKQ", "dQw4w9WgXcQ"]     # long-lived public videos with 1080p (Blender's Big Buck Bunny, a classic)
OUTPUT = "out/_youtube_prueba.json"


def _options(way: str, client: str, pot_url: str | None) -> dict[str, Any]:
    options: dict[str, Any] = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
                               "socket_timeout": 30, "retries": 2}
    if way:
        options["proxy"] = way
    if client != "default":
        options["extractor_args"] = {"youtube": {"player_client": [client]}}
    if pot_url:
        options.setdefault("extractor_args", {})["youtubepot-bgutilhttp"] = {"base_url": [pot_url]}
    return options


def _piece(options: dict[str, Any], video: str, fmt: str, start: float, end: float, folder: Path) -> dict[str, Any]:
    import yt_dlp
    from yt_dlp.utils import download_range_func

    target = folder / f"{video}-{start:.0f}"
    began = time.monotonic()
    with yt_dlp.YoutubeDL({**options, "format": fmt, "outtmpl": str(target) + ".%(ext)s",
                           "download_ranges": download_range_func(None, [(start, end)])}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video}", download=True)
    seconds = time.monotonic() - began
    size = sum(p.stat().st_size for p in folder.glob(f"{target.name}.*"))
    chosen = info.get("requested_formats") or [info]
    return {"seconds": round(seconds, 1), "mb": round(size / 1e6, 2), "mbps": round(size / 1e6 / max(seconds, 0.1), 2),
            "protocol": "+".join(sorted({str(f.get("protocol") or "?") for f in chosen})),
            "height": max(int(f.get("height") or 0) for f in chosen)}


def run(root: Path) -> dict[str, Any]:
    import yt_dlp

    from .sourcing.youtube import proxy_list

    cfg = RunContext.create("_prueba", root=root).section("sourcing").get("youtube", {})
    ways = proxy_list(os.environ.get("YOUTUBE_PROXY"), cfg.get("proxies"), cfg.get("proxy")) or [""]
    pot_url = str(cfg.get("pot_provider_url", "http://127.0.0.1:4416")).rstrip("/")
    rows: list[dict[str, Any]] = []
    folder = Path(tempfile.mkdtemp(prefix="ytprueba-"))
    try:
        for way in ways:
            name = way.split("@")[-1] if way else "servidor (directo)"
            for client in CLIENTS:
                for video in VIDEOS:
                    row: dict[str, Any] = {"way": name, "client": client, "video": video}
                    options = _options(way, client, pot_url)
                    try:
                        began = time.monotonic()
                        with yt_dlp.YoutubeDL({**options, "skip_download": True}) as ydl:
                            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video}", download=False)
                        formats = info.get("formats") or []
                        row.update({"details_s": round(time.monotonic() - began, 1),
                                    "storyboard": any(str(f.get("format_id", "")).startswith("sb") for f in formats),
                                    "max_height": max([int(f.get("height") or 0) for f in formats
                                                       if f.get("vcodec") not in (None, "none")] or [0])})
                        row["p360"] = _piece(options, video, "bv*[height<=360]/b[height<=360]", 30, 40, folder)
                        row["p1080"] = _piece(options, video, "bv*[height<=1080][height>=720]/bv*[height<=1080]", 60, 65, folder)
                        row["ok"] = True
                    except Exception as error:             # one failing client is an answer too
                        row.update({"ok": False, "error": str(error).splitlines()[0][:200]})
                    print(f"{name} · {client} · {video}: " + (
                        f"detalles {row['details_s']} s · 360p {row['p360']['mbps']} MB/s ({row['p360']['protocol']}) · "
                        f"1080p {row['p1080']['mbps']} MB/s" if row.get("ok") else f"falló: {row.get('error')}"), flush=True)
                    rows.append(row)
                    shutil.rmtree(folder, ignore_errors=True)
                    folder.mkdir(parents=True, exist_ok=True)
                    time.sleep(2)                          # gentle: never a burst against YouTube
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    result = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows, "summary": summary(rows)}
    target = root / OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per way and client: medians, and how many videos worked; the fastest working one first."""

    out = []
    for key in dict.fromkeys((r["way"], r["client"]) for r in rows):
        group = [r for r in rows if (r["way"], r["client"]) == key]
        good = [r for r in group if r.get("ok")]
        med = lambda values: round(statistics.median(values), 2) if values else None  # noqa: E731
        out.append({"way": key[0], "client": key[1], "ok": len(good), "of": len(group),
                    "details_s": med([r["details_s"] for r in good]),
                    "mbps360": med([r["p360"]["mbps"] for r in good]),
                    "mbps1080": med([r["p1080"]["mbps"] for r in good]),
                    "protocol": (good[0]["p360"]["protocol"] if good else None),
                    "storyboard": all(r.get("storyboard") for r in good) if good else False,
                    "error": next((r.get("error") for r in group if not r.get("ok")), None)})
    return sorted(out, key=lambda s: (-s["ok"], -(s["mbps360"] or 0)))
