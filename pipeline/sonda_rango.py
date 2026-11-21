"""What a byte range of a YouTube video brings back, without downloading anything (descargas-rango-fallo.md).

    python -m pipeline.sonda_rango <vídeo o enlace> [--formato "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]"]

One extraction (the video's details, through the same route and residential session as a video of the queue) and,
for each format a byte range would read, ONE request for its first 64 KB. It prints the format chosen (itag, ext,
codec, container, protocol), the answer (HTTP code, Content-Type), the first 16 bytes in hex and what the parser
makes of them: an mp4 with its index (the range would work), a webm, an mp4 without sidx, or something else. Nothing
is written but the details' cache.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

DEFAULT_FORMAT = "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]"


def verdict(head: bytes) -> str:
    """What the parser makes of the first bytes."""

    from .sourcing.byteranges import NoIndex, needed_head, plan
    from .sourcing.youtube import EBML_MAGIC

    if head[:4] == EBML_MAGIC:
        return "webm (Matroska): su índice es «Cues», no sidx; este programa no lo corta por rangos"
    if head[4:8] != b"ftyp":
        return "no empieza por un mp4 (ftyp): otro envoltorio de la respuesta"
    try:
        need = needed_head(head)
        if need is not None and need > len(head):
            return f"mp4: el índice ocupa {need / 1e6:.1f} MB, más de lo leído (64 KB): haría falta otra petición"
        cut = plan(head, 0.0, 5.0)
        return f"mp4 con índice (sidx): el rango funcionaría (los 5 primeros s = bytes {cut.data[0]}-{cut.data[1]})"
    except NoIndex as error:
        return f"mp4 sin índice usable: {error}"


def probe(ctx: Any, video: str, fmt: str = DEFAULT_FORMAT, youtube: Any = None) -> list[str]:
    """One line per format a byte range would read (see the module's docstring)."""

    from .material import video_ids
    from .sourcing.youtube import range_diagnosis

    found = video_ids([video])
    if not found:
        raise ValueError(f"no reconozco un vídeo de YouTube en «{video}»")
    video_id = found[0]
    if youtube is None:
        from .sourcing import youtube_source

        youtube = opened = youtube_source(ctx)
    else:
        opened = None
    lines = []
    try:
        youtube._local.video_id = video_id
        print(f"{video_id}: extrayendo los formatos (una petición, puede tardar un minuto)…", flush=True)
        info = youtube._fresh_full_info(video_id)
        try:
            pieces = youtube._range_formats(info, fmt, False, False)
        except Exception as error:            # NoIndex «sin formato mp4 por HTTPS» and the like: said, not raised
            return [f"{video_id} · ningún formato mp4 por HTTPS para «{fmt}»: {error}\n   → el rango no se puede "
                    "intentar con este vídeo (solo HLS o webm)"]
        if not pieces:
            return [f"{video_id} · yt-dlp no eligió ningún formato para «{fmt}»"]
        for piece in pieces:
            url = str(piece["url"])
            headers = {k: str(v) for k, v in (piece.get("http_headers") or {}).items()}

            def first_bytes() -> tuple[bytes, int, str]:
                way = getattr(youtube._local, "way", 0) or 0
                return youtube._range_get(way, youtube._requests_proxies(way), url, headers, 0, 64 * 1024 - 1)

            head, status, kind = youtube._call("sonda (rango)", first_bytes)
            lines.append(f"{video_id} · {range_diagnosis(piece, status, kind, head)}\n   → {verdict(head)}")
    finally:
        if opened is not None:
            opened.close()
    return lines


def main(argv: list[str] | None = None) -> int:
    from .context import PROJECT_ROOT, RunContext

    parser = argparse.ArgumentParser(prog="python -m pipeline.sonda_rango", description=__doc__.splitlines()[0])
    parser.add_argument("video")
    parser.add_argument("--formato", default=DEFAULT_FORMAT)
    args = parser.parse_args(argv)
    ctx = RunContext.create("_sonda_rango", root=PROJECT_ROOT)
    try:
        lines = probe(ctx, args.video, args.formato)
    except Exception as error:               # the extraction itself failed: say it, never end in silence
        print(f"La sonda no pudo terminar: {type(error).__name__}: {str(error)[:400]}")
        return 1
    for line in lines or ["(la sonda no obtuvo ninguna respuesta)"]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
