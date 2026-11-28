"""The queue's watchdog: a video's process that hangs is cut, not only reported.

The heartbeat (out/_vigilar.latido) is written by a thread of its own: it proves the watcher lives, not that a video
advances, and the parallel queue read each video's output with no time limit. Here, every `check_seconds` (30), for
each video process of the parallel queue:

- a stage running (work/<slug>/current.json: not waiting for its turn, not ended) for longer than
  `queue.stage_minutes` (360) + `queue.stage_minutes_per_video_minute` (20) × the video's minutes, or
- a process that wrote nothing for `queue.silent_minutes` (180) while a stage runs,

is stopped (SIGTERM, then SIGKILL after `grace_seconds`, 60) and reported as a failure the watcher retries, with
the stage and the time in the notice. The serial queue runs its video in its own process: there (`watch_here`) a
stage past its limit raises `Cut` in the queue's main thread (a signal, so even a blocking wait is interrupted), the
video fails and the queue goes on with the next. In-process there is no output to hear, so only the stage's time
counts; and only where the system has SIGUSR2 (not Windows). While a video waits for its turn, for the API quota or for tomorrow's proxy
budget (no stage running) nothing is counted against it.
"""

from __future__ import annotations

import json
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def video_minutes(root: Path, slug: str) -> float:
    return float(_read(root / "work" / slug / "words.json").get("durationSeconds") or 0) / 60


def running_stage(root: Path, slug: str) -> tuple[str, float] | None:
    """(stage, seconds it has been running), or None when no stage is running (waiting for a turn, between stages)."""

    current = _read(root / "work" / slug / "current.json")
    if not current or current.get("ended") or current.get("waiting") or not current.get("started"):
        return None
    try:
        started = datetime.fromisoformat(str(current["started"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.astimezone()
    return str(current.get("stage") or "?"), (datetime.now(timezone.utc) - started).total_seconds()


def stop(process: subprocess.Popen, grace: float = 60.0) -> None:
    """SIGTERM (the video's process closes its stage cleanly: _stop_signals), then SIGKILL after `grace`."""

    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
    except OSError:
        pass


class Cut(Exception):
    """The watchdog cut the video that ran in this very process (the serial queue)."""


class _Here:
    """The serial queue's video, as the watchdog sees a process: «stopping» it interrupts the main thread."""

    in_process = True

    def __init__(self, guardian: "Guardian", slug: str) -> None:
        self.guardian, self.slug = guardian, slug
        self.ended = False

    def poll(self) -> int | None:
        return 0 if self.ended else None

    def terminate(self) -> None:
        if not self.ended and self.guardian._here == self.slug:
            signal.pthread_kill(threading.main_thread().ident or 0, signal.SIGUSR2)

    kill = terminate

    def wait(self, timeout: float | None = None) -> int:
        return 0


class Guardian:
    def __init__(self, root: Path, cfg: dict[str, Any] | None = None) -> None:
        cfg = cfg or {}
        self.root = root
        self.stage_minutes = float(cfg.get("stage_minutes", 360))
        self.per_video_minute = float(cfg.get("stage_minutes_per_video_minute", 20))
        self.silent_minutes = float(cfg.get("silent_minutes", 180))
        self.check_seconds = float(cfg.get("check_seconds", 30))
        self.grace = float(cfg.get("grace_seconds", 60))
        self._watched: dict[str, tuple[subprocess.Popen, float]] = {}
        self.cut: dict[str, str] = {}                  # slug → why it was cut (for the queue's report)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._here: str | None = None
        self._old_handler: Any = None

    # --- what the queue calls ---------------------------------------------------------------------------------
    def watch(self, slug: str, process: subprocess.Popen) -> None:
        with self._lock:
            self._watched[slug] = (process, time.monotonic())
            self.cut.pop(slug, None)
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="perro-guardian", daemon=True)
            self._thread.start()

    def heard(self, slug: str) -> None:
        """The process wrote a line: it is alive."""

        with self._lock:
            if slug in self._watched:
                self._watched[slug] = (self._watched[slug][0], time.monotonic())

    def done(self, slug: str) -> str | None:
        """The process ended: why it was cut, if it was."""

        with self._lock:
            self._watched.pop(slug, None)
            return self.cut.get(slug)

    def watch_here(self, slug: str) -> bool:
        """The serial queue is about to run `slug` in this process (the main thread). False where it cannot be cut."""

        if not hasattr(signal, "SIGUSR2") or threading.current_thread() is not threading.main_thread():
            return False

        def cut(signum: int, frame: Any) -> None:
            if self._here == slug:
                raise Cut(self.cut.get(slug) or "cortado por el perro guardián")

        self._old_handler = signal.signal(signal.SIGUSR2, cut)
        self._here = slug
        self.watch(slug, _Here(self, slug))           # type: ignore[arg-type]
        return True

    def done_here(self, slug: str) -> str | None:
        """The serial video ended (or was cut): why it was cut, if it was."""

        if self._here != slug:
            return None
        self._here = None
        with self._lock:
            here = self._watched.get(slug)
        if here is not None:
            here[0].ended = True                       # type: ignore[attr-defined]
        why = self.done(slug)
        if self._old_handler is not None:
            signal.signal(signal.SIGUSR2, self._old_handler)
            self._old_handler = None
        return why

    def close(self) -> None:
        """The round ended: the check thread stops (nothing is stopped with it)."""

        self._stop.set()

    def stop_all(self) -> None:
        """The queue is stopping (systemctl stop/restart): every video process is closed cleanly, none left behind
        (19-11: a video's process outlived the service's restart)."""

        self._stop.set()
        with self._lock:
            processes = [p for p, _ in self._watched.values()]
        threads = [threading.Thread(target=stop, args=(p, self.grace), daemon=True) for p in processes]
        for t in threads:
            t.start()
        for t in threads:
            t.join(self.grace + 5)

    # --- the check ---------------------------------------------------------------------------------------------
    def limit_seconds(self, slug: str) -> float:
        return 60 * (self.stage_minutes + self.per_video_minute * video_minutes(self.root, slug))

    def why_cut(self, slug: str, last_heard: float) -> str | None:
        running = running_stage(self.root, slug)
        if running is None:
            return None
        stage, seconds = running
        if seconds > self.limit_seconds(slug):
            return f"cortado por el perro guardián: la etapa {stage} llevaba {seconds / 3600:.1f} h (límite " \
                   f"{self.limit_seconds(slug) / 3600:.1f} h)"
        silent = time.monotonic() - last_heard
        if silent > 60 * self.silent_minutes:
            return f"cortado por el perro guardián: {silent / 60:.0f} min sin escribir nada en la etapa {stage}"
        return None

    def check(self) -> list[str]:
        with self._lock:
            watched = dict(self._watched)
        cut = []
        for slug, (process, last_heard) in watched.items():
            if process.poll() is not None or slug in self.cut:
                continue
            if getattr(process, "in_process", False):     # nothing to hear in-process: only the stage's time
                last_heard = time.monotonic()
            why = self.why_cut(slug, last_heard)
            if why:
                with self._lock:
                    self.cut[slug] = why
                print(f"[{slug}] {why}", flush=True)
                threading.Thread(target=stop, args=(process, self.grace), daemon=True).start()
                cut.append(slug)
        return cut

    def _loop(self) -> None:
        while not self._stop.wait(self.check_seconds):
            try:
                self.check()
            except Exception as error:              # the watchdog itself never stops the queue
                print(f"(perro guardián: {type(error).__name__}: {error})")
