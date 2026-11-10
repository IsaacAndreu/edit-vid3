"""Run instrumentation: per-step wall time, per-scene details and call counters.

Everything is written incrementally to ``<output>.timing.json`` so the data
survives a crash in the middle of a long run.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .cache import atomic_write_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Metrics:
    """Thread-safe collector. One shared instance (``METRICS``) per process."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._path: Path | None = None
        self._reset_state()

    def _reset_state(self) -> None:
        self._started_at = _now_iso()
        self._started_perf = time.perf_counter()
        self._status = "running"
        self._steps: list[dict[str, Any]] = []
        self._counters: dict[str, int] = {}
        self._durations: dict[str, float] = {}
        self._scenes: dict[int, dict[str, Any]] = {}
        self._meta: dict[str, Any] = {}

    def reset(self, path: Path | None = None, **meta: Any) -> None:
        with self._lock:
            self._path = path
            self._reset_state()
            self._meta = dict(meta)
            self.flush()

    def count(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def add_seconds(self, name: str, seconds: float) -> None:
        with self._lock:
            self._durations[name] = self._durations.get(name, 0.0) + max(0.0, seconds)

    @contextmanager
    def timed(self, name: str) -> Iterator[None]:
        """Accumulate wall time of a repeated operation and count its calls."""

        started = time.perf_counter()
        try:
            yield
        finally:
            self.add_seconds(name, time.perf_counter() - started)
            self.count(f"{name}.calls")

    @contextmanager
    def step(self, name: str, **details: Any) -> Iterator[dict[str, Any]]:
        """Time one pipeline step. The yielded dict accepts extra details."""

        record: dict[str, Any] = {"name": name, "status": "running", **details}
        with self._lock:
            self._steps.append(record)
            self.flush()
        started = time.perf_counter()
        try:
            yield record
        except BaseException:
            record["status"] = "error"
            raise
        else:
            record["status"] = "ok"
        finally:
            record["seconds"] = round(time.perf_counter() - started, 3)
            self.flush()

    def scene(self, index: int, **fields: Any) -> None:
        """Merge details for a 1-based scene index."""

        with self._lock:
            self._scenes.setdefault(index, {"index": index}).update(fields)

    def finish(self, status: str) -> None:
        with self._lock:
            self._status = status
            self.flush()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._meta,
                "startedAt": self._started_at,
                "updatedAt": _now_iso(),
                "status": self._status,
                "totalSeconds": round(time.perf_counter() - self._started_perf, 3),
                "steps": [dict(step) for step in self._steps],
                "counters": dict(sorted(self._counters.items())),
                "durations": {key: round(value, 3) for key, value in sorted(self._durations.items())},
                "scenes": [dict(self._scenes[index]) for index in sorted(self._scenes)],
            }

    def flush(self) -> None:
        with self._lock:
            if self._path is None:
                return
            try:
                atomic_write_json(self._path, self.snapshot())
            except OSError:
                # Instrumentation must never break a run.
                pass


METRICS = Metrics()
