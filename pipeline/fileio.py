"""Files that several processes share, written so that a kill, a restart or a second video never leaves them broken.

- Media (clips cut from YouTube, whole downloads): written to a hidden `.part<pid>-<name>` next to the final name,
  checked with ffprobe (it opens, it has a picture, it lasts what it should) and only then renamed. A clip whose
  name exists is always complete: the service restarts after every `git pull`, and an ffmpeg killed half way used
  to leave a truncated clip under its final name that the library reused forever.
- Small JSON state (refusals, bot answers, quarantines): read-modify-write under an exclusive file lock (`flock`)
  and written atomically (temporary file + rename). A corrupt file is kept aside and reported, never taken for an
  empty one in silence.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

PART = ".part"
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(path: Path) -> threading.Lock:
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(str(path), threading.Lock())


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Exclusive between threads of this process and between processes (flock on `path`, created if missing).
    Where flock does not exist (Windows) only between threads, as before."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with _thread_lock(path):
        try:
            import fcntl
        except ImportError:
            yield
            return
        with open(path, "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{PART}{os.getpid()}-{threading.get_ident()}-{path.name}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path: Path, default: Any) -> Any:
    """The JSON at `path`, `default` when missing. A file that does not parse is moved aside (`<name>.corrupto-<time>`)
    with a line in the log, and `default` is returned: the next write starts clean, and the evidence stays."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default
    except OSError as error:
        print(f"   (no se pudo leer {path.name}: {type(error).__name__}; se usa vacío)")
        return default
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except ValueError:
        aside = path.with_name(f"{path.name}.corrupto-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(path, aside)
        except OSError:
            aside = path
        print(f"   AVISO: {path.name} estaba roto (JSON inválido); copia en {aside.name}, se empieza de cero")
        return default


def update_json(path: Path, change: Callable[[Any], Any], default: Any) -> Any:
    """Read-modify-write of a JSON file shared by several processes. `change(data)` returns the new data (or None to
    leave the file untouched). Returns what is on disk afterwards."""

    with file_lock(path.with_name(path.name + ".lock")):
        data = read_json(path, default)
        new = change(data)
        if new is None:
            return data
        atomic_write_text(path, json.dumps(new, ensure_ascii=False))
        return new


# --- media ------------------------------------------------------------------------------------------------------

def part_for(target: Path) -> Path:
    """Where `target` is written before it is checked: hidden, same folder (rename is atomic), same extension (ffmpeg
    chooses the container by it), one per process and thread (two videos cutting the same clip never mix)."""

    return target.with_name(f"{PART}{os.getpid()}-{threading.get_ident()}-{target.name}")


def probe(path: Path, timeout: float = 60) -> dict[str, Any] | None:
    try:
        done = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                               "stream=codec_type,height,start_time:format=duration", "-of", "json", str(path)],
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        return json.loads(done.stdout or "{}")
    except ValueError:
        return None


def media_problem(path: Path, *, video: bool = True, seconds: float | None = None, tolerance: float = 0.5,
                  timeout: float = 60) -> str | None:
    """Why `path` is not a usable clip (None when it is): missing, empty, ffprobe cannot open it, no picture (when
    `video`), no duration, or shorter than `seconds` minus `tolerance` (a cut killed half way)."""

    try:
        if path.stat().st_size == 0:
            return "vacío"
    except OSError:
        return "no existe"
    info = probe(path, timeout)
    if info is None:
        return "ffprobe no lo abre"
    streams = info.get("streams") or []
    if video and not any(s.get("codec_type") == "video" for s in streams):
        return "sin pista de vídeo"
    if not video and not streams:
        return "sin pistas"
    try:
        duration = float((info.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return "sin duración"
    if seconds is not None and duration < seconds - tolerance:
        return f"dura {duration:.2f} s de {seconds:.2f} s"
    return None


def publish(part: Path, target: Path, *, video: bool = True, seconds: float | None = None,
            tolerance: float = 0.5) -> None:
    """Check `part` and rename it to `target`; raise RuntimeError (and delete it) when it is not a usable clip."""

    problem = media_problem(part, video=video, seconds=seconds, tolerance=tolerance)
    if problem:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"el archivo salió incompleto ({problem}): no se guarda en la caché")
    os.replace(part, target)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def clean_parts(folder: Path, *, pattern: str = "*/" + PART + "*", older_hours: float = 6.0) -> int:
    """Delete the leftovers of writes that never finished: `.part<pid>-…` whose process is gone (or older than
    `older_hours`, whoever wrote them). Returns how many went."""

    removed = 0
    now = time.time()
    for path in folder.glob(pattern) if folder.is_dir() else []:
        try:
            pid = int(path.name[len(PART):].split("-", 1)[0])
        except ValueError:
            pid = 0
        try:
            old = now - path.stat().st_mtime > older_hours * 3600
        except OSError:
            continue
        if old or not _alive(pid):
            try:
                if path.is_dir():
                    import shutil

                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
