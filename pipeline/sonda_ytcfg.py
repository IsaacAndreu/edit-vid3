"""Probe before switching on `sourcing.youtube.player_skip: [configs]`: does skipping the client configs keep the
same formats, and how many bytes does it save? Run on the server, through its own way out to YouTube:

    python -m pipeline.sonda_ytcfg [id_de_vídeo …]     (5 recent videos of the cache by default)

Each video is extracted twice through the configured proxy (its own sticky session, as the pipeline does): as today,
and with player_skip=[configs]. For each: formats, HLS formats, best height, whether a 720p avc1 stream is there, and
the MB by destination (www.youtube.com/ is the client config this saves). ~2 MB × 2 per video through the proxy.
The answer goes to out/_sonda_ytcfg.md: switch it on only when the formats are the same for every video.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from .context import PROJECT_ROOT, RunContext


def _summary(data: dict[str, Any], hosts: dict[str, int], seconds: float) -> dict[str, Any]:
    formats = data.get("formats") or []
    video = [f for f in formats if f.get("vcodec") not in (None, "none")]
    return {"formats": len(formats), "hls": sum(1 for f in formats if str(f.get("protocol") or "").startswith("m3u8")),
            "maxHeight": max([int(f.get("height") or 0) for f in video] or [0]),
            "avc720": any(str(f.get("vcodec") or "").startswith("avc1") and int(f.get("height") or 0) >= 720 for f in video),
            "mb": round(sum(hosts.values()) / 1e6, 2), "hosts": {k: round(v / 1e6, 2) for k, v in hosts.items()},
            "seconds": round(seconds, 1)}


def probe(root: Path, videos: list[str]) -> list[dict[str, Any]]:
    from .sourcing import youtube_source

    ctx = RunContext.create("_sonda_ytcfg", root=root)
    rows = []
    for skip in ([], ["configs"]):
        ctx.config.setdefault("sourcing", {}).setdefault("youtube", {})["player_skip"] = skip
        source = youtube_source(ctx)
        source.metrics_path = root / "out" / "_sonda_ytcfg.jsonl"
        try:
            for video in videos:
                source._local.video_id = video
                source._local.proxy_hosts = {}
                began = time.monotonic()
                try:
                    data = source._call("metadata", lambda: source._extract(f"https://www.youtube.com/watch?v={video}",
                                                                           {"skip_download": True}))
                    row = _summary(data, dict(getattr(source._local, "proxy_hosts", {}) or {}), time.monotonic() - began)
                except Exception as error:
                    row = {"error": str(error)[:160]}
                rows.append({"video": video, "skip": ",".join(skip) or "—", **row})
        finally:
            source.close()
    return rows


def markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Sonda: player_skip [configs]", "",
             "| Vídeo | player_skip | Formatos | HLS | Altura máx. | avc1 720p | MB por el proxy | s | Error |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['video']} | {r['skip']} | {r.get('formats', '—')} | {r.get('hls', '—')} | "
                     f"{r.get('maxHeight', '—')} | {r.get('avc720', '—')} | {r.get('mb', '—')} | {r.get('seconds', '—')} | "
                     f"{r.get('error', '')} |")
    same = {}
    for r in rows:
        same.setdefault(r["video"], []).append((r.get("formats"), r.get("hls"), r.get("maxHeight"), r.get("avc720")))
    equal = all(len(v) == 2 and v[0] == v[1] and v[0][0] for v in same.values())
    lines += ["", "**Mismos formatos con y sin [configs]: " + ("sí — se puede encender" if equal else
              "NO — déjalo apagado") + "**", ""]
    return "\n".join(lines) + "\n"


def recent_videos(root: Path, count: int = 5) -> list[str]:
    paths = sorted((root / "cache" / "videos").glob("*/ytdlp-info.json"), key=lambda p: -p.stat().st_mtime)
    return [p.parent.name for p in paths[:count]]


if __name__ == "__main__":
    videos = sys.argv[1:] or recent_videos(PROJECT_ROOT)
    text = markdown(probe(PROJECT_ROOT, videos))
    (PROJECT_ROOT / "out").mkdir(exist_ok=True)
    (PROJECT_ROOT / "out" / "_sonda_ytcfg.md").write_text(text, encoding="utf-8")
    print(text)
