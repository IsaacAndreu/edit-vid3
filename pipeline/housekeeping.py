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
    try:
        trim_videos(ctx)
    except Exception:
        pass


MEDIA_SUFFIXES = (".mp4", ".mkv", ".webm", ".m4a", ".part")


def _in_use(ctx: RunContext) -> set[Path]:
    """The analysis windows of unfinished videos (their judge/fallback still read them)."""

    import json

    keep: set[Path] = set()
    work = ctx.root / "work"
    for scores in work.glob("*/scores") if work.is_dir() else []:
        if (ctx.root / "out" / scores.parent.name / "video-final.mp4").is_file():
            continue
        for path in scores.glob("*.json"):
            try:
                for option in json.loads(path.read_text("utf-8")).get("options", []):
                    if option.get("analysisPath"):
                        keep.add((ctx.root / option["analysisPath"]).resolve())
            except (OSError, ValueError):
                continue
    return keep


def trim_videos(ctx: RunContext, now: float | None = None) -> float:
    """cache/videos/ kept small, always (not only with cleanup.cache_days): the WHOLE YouTube sources fetched to cut
    clips from (full_*, up to 600 MB each: 193 GB on the server after two weeks) go once untouched for
    `cleanup.whole_hours` (12) — they only help while that video's clips are being cut; then, while the folder is
    above `cleanup.videos_max_gb` (50), the oldest downloaded media go first. Storyboards and metadata stay. GB freed."""

    cfg = ctx.section("cleanup")
    folder = ctx.cache_dir / "videos"
    if not folder.is_dir():
        return 0.0
    now = now or time.time()
    hours = float(cfg.get("whole_hours", 12))
    freed = 0
    media = []
    for path in folder.rglob("*"):
        if not path.is_file() or path.suffix not in MEDIA_SUFFIXES or path.parent.name == "sb":
            continue
        stat = path.stat()
        if path.name.startswith(("full_", "wip_")) and now - stat.st_mtime > hours * 3600:
            freed += stat.st_size
            path.unlink(missing_ok=True)
            continue
        media.append((stat.st_mtime, stat.st_size, path))
    cap = float(cfg.get("videos_max_gb", 50)) * 1e9
    total = sum(size for _, size, _ in media)
    keep = _in_use(ctx) if total > cap else set()
    for mtime, size, path in sorted(media):
        if total <= cap:
            break
        if now - mtime < 2 * 3600 or path.resolve() in keep:     # the video being made / an unfinished one's analysis
            continue
        path.unlink(missing_ok=True)
        total -= size
        freed += size
    if freed:
        print(f"Limpieza de cache/videos: {freed / 1e9:.1f} GB (vídeos de YouTube enteros y descargas antiguas)")
    return freed / 1e9


def old_cache(ctx: RunContext) -> None:
    """Downloads in cache/ (YouTube clips, Pexels) not touched for cleanup.cache_days days."""

    try:
        trim_videos(ctx)
    except Exception as error:                        # a cleanup never stops the queue
        print(f"(Limpieza de cache/videos no hecha: {str(error)[:100]})")
    days = float(ctx.section("cleanup").get("cache_days", 0) or 0)
    if days <= 0:
        return
    try:
        from . import library

        library.protect(ctx)                  # the library's thumbnails are kept out of this cleanup
    except Exception:
        pass
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


# --- videos already on YouTube: their heavy files go ----------------------------------------------------------------

PUBLISHED = "publicado.json"          # in out/<slug>/: {at, url} — marked in the studio or found on your channel
REMOVED = "borrado.json"              # in out/<slug>/: the heavy files were deleted (the video counts as done)
OUT_HEAVY = ("*.mp4", "shorts/*.mp4", "*.mov", "*.mkv", "*.wav")


def is_done(root: Path, slug: str) -> bool:
    """A finished video: its final file, or already uploaded and cleaned up (never made again by the queue)."""

    out = root / "out" / slug
    return (out / "video-final.mp4").is_file() or (out / REMOVED).is_file()


def _read(path: Path) -> dict[str, Any]:
    import json

    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def published(root: Path, slug: str) -> dict[str, Any]:
    return _read(root / "out" / slug / PUBLISHED)


def mark_published(root: Path, slug: str, url: str = "", value: bool = True) -> dict[str, Any]:
    import json

    out = root / "out" / slug
    if not out.is_dir():
        raise FileNotFoundError(slug)
    path = out / PUBLISHED
    if not value:
        path.unlink(missing_ok=True)
        return {}
    data = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "url": url.strip()}
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def _titles(root: Path, slug: str) -> list[str]:
    """The titles this video may have been uploaded with: titulo.txt and the ones proposed in youtube.txt."""

    import re

    from .context import find_video

    found = []
    title = find_video(root, slug) / "titulo.txt"
    if title.is_file():
        found.append(title.read_text("utf-8").strip())
    youtube = root / "out" / slug / "youtube.txt"
    if youtube.is_file():
        found += [m.group(1).strip() for m in re.finditer(r"^\s*\d\.\s+(.+)$", youtube.read_text("utf-8"), re.M)][:5]
    return [t for t in found if t]


def _same_title(a: str, b: str) -> bool:
    import re
    import unicodedata

    def words(text: str) -> set[str]:
        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
        return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 2}

    x, y = words(a), words(b)
    return bool(x and y) and len(x & y) / max(1, min(len(x), len(y))) >= 0.8


def find_uploads(root: Path) -> list[str]:
    """Finished videos that are already on your channel (same title), marked as published. Needs your channel per
    profile (studio → Ajustes) and YOUTUBE_API_KEYS; ~2 API units per channel."""

    from .context import video_folders
    from .mychannel import handle_for
    from .web import _channel_of
    from .ytapi import YouTubeAPI

    pending: dict[str, list[str]] = {}
    for folder in video_folders(root):
        slug = folder.name
        if (root / "out" / slug / "video-final.mp4").is_file() and not published(root, slug):
            pending.setdefault(_channel_of(root, folder), []).append(slug)
    marked = []
    for channel, slugs in pending.items():
        try:
            handle = handle_for(root, channel) if channel else ""
            if not handle:
                continue
            api = YouTubeAPI(RunContext.create("_subidos", root=root, channel=channel))
            if not api.keys:
                return marked
            info = api.channel(handle)
            uploads = api.uploads(info["uploads"], 30) if info.get("uploads") else []
        except Exception as error:                      # never stops the queue
            print(f"   Subidos ({channel}): {str(error)[:120]}")
            continue
        for slug in slugs:
            hit = next((u for u in uploads for t in _titles(root, slug) if _same_title(t, u["title"])), None)
            if hit:
                mark_published(root, slug, hit["url"])
                marked.append(slug)
                print(f"   {slug}: ya está en YouTube ({hit['url']})")
    return marked


def rotate_published(root: Path, config: dict[str, Any], now: float | None = None) -> float:
    """cleanup.published_days (7 in the server's config.local.yaml; unset = never): a video uploaded that long ago loses its heavy files — the final video, previews,
    Shorts and the work clips — and keeps titles, thumbnails, the diagnosis, the logs and the frames the studio's
    «Errores» page needs. Also when the disk has less than cleanup.min_free_gb free: the oldest uploads first.
    Videos not marked as uploaded are never touched. Returns the GB freed."""

    import json

    from .context import video_folders

    cfg = config.get("cleanup") or {}
    if cfg.get("published_days") is None:            # only where it is set (the server's config.local.yaml), never by surprise
        return 0.0
    days = float(cfg["published_days"])
    if days < 0:
        return 0.0
    now = now or time.time()
    candidates = []
    for folder in video_folders(root):
        out = root / "out" / folder.name
        mark = published(root, folder.name)
        if mark and not (out / REMOVED).is_file() and (out / "video-final.mp4").is_file():
            at = time.mktime(time.strptime(mark["at"][:19], "%Y-%m-%dT%H:%M:%S")) if mark.get("at") else now
            candidates.append((at, folder.name))
    candidates.sort()
    min_free = float(cfg.get("min_free_gb", 30))
    freed = 0
    for at, slug in candidates:
        disk_low = shutil.disk_usage(root).free / 1e9 < min_free
        if now - at < days * 86400 and not disk_low:
            continue
        try:
            from .feedback import shots, frame

            for shot in shots(root, slug):              # «Errores» keeps working without the final video
                frame(root, slug, shot["id"])
        except Exception:
            pass
        out, work = root / "out" / slug, root / "work" / slug
        files = [p for pattern in OUT_HEAVY for p in out.glob(pattern) if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        for p in files:
            p.unlink(missing_ok=True)
        for name in HEAVY:
            if (work / name).is_dir():
                size += _size(work / name)
                shutil.rmtree(work / name, ignore_errors=True)
        (out / REMOVED).write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "gb": round(size / 1e9, 2),
                                               "why": "espacio" if disk_low else f"subido hace {days:g}+ días"}, indent=1),
                                   encoding="utf-8")
        freed += size
        print(f"   {slug}: subido a YouTube → borrados {size / 1e9:.1f} GB (vídeo final, previas, Shorts, clips)")
    return freed / 1e9


def published_chores(root: Path) -> None:
    """For the watcher and the queue: find the uploads on your channel, then free the space of the old ones."""

    try:
        config = RunContext.create("_subidos", root=root).config
    except Exception:
        return
    try:
        find_uploads(root)
    except Exception as error:
        print(f"(Comprobación de vídeos subidos no hecha: {str(error)[:100]})")
    try:
        gb = rotate_published(root, config)
        if gb:
            print(f"Limpieza de vídeos ya subidos: {gb:.1f} GB liberados")
        cleanup = config.get("cleanup") or {}
        if cleanup.get("published_days") is not None and shutil.disk_usage(root).free / 1e9 < float(cleanup.get("min_free_gb", 30)):
            from . import notify

            notify.send(RunContext.create("_subidos", root=root, config={}), "⚠️ Disco casi lleno",
                        f"Quedan {shutil.disk_usage(root).free / 1e9:.0f} GB libres en el servidor. Marca como subidos "
                        "los vídeos que ya estén en YouTube (estudio → el vídeo → «Ya está subido») para liberar espacio.")
    except Exception as error:
        print(f"(Limpieza de vídeos subidos no hecha: {str(error)[:100]})")
