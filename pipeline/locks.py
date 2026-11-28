"""Turns for the heavy stages when the night queue runs two videos at once.

One video's network work (searching and downloading from YouTube) overlaps the other's CPU work
(analysis, render), so the PC is never idle waiting for YouTube. Each group allows one video at a
time: two downloads would share the same connection and YouTube limits; two renders the same cores.
Locks are files in work/ (work/.turno-red, work/.turno-cpu) holding the owner's PID and the time that process
started («pid:start», `stamp()`); a lock whose process is gone (power cut, Ctrl+C), or whose PID now belongs to
another process (a reboot reuses PIDs: 27-11, a turn blocked for ever, in silence), is taken over. A turn older than
`TURN_HOURS` (24, longer than any stage the watchdog lets run) is stale whatever it says. A wait for a turn longer
than `queue.turn_wait_warn_minutes` (120) is told once (log and notice): the watchdog ignores videos that wait.

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
# analysis takes no turn: its fine pass is ~95 % waiting for YouTube's 360p windows (gym4.0: 279 windows in 104 min,
# the CLIP work itself 32 s) and holding a CPU place meanwhile kept simulations and renders waiting for nothing; its
# downloads already go through the shared YouTube pace and hourly budget of every process
# align has a turn of its own (fase 5.5): two minutes of Whisper, on half the cores (align.cpu_threads), no longer wait
# behind two renders; two alignments at once still wait for each other (queue.slots.align, 1)
GROUPS = {"sourcing": "red", "ingest": "red", "fallback": "cpu", "align": "align", "render": "cpu"}
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


TURN_HOURS = 24


def process_start(pid: int) -> str | None:
    """When the process `pid` started (clock ticks since boot, /proc on Linux; psutil elsewhere if installed), or
    None when it cannot be known."""

    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat[stat.rindex(")") + 2:].split()[19]        # field 22: starttime (the name may hold spaces)
    except (OSError, ValueError, IndexError):
        pass
    try:
        import psutil

        return f"{psutil.Process(pid).create_time():.0f}"
    except Exception:
        return None


def stamp(pid: int | None = None) -> str:
    """What a lock holds for its owner: «pid:start» (only «pid» where the start cannot be known)."""

    pid = os.getpid() if pid is None else pid
    start = process_start(pid)
    return f"{pid}:{start}" if start else str(pid)


def owner_alive(token: str) -> bool:
    """The owner written in a lock («pid:start», or the old «pid») is this very process still running."""

    pid_text, _, start = str(token or "").partition(":")
    try:
        pid = int(pid_text)
    except ValueError:
        return False
    if not _alive(pid):
        return False
    if start:
        now = process_start(pid)
        if now is not None and now != start:                    # the PID was reused by another process
            return False
    return True


def lock_owner(path: Path) -> str:
    try:
        return path.read_text().split()[0]
    except (OSError, IndexError):
        return ""


def warn_minutes(root: Path) -> float:
    try:
        from .context import RunContext

        return float(RunContext.create("_cola", root=root).section("queue").get("turn_wait_warn_minutes", 120) or 0)
    except Exception:
        return 120.0


def _tell(root: Path, text: str) -> None:
    print(f"   ⚠ {text}", flush=True)
    try:
        from .context import RunContext
        from .notify import send

        send(RunContext.create("_notify", root=root, config={}), text.splitlines()[0], text)
    except Exception as error:                                   # the wait goes on even without a notice
        print(f"   (aviso no enviado: {type(error).__name__})")


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
            os.write(fd, f"{stamp()} {label}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            owner = lock_owner(path)
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                continue
            if owner_alive(owner) and age < TURN_HOURS * 3600:
                return False
            if not owner and age < 10:           # empty: just created, its owner is writing its PID right now
                return False
            path.unlink(missing_ok=True)
    return False


_HELD: dict[str, list] = {}       # group → [place file, label, root, poll] held by this process (for lend)


def _acquire(root: Path, group: str, label: str, poll: float) -> Path:
    places = [root / "work" / (f".turno-{group}" if i == 1 else f".turno-{group}-{i}") for i in range(1, slots(root, group) + 1)]
    places[0].parent.mkdir(parents=True, exist_ok=True)
    waited = 0.0
    told = False
    warn = warn_minutes(root)
    while True:
        path = next((p for p in places if _take(p, label)), None)
        if path is not None:
            break
        if warn > 0 and not told and waited >= warn * 60:
            told = True
            holders = ", ".join(" ".join(p.read_text().split()[:2]) for p in places if p.is_file()) or "?"
            what = "red" if group == "red" else "alineación" if group == "align" else "CPU"
            _tell(root, f"{label or 'Un vídeo'} lleva {waited / 3600:.0f} h esperando turno de {what}; "
                        f"lo tiene: {holders}. Si ese proceso ya no existe, borra el archivo de work/.turno-{group}*")
        if waited == 0:
            print(f"   esperando turno de {'red' if group == 'red' else 'alineación' if group == 'align' else 'CPU'} "
                  "(lo usan otros vídeos)…")
        time.sleep(poll)
        waited += poll
    if waited:
        print(f"   turno conseguido tras {waited / 60:.0f} min")
    return path


@contextlib.contextmanager
def turn(root: Path, stage: str, label: str = "", poll: float = 5.0) -> Iterator[None]:
    group = GROUPS.get(stage)
    if not group or not os.environ.get(ENV):
        yield
        return
    held = [_acquire(root, group, label, poll), label, root, poll]
    _HELD[group] = held
    try:
        yield
    finally:
        _HELD.pop(group, None)
        held[0].unlink(missing_ok=True)          # the place it holds now (lend may have changed it)


def release_red_turn(root: Path) -> bool:
    """queue.release_red_turn (off): lend the network turn during a stage's work that does not touch the network."""

    try:
        from .context import RunContext

        return bool(RunContext.create("_cola", root=root).section("queue").get("release_red_turn", False))
    except Exception:
        return False


@contextlib.contextmanager
def lend(root: Path, stage: str) -> Iterator[None]:
    """Fase 3.7, behind `queue.release_red_turn` (off by default): while this block does no network work (the CLIP
    features computed at the end of sourcing), the stage's turn is given back so another video's searches can go,
    and taken again (waiting if needed) before the stage asks the network for anything else. Off: nothing changes.

    To compare: `python main.py --youtube-stats 1` a night with it off and one with it on — «bot» and «429» per
    hour (## Por horas) and the share of failed requests; `red: 2` once doubled them."""

    group = GROUPS.get(stage)
    held = _HELD.get(group or "")
    if group != "red" or held is None or not release_red_turn(root):
        yield
        return
    held[0].unlink(missing_ok=True)
    print("   (turno de red prestado mientras se calcula en local)")
    try:
        yield
    finally:
        held[0] = _acquire(held[2], group, held[1], held[3])
