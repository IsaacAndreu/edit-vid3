"""Turns for the heavy stages when the night queue runs two videos at once.

One video's network work (searching and downloading from YouTube) overlaps the other's CPU work
(analysis, render), so the PC is never idle waiting for YouTube. Each group allows one video at a
time: two downloads would share the same connection and YouTube limits; two renders the same cores.
Locks are files in work/ (work/.turno-red, work/.turno-cpu) holding the owner's PID; a lock whose
process is gone (power cut, Ctrl+C) is taken over.

A bigger machine gives a group more places at once: `queue.slots` ({red: 3, cpu: 2}) → work/.turno-red,
.turno-red-2, .turno-red-3… (1 each by default, as before).
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Iterator

# fallback runs the face and vision models (~5 GB over the base on the server): with the CPU turn it never overlaps a
# render (~14 GB), which together would not fit in 23 GB of RAM
GROUPS = {"sourcing": "red", "ingest": "red", "fallback": "cpu", "align": "cpu", "analysis": "cpu", "render": "cpu"}
ENV = "EDITVID_TURNS"           # set by the queue for its videos; single runs never wait


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259                                          # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def slots(root: Path, group: str) -> int:
    """Places of a group at once (queue.slots.<group>, 1 by default)."""

    try:
        from .context import RunContext

        value = (RunContext.create("_cola", root=root).section("queue").get("slots") or {}).get(group, 1)
        return max(1, int(value))
    except Exception:
        return 1


def _take(path: Path, label: str) -> bool:
    """The place at `path` if it is free (or its owner is gone)."""

    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {label}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                owner = int(path.read_text().split()[0])
            except (OSError, ValueError, IndexError):
                owner = 0
            if _alive(owner):
                return False
            path.unlink(missing_ok=True)
    return False


@contextlib.contextmanager
def turn(root: Path, stage: str, label: str = "", poll: float = 5.0) -> Iterator[None]:
    group = GROUPS.get(stage)
    if not group or not os.environ.get(ENV):
        yield
        return
    places = [root / "work" / (f".turno-{group}" if i == 1 else f".turno-{group}-{i}") for i in range(1, slots(root, group) + 1)]
    places[0].parent.mkdir(parents=True, exist_ok=True)
    waited = 0.0
    while True:
        path = next((p for p in places if _take(p, label)), None)
        if path is not None:
            break
        if waited == 0:
            print(f"   esperando turno de {'red' if group == 'red' else 'CPU'} (lo usan otros vídeos)…")
        time.sleep(poll)
        waited += poll
    if waited:
        print(f"   turno conseguido tras {waited / 60:.0f} min")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)
