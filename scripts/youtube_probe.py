#!/usr/bin/env python3
"""Search YouTube and download short probe clips through the configured proxy.

This intentionally skips the documentary pipeline (factcheck, alignment, CLIP,
judge and render). It reuses YouTubeSource so proxy enforcement, pacing,
quarantine, HLS range downloads and the existing download metrics stay in one
place.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.context import RunContext
from pipeline.sourcing import youtube_source


def _format_for_height(source: Any, height: int) -> tuple[str, str]:
    if height <= 360:
        return source.SECTION_FORMAT, "a360"
    return (
        f"bv*[height<={height}][vcodec^=avc1]/"
        f"bv*[height<={height}]/b[height<={height}]/wv*",
        f"a{height}",
    )


def _download_range(info: dict[str, Any], start: float, seconds: float) -> tuple[float, float]:
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        return start, start + seconds
    if start >= duration:
        raise ValueError(f"el vídeo dura {duration:.1f}s; --start={start:.1f}s queda fuera")
    end = min(duration, start + seconds)
    if end <= start:
        raise ValueError("el intervalo de descarga está vacío")
    return start, end


def _run_dir(root: Path, output_root: str) -> Path:
    base = Path(output_root)
    if not base.is_absolute():
        base = root / base
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base / stamp


def _context(root: Path, run_dir: Path) -> RunContext:
    ctx = RunContext.create("_youtube_probe", root=root)
    paths = ctx.config.setdefault("paths", {})
    paths["cache"] = str((run_dir / "cache").relative_to(root))
    paths["work"] = str((run_dir / "work").relative_to(root))
    # YouTubeSource resolves YOUTUBE_PROXY through the context's .env. Load it
    # explicitly even when cookies are disabled in the project config.
    ctx.env("YOUTUBE_PROXY", required=False)
    ctx.env("YOUTUBE_METADATA_PROXY", required=False)
    return ctx


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Busca YouTube y descarga clips HLS cortos usando la configuración del proyecto."
    )
    parser.add_argument("queries", nargs="+", help="consulta(s) de YouTube")
    parser.add_argument("--results", type=int, default=5, help="resultados a considerar por consulta (por defecto: 5)")
    parser.add_argument("--download-count", type=int, default=1,
                        help="clips a descargar por consulta (por defecto: 1)")
    parser.add_argument("--start", type=float, default=0.0, help="segundo inicial del clip (por defecto: 0)")
    parser.add_argument("--seconds", type=float, default=10.0,
                        help="duración máxima de cada clip (por defecto: 10)")
    parser.add_argument("--height", type=int, choices=(360, 720, 1080), default=360,
                        help="altura máxima solicitada (por defecto: 360)")
    parser.add_argument("--audio", action="store_true", help="conservar también el audio del tramo")
    parser.add_argument("--output-root", default="out/_youtube_probe",
                        help="directorio de salida relativo al repositorio")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.results < 1 or args.download_count < 1 or args.seconds <= 0 or args.start < 0:
        print("results, download-count y seconds deben ser positivos; start no puede ser negativo", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    run_dir = _run_dir(root, args.output_root)
    downloads_dir = run_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    ctx = _context(root, run_dir)
    source = None
    manifest: list[dict[str, Any]] = []

    try:
        source = youtube_source(ctx)
        fmt, prefix = _format_for_height(source, args.height)
        for query in args.queries:
            print(f"[search] {query}")
            results = source.search(query)
            candidates = [entry for entry in results if isinstance(entry, dict) and entry.get("id")]
            print(f"  encontrados: {len(candidates)}")
            for index, entry in enumerate(candidates[:args.results][:args.download_count], start=1):
                video_id = str(entry["id"])
                title = str(entry.get("title") or video_id)
                print(f"  [{index}] {title} ({video_id})")
                info = source.info(video_id)
                start, end = _download_range(info, args.start, args.seconds)
                if args.height <= 360 and not args.audio:
                    path = source.download_section(video_id, start, end)
                else:
                    path = source.download_range(
                        video_id,
                        start,
                        end,
                        fmt=fmt,
                        prefix=prefix + ("a" if args.audio else ""),
                        audio=args.audio,
                    )
                destination = downloads_dir / f"{len(manifest) + 1:02d}-{video_id}.mp4"
                shutil.copy2(path, destination)
                manifest.append({
                    "query": query,
                    "id": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "start": start,
                    "end": end,
                    "height": args.height,
                    "audio": bool(args.audio),
                    "path": str(destination.relative_to(root)),
                    "proxy_required": True,
                })
                print(f"    guardado: {destination.relative_to(root)}")
    finally:
        if source is not None:
            source.close()

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] {len(manifest)} clip(s); manifiesto: {manifest_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
