"""Machine-level chores for a server with a small disk and no one watching it.

- Resources: while a stage runs, the peak RAM in use and CPU load of the whole machine (sampled every 2 s) go into
  its marker, so diagnostico.md shows which stage needs the most (psutil if installed, else /proc on Linux).
- Cleanup (`cleanup:` in config.local.yaml, off by default): after a video is finished, its heavy work files
  (render segments, downloaded clips, editor proxies) are deleted, keeping the final video, the plans and the logs;
  and YouTube/Pexels downloads in cache/ not used for `cache_days` days are deleted.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Any

from .context import RunContext

HEAVY = ("render", "media", "media_fallback", "editor", "motion", "coldopen", "spotlight")
CACHED = ("videos", "pexels")


def _snapshot() -> tuple[float | None, float | None]:
    """(GB of RAM in use, CPU busy 0-100 since the last call) for the whole machine."""

    try:
        import psutil

        return psutil.virtual_memory().used / 1e9, psutil.cpu_percent(interval=None)
    except ImportError:
        pass
    try:
        info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
        used = (int(info["MemTotal"].split()[0]) - int(info["MemAvailable"].split()[0])) / 1e6
    except (OSError, KeyError, ValueError):
        return None, None
    try:
        fields = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        idle, total = fields[3] + fields[4], sum(fields)
        last = getattr(_snapshot, "last", None)
        _snapshot.last = (idle, total)                       # type: ignore[attr-defined]
        cpu = None if last is None or total == last[1] else 100 * (1 - (idle - last[0]) / (total - last[1]))
    except (OSError, ValueError, IndexError):
        cpu = None
    return used, cpu


class Sampler:
    """`with Sampler() as s: …` → s.ram_peak (GB), s.cpu_peak and s.cpu_mean (%) of the machine meanwhile."""

    def __init__(self, every: float = 2.0) -> None:
        self.every = every
        self.ram_peak: float | None = None
        self.cpu_peak: float | None = None
        self._cpu: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    @property
    def cpu_mean(self) -> float | None:
        return sum(self._cpu) / len(self._cpu) if self._cpu else None

    def _loop(self) -> None:
        _snapshot()
        while not self._stop.wait(self.every):
            ram, cpu = _snapshot()
            if ram is not None:
                self.ram_peak = max(self.ram_peak or 0.0, ram)
            if cpu is not None:
                self.cpu_peak = max(self.cpu_peak or 0.0, cpu)
                self._cpu.append(cpu)

    def __enter__(self) -> "Sampler":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def fields(self) -> dict[str, float]:
        out = {}
        if self.ram_peak is not None:
            out["ramPeakGb"] = round(self.ram_peak, 1)
        if self.cpu_peak is not None:
            out["cpuPeak"] = round(self.cpu_peak)
        if self.cpu_mean is not None:
            out["cpuMean"] = round(self.cpu_mean)
        return out


def _size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else 0


def after_video(ctx: RunContext) -> None:
    """A finished video's heavy work files, when cleanup.after_video is on."""

    cfg = ctx.section("cleanup")
    if not cfg.get("after_video") or not (ctx.out_dir / "video-final.mp4").is_file():
        return
    freed = 0
    for name in HEAVY:
        folder = ctx.work_dir / name
        if folder.is_dir():
            freed += _size(folder)
            shutil.rmtree(folder, ignore_errors=True)
    print(f"   Limpieza: {freed / 1e9:.1f} GB de temporales de {ctx.slug} borrados (quedan el vídeo, los planes y los logs)")


def old_cache(ctx: RunContext) -> None:
    """Downloads in cache/ (YouTube clips, Pexels) not touched for cleanup.cache_days days."""

    days = float(ctx.section("cleanup").get("cache_days", 0) or 0)
    if days <= 0:
        return
    limit = time.time() - days * 86400
    freed = 0
    for name in CACHED:
        folder = ctx.cache_dir / name
        for path in folder.rglob("*") if folder.is_dir() else []:
            if path.is_file() and path.stat().st_mtime < limit:
                freed += path.stat().st_size
                path.unlink(missing_ok=True)
    if freed:
        print(f"Limpieza de caché: {freed / 1e9:.1f} GB de descargas de hace más de {days:g} días")
