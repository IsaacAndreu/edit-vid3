"""Turns for the heavy stages when the night queue runs two videos at once.

One video's network work (searching and downloading from YouTube) overlaps the other's CPU work
(analysis, render), so the PC is never idle waiting for YouTube. Each group allows one video at a
time: two downloads would share the same connection and YouTube limits; two renders the same cores.
Locks are files in work/ (work/.turno-red, work/.turno-cpu) holding the owner's PID; a lock whose
process is gone (power cut, Ctrl+C) is taken over.
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Iterator

GROUPS = {"sourcing": "red", "ingest": "red", "fallback": "red", "align": "cpu", "analysis": "cpu", "render": "cpu"}
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


@contextlib.contextmanager
def turn(root: Path, stage: str, label: str = "", poll: float = 5.0) -> Iterator[None]:
    group = GROUPS.get(stage)
    if not group or not os.environ.get(ENV):
        yield
        return
    path = root / "work" / f".turno-{group}"
    path.parent.mkdir(parents=True, exist_ok=True)
    waited = 0.0
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {label}".encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                owner = int(path.read_text().split()[0])
            except (OSError, ValueError, IndexError):
                owner = 0
            if not _alive(owner):
                path.unlink(missing_ok=True)
                continue
            if waited == 0:
                print(f"   esperando turno de {'red' if group == 'red' else 'CPU'} (lo usa otro vídeo)…")
            time.sleep(poll)
            waited += poll
    if waited:
        print(f"   turno conseguido tras {waited / 60:.0f} min")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)
