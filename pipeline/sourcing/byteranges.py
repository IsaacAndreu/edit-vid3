"""Ranges of a video WITHOUT HLS by HTTP byte ranges (opt-in: sourcing.youtube.byte_ranges, off by default).

YouTube's DASH formats in mp4 are fragmented: `ftyp`, `moov` (the init: codec, timescale), a `sidx` (segment index:
the size and duration of every fragment) and then `moof`+`mdat` fragments. Reading the first KB of the file with one
`Range` request tells which bytes hold the seconds asked for; only those are requested (in pieces under 10 MB, the
same size yt-dlp uses so YouTube does not throttle), written after the init as a small fragmented mp4, and ffmpeg
cuts it locally — as with the HLS segments. A 5 s clip of a 40 min video costs ~1-3 MB instead of the whole file.

webm (its index is `Cues`, inside the Matroska header) or an mp4 without `sidx` near its start: not handled here,
the caller keeps its previous behaviour.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


class NoIndex(ValueError):
    """The first bytes do not hold an mp4 init + sidx: this file cannot be cut by byte ranges."""


@dataclass(frozen=True)
class Plan:
    init: tuple[int, int]           # [first, last] byte of ftyp+moov
    data: tuple[int, int]           # [first, last] byte of the fragments covering the seconds asked for
    start: float                    # the source time where those fragments begin (seconds)
    end: float                      # and where they end


def _boxes(data: bytes, offset: int = 0):
    """(type, start, size, header) of each top-level box in data[offset:]; stops at a box that is cut short."""

    position = offset
    while position + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[position:position + 8])
        header = 8
        if size == 1:
            if position + 16 > len(data):
                return
            size = struct.unpack(">Q", data[position + 8:position + 16])[0]
            header = 16
        elif size == 0:
            return
        if size < header:
            raise NoIndex(f"caja {kind!r} de tamaño {size}")
        yield kind.decode("latin-1"), position, size, header
        position += size


def needed_head(data: bytes) -> int | None:
    """How many bytes from the start hold ftyp, moov and sidx (None: not enough read yet to know)."""

    seen = set()
    for kind, start, size, _ in _boxes(data):
        seen.add(kind)
        if kind == "sidx":
            return start + size
        if kind in ("moof", "mdat"):
            raise NoIndex("sin sidx antes del primer fragmento")
        if start + size > len(data):
            return start + size + 64 * 1024 if kind in ("moov", "ftyp") else None
    if seen and not seen <= {"ftyp", "moov", "free", "styp", "uuid"}:
        raise NoIndex(f"cajas inesperadas al principio: {sorted(seen)}")
    return None


def plan(head: bytes, start: float, end: float, *, margin: float = 0.0) -> Plan:
    """The bytes to request for [start - margin, end] given the first bytes of the file (ftyp, moov, sidx)."""

    boxes = list(_boxes(head))
    kinds = [k for k, *_ in boxes]
    if "moov" not in kinds or "sidx" not in kinds:
        raise NoIndex(f"faltan moov o sidx ({kinds[:6]})")
    moov = next(b for b in boxes if b[0] == "moov")
    _, sidx_at, sidx_size, header = next(b for b in boxes if b[0] == "sidx")
    if sidx_at + sidx_size > len(head):
        raise NoIndex("sidx cortado: hacen falta más bytes")
    body = head[sidx_at + header: sidx_at + sidx_size]
    version = body[0]
    cursor = 4 + 4                                   # version+flags, reference_ID
    timescale = struct.unpack(">I", body[cursor:cursor + 4])[0]
    cursor += 4
    if version == 0:
        earliest, first_offset = struct.unpack(">II", body[cursor:cursor + 8])
        cursor += 8
    else:
        earliest, first_offset = struct.unpack(">QQ", body[cursor:cursor + 16])
        cursor += 16
    cursor += 2                                       # reserved
    count = struct.unpack(">H", body[cursor:cursor + 2])[0]
    cursor += 2
    if not timescale or not count:
        raise NoIndex("sidx vacío")
    offset = sidx_at + sidx_size + first_offset
    time = earliest
    lo = max(0.0, start - margin)
    first = last = None
    t_first = t_last = 0.0
    for _ in range(count):
        size_word, duration = struct.unpack(">II", body[cursor:cursor + 8])
        cursor += 12                                  # + SAP word
        if size_word >> 31:
            raise NoIndex("sidx jerárquico (referencias a otros sidx)")
        size = size_word & 0x7FFFFFFF
        a, b = time / timescale, (time + duration) / timescale
        if b > lo and a < end and first is None:
            first, t_first = offset, a
        if first is not None and a < end:
            last, t_last = offset + size - 1, b
        offset += size
        time += duration
    if first is None or last is None:
        raise NoIndex(f"ningún fragmento cubre {start:.1f}-{end:.1f} s")
    return Plan(init=(0, moov[1] + moov[2] - 1), data=(first, last), start=t_first, end=t_last)


def pieces(first: int, last: int, chunk: int = 9 * 1024 * 1024) -> list[tuple[int, int]]:
    """[first, last] in Range pieces under 10 MB each."""

    return [(a, min(last, a + chunk - 1)) for a in range(first, last + 1, chunk)]
