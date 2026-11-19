"""Probe (fase 3.6, experimental): which resources of a video extracted through the paid proxy answer when fetched
STRAIGHT from this server, without the proxy (its GB not paid)?

    python -m pipeline.sonda_directo [id_de_vídeo]      (Big Buck Bunny by default)

One extraction through the configured way out (the video's sticky session, ~1-3 MB of proxy), then one small direct
request for each kind of resource: a storyboard sheet, the subtitles (json3), an HLS manifest, its first segment, and
the first 64 KB of an HTTPS video stream. The code assumes stream URLs are bound to the IP that extracted them (and
an earlier test gave 1 % success extracting through one IP and downloading through another): this says, resource by
resource, whether that holds here. Nothing in the pipeline changes with it. Writes out/_sonda_directo.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

from .context import PROJECT_ROOT, RunContext


def _direct(url: str, headers: dict[str, str] | None = None, first: int | None = None) -> dict[str, Any]:
    session = requests.Session()
    session.trust_env = False                          # never the proxy, explicit or inherited
    wanted = {**(headers or {}), **({"Range": f"bytes=0-{first - 1}"} if first else {})}
    try:
        with session.get(url, headers=wanted, timeout=30, stream=True) as response:
            body = b""
            for block in response.iter_content(64 * 1024):
                body += block
                if len(body) >= (first or 256 * 1024):
                    break
            return {"status": response.status_code, "bytes": len(body), "text": body[:4096]}
    except requests.RequestException as error:
        return {"status": None, "bytes": 0, "error": type(error).__name__, "text": b""}


def probe(root: Path, video: str) -> list[dict[str, Any]]:
    from .sourcing import youtube_source
    from .sourcing.youtube import parse_media_playlist

    ctx = RunContext.create("_sonda_directo", root=root)
    source = youtube_source(ctx)
    source.metrics_path = root / "out" / "_sonda_directo.jsonl"
    rows: list[dict[str, Any]] = []
    try:
        info = source.info(video)                                  # through the proxy, as the pipeline does
        full = json.loads(source._fresh_full_info(video).read_text("utf-8"))
    finally:
        source.close()
    board = (info.get("storyboard") or {}).get("urls") or []
    if board:
        rows.append({"resource": "miniaturas del storyboard (i.ytimg.com)", **_direct(board[0])})
    captions = next(iter((info.get("captions") or {}).values()), None)
    if captions:
        rows.append({"resource": "subtítulos json3 (youtube.com/api/timedtext)", **_direct(captions)})
    formats = full.get("formats") or []
    hls = next((f for f in formats if str(f.get("protocol") or "").startswith("m3u8")), None)
    if hls:
        headers = {k: str(v) for k, v in (hls.get("http_headers") or {}).items()}
        manifest = _direct(str(hls["url"]), headers)
        rows.append({"resource": "manifiesto HLS", **manifest})
        if manifest.get("status") == 200:
            segments, _ = parse_media_playlist(manifest["text"].decode("utf-8", "replace"), str(hls["url"]))
            if segments:
                rows.append({"resource": "primer segmento HLS (googlevideo)", **_direct(segments[0][0], headers, 64 * 1024)})
    https = next((f for f in formats if f.get("protocol") == "https" and f.get("vcodec") not in (None, "none")), None)
    if https:
        headers = {k: str(v) for k, v in (https.get("http_headers") or {}).items()}
        rows.append({"resource": "64 KB de un formato HTTPS (googlevideo)", **_direct(str(https["url"]), headers, 64 * 1024)})
    for row in rows:
        row.pop("text", None)
    return rows


def markdown(video: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"# Sonda: ¿qué responde directo, sin el proxy? · {video}", "",
             "| Recurso | Respuesta directa | Bytes |", "|---|---|---|"]
    for r in rows:
        status = r.get("status") or r.get("error") or "—"
        lines.append(f"| {r['resource']} | {status} | {r.get('bytes', 0)} |")
    ok = [r["resource"] for r in rows if r.get("status") in (200, 206)]
    lines += ["", "Responden directo (candidatos a no pasar por el proxy): " + (", ".join(ok) or "ninguno"), ""]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    from .ytcheck import TEST_VIDEO

    video_id = sys.argv[1] if len(sys.argv) > 1 else TEST_VIDEO
    text = markdown(video_id, probe(PROJECT_ROOT, video_id))
    (PROJECT_ROOT / "out").mkdir(exist_ok=True)
    (PROJECT_ROOT / "out" / "_sonda_directo.md").write_text(text, encoding="utf-8")
    print(text)
