"""Why do ranges go whole when almost every video has HLS? An offline look at what the server already has.

    python -m pipeline.diag_hls [días]      (7 by default; no request to YouTube, only files on disk)

1. For every `cache/videos/<id>/ytdlp-info.json` (the extraction the downloads use): does it carry m3u8 formats, are
   they marked «to be tested» (yt-dlp's `__needs_testing`, videos uploaded ≤ 2 days before extraction), and
   does yt-dlp's own format selection find an HLS stream for the requests the pipeline makes (analysis 360p, HD
   clip, clip with sound)? A video with m3u8 formats where the selection finds none is the bug to fix.
2. For every «download (completo)» and «archivo» row of the last `días` in work/*/youtube_downloads.jsonl: the route
   it took and why not HLS (rows written since 11-2026), or for older rows what its video's extraction says.

Writes out/_diag_hls.md and prints it.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from .sourcing.youtube import YouTubeSource, cap_fps, cap_height, hls_format, selectable

REQUESTS = {
    "análisis 360p": (YouTubeSource.SECTION_FORMAT, False),
    "clip HD": (YouTubeSource.HD_FORMAT, False),
    "clip HD con sonido": ("bv*[height<=1080][vcodec^=avc1]+ba/bv*[height<=1080]+ba/b[height<=1080]", True),
}


def _select(info: dict[str, Any], fmt: str) -> str | None:
    import yt_dlp

    try:
        # check_formats False: never test a format by downloading a piece of it (yt-dlp does it for the HLS formats of
        # videos uploaded in the last 2 days, `__needs_testing`): this look stays offline
        with yt_dlp.YoutubeDL({"format": fmt, "simulate": True, "quiet": True, "no_warnings": True,
                               "check_formats": False}) as ydl:
            chosen = ydl.process_ie_result(selectable(info), download=False)
    except Exception as error:
        return f"ERROR {str(error)[:80]}"
    piece = (chosen.get("requested_formats") or [chosen])[0]
    return str(piece.get("format_id"))


def extractions(root: Path, limit: int = 400) -> dict[str, Any]:
    paths = sorted((root / "cache" / "videos").glob("*/ytdlp-info.json"), key=lambda p: -p.stat().st_mtime)[:limit]
    out: dict[str, Any] = {"total": len(paths), "withHls": 0, "selectionFails": {k: 0 for k in REQUESTS},
                           "examples": [], "clients": {}, "untested": 0}
    for path in paths:
        try:
            info = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        clients = ",".join(info.get("_edit_vid3_clients") or []) or "por defecto"
        out["clients"][clients] = out["clients"].get(clients, 0) + 1
        formats = info.get("formats") or []
        if not any(str(f.get("protocol") or "").startswith("m3u8") for f in formats):
            continue
        out["withHls"] += 1
        if any(f.get("__needs_testing") for f in formats if str(f.get("protocol") or "").startswith("m3u8")):
            # a video uploaded ≤ 2 days before its extraction: yt-dlp downloads a piece of each HLS format to test it
            # before choosing, and drops the HLS ones whose test fails (→ the whole file is downloaded instead)
            out["untested"] += 1
        for name, (fmt, audio) in REQUESTS.items():
            request = hls_format(cap_fps(cap_height(fmt, 720), 30), audio=audio)
            chosen = _select(info, request)
            if chosen is None or chosen.startswith("ERROR"):
                out["selectionFails"][name] += 1
                if len(out["examples"]) < 8:
                    hls = [f"{f.get('format_id')} {f.get('height')}p{f.get('fps')} {f.get('vcodec')}/{f.get('acodec')}"
                           for f in formats if str(f.get("protocol") or "").startswith("m3u8")]
                    out["examples"].append({"video": path.parent.name, "request": name, "answer": chosen,
                                            "hls": hls[:8]})
    return out


def rows(root: Path, days: float) -> dict[str, Any]:
    since = time.time() - days * 86400
    out: dict[str, Any] = {"whole": 0, "routes": {}, "notHls": {}, "oldWhole": {"conHlsEnDisco": 0, "sinHls": 0, "sinInfo": 0},
                           "noFit": {}}
    for log in (root / "work").glob("*/youtube_downloads.jsonl") if (root / "work").is_dir() else []:
        try:
            if log.stat().st_mtime < since:
                continue
            lines = log.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if float(row.get("ts") or 0) < since:
                continue
            action = str(row.get("action") or "")
            if action.startswith("archivo") and row.get("route"):
                out["routes"][row["route"]] = out["routes"].get(row["route"], 0) + 1
            if row.get("notHls"):
                reason = str(row["notHls"]).split(":")[0][:90]
                out["notHls"][reason] = out["notHls"].get(reason, 0) + 1
                if str(row["notHls"]).startswith("ningún formato HLS encaja") and row.get("video"):
                    out["noFit"][str(row["video"])] = out["noFit"].get(str(row["video"]), 0) + 1
            if action == "download (completo)":
                out["whole"] += 1
                if not row.get("notHls"):
                    info = root / "cache" / "videos" / str(row.get("video")) / "ytdlp-info.json"
                    try:
                        formats = json.loads(info.read_text("utf-8")).get("formats") or []
                        key = "conHlsEnDisco" if any(str(f.get("protocol") or "").startswith("m3u8") for f in formats) \
                            else "sinHls"
                    except (OSError, ValueError):
                        key = "sinInfo"
                    out["oldWhole"][key] += 1
    return out


def no_fit(root: Path, videos: dict[str, int]) -> dict[str, Any]:
    """The videos whose ranges said «ningún formato HLS encaja» on the server: how many, and what their extraction on
    disk says. If they are the ones with HLS «por probar», the culprit is yt-dlp's test download of those formats
    (`hls_format_test: false` skips it); if offline selection finds HLS for them, something else in the pipeline's
    own selection differs."""

    out: dict[str, Any] = {"videos": len(videos), "rows": sum(videos.values()), "untested": 0, "untestedRows": 0,
                           "offlineFinds": 0, "noInfo": 0, "examples": []}
    request = hls_format(cap_fps(cap_height(YouTubeSource.SECTION_FORMAT, 720), 30))
    for video, count in sorted(videos.items(), key=lambda kv: -kv[1]):
        try:
            info = json.loads((root / "cache" / "videos" / video / "ytdlp-info.json").read_text("utf-8"))
        except (OSError, ValueError):
            out["noInfo"] += 1
            continue
        hls = [f for f in info.get("formats") or [] if str(f.get("protocol") or "").startswith("m3u8")]
        untested = any(f.get("__needs_testing") for f in hls)
        if untested:
            out["untested"] += 1
            out["untestedRows"] += count
        chosen = _select(info, request) if hls else None
        if chosen and not chosen.startswith("ERROR"):
            out["offlineFinds"] += 1
        if len(out["examples"]) < 6:
            out["examples"].append(f"{video} ×{count}: {len(hls)} HLS, {'por probar' if untested else 'probados'}, "
                                   f"selección sin red → {chosen}")
    return out


def markdown(ext: dict[str, Any], log: dict[str, Any], days: float) -> str:
    lines = ["# HLS: por qué se baja el vídeo entero", "",
             f"## Extracciones en caché (las {ext['total']} más recientes)", "",
             f"- Con formatos m3u8: {ext['withHls']} de {ext['total']}",
             "- Clientes: " + ", ".join(f"{k} {n}" for k, n in ext["clients"].items()),
             f"- Con HLS «por probar» (vídeo subido ≤ 2 días antes de extraerlo; yt-dlp prueba cada formato HLS antes de "
             f"usarlo y descarta los que fallan): {ext['untested']} de {ext['withHls']}",
             "- La selección de yt-dlp NO encuentra HLS aunque los hay: "
             + ", ".join(f"{k} {n}" for k, n in ext["selectionFails"].items()), ""]
    for e in ext["examples"]:
        lines.append(f"  - {e['video']} · {e['request']} → {e['answer']} · HLS: {'; '.join(e['hls'])}")
    lines += ["", f"## Peticiones de los últimos {days:g} días", "",
              f"- Descargas enteras: {log['whole']}",
              "- Vía de cada tramo (filas nuevas): " + (", ".join(f"{k} {n}" for k, n in log["routes"].items()) or "—"),
              "- Por qué no fue HLS (filas nuevas): " + (", ".join(f"{k} {n}" for k, n in log["notHls"].items()) or "—"),
              "- Descargas enteras antiguas (sin motivo apuntado), según su extracción en disco: "
              + ", ".join(f"{k} {n}" for k, n in log["oldWhole"].items()), ""]
    fit = log.get("noFitDetail")
    if fit and fit["videos"]:
        lines += ["## «Ningún formato HLS encaja»: qué vídeos", "",
                  f"- {fit['rows']} filas de {fit['videos']} vídeos distintos (sin su extracción en disco: {fit['noInfo']})",
                  f"- Con HLS «por probar»: {fit['untested']} vídeos, {fit['untestedRows']} filas → si son casi todas, "
                  "la culpa es la prueba de formatos de yt-dlp: `hls_format_test: false` la quita",
                  f"- La selección sin red sí encuentra HLS en {fit['offlineFinds']} de ellos"]
        lines += [f"  - {e}" for e in fit["examples"]] + [""]
    return "\n".join(lines) + "\n"


def main(root: Path, days: float = 7.0) -> str:
    log = rows(root, days)
    log["noFitDetail"] = no_fit(root, log["noFit"])
    text = markdown(extractions(root), log, days)
    path = root / "out" / "_diag_hls.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(main(Path(__file__).resolve().parents[1], float(sys.argv[1]) if len(sys.argv) > 1 else 7.0))
