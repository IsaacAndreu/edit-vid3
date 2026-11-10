"""Weekly backup of what cannot be made again: before a server move, or after a disk failure.

What goes in (a .tar.gz in `backup.dir`, /root/copias-edit-vid3 by default, outside the repository): this machine's
settings (config.local.yaml and .env — keys included, so the file is private: it never goes to git), every video's
folder in materiales/ (script, voice, its config), the studio's data (out/_*.json: settings, voices, calendar, ideas,
experiments, pilots…), each finished video's YouTube texts and «published» mark, the clip library's lists
(cache/library/*/library.json), the YouTube API journal and the list of refused videos. Not the videos, renders or
downloads: those can be made again. The last `backup.keep` (4) copies stay; the studio's «Estado del servidor» has the
newest one to download (to keep it on your PC or Google Drive).

    python main.py --copia      (the watcher makes one every `backup.days` (7) days by itself)
"""

from __future__ import annotations

import tarfile
import time
from pathlib import Path
from typing import Any

DEFAULT_DIR = "/root/copias-edit-vid3"
SKIP_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4a", ".wav"}       # media made again from the voice and the script


def _cfg(root: Path) -> dict[str, Any]:
    try:
        from .context import RunContext

        return RunContext.create("_copia", root=root).section("backup")
    except Exception:
        return {}


def folder(root: Path) -> Path:
    return Path(str(_cfg(root).get("dir") or DEFAULT_DIR)).expanduser()


def files(root: Path) -> list[Path]:
    """What goes in the copy, relative to the project."""

    out: list[Path] = []
    for name in ("config.local.yaml", ".env"):
        if (root / name).is_file():
            out.append(Path(name))
    materials = root / "materiales"
    for path in materials.rglob("*") if materials.is_dir() else []:
        if path.is_file() and (path.suffix.lower() not in SKIP_SUFFIXES or path.name == "voz.mp3"):
            out.append(path.relative_to(root))
    for pattern in ("out/_*.json", "out/_radar/*.json", "out/_ideas/**/*.json", "out/*/publicado.json",
                    "out/*/youtube.txt", "out/*/piloto.json", "cache/library/*/library.json",
                    "cache/ytapi/registro-*.jsonl", "cache/videos/.rechazados.json"):
        out += [p.relative_to(root) for p in root.glob(pattern) if p.is_file()]
    return sorted(set(out))


def make(root: Path) -> Path:
    target = folder(root)
    target.mkdir(parents=True, exist_ok=True)
    try:
        target.chmod(0o700)                      # keys inside: only this machine's admin reads it
    except OSError:
        pass
    path = target / f"edit-vid3-{time.strftime('%Y-%m-%d-%H%M')}.tar.gz"
    tmp = path.with_suffix(".part")
    with tarfile.open(tmp, "w:gz") as tar:
        for rel in files(root):
            tar.add(root / rel, arcname=str(rel))
    tmp.replace(path)
    path.chmod(0o600)
    keep = int(_cfg(root).get("keep", 4))
    for old in sorted(target.glob("edit-vid3-*.tar.gz"))[:-keep]:
        old.unlink(missing_ok=True)
    return path


def latest(root: Path) -> Path | None:
    found = sorted(folder(root).glob("edit-vid3-*.tar.gz")) if folder(root).is_dir() else []
    return found[-1] if found else None


def make_if_due(root: Path) -> Path | None:
    """A new copy when the newest is older than `backup.days` (7); 0 turns it off."""

    days = float(_cfg(root).get("days", 7) or 0)
    if days <= 0:
        return None
    last = latest(root)
    if last and time.time() - last.stat().st_mtime < days * 86400:
        return None
    return make(root)


def info(root: Path) -> dict[str, Any] | None:
    last = latest(root)
    if not last:
        return None
    return {"name": last.name, "mb": round(last.stat().st_size / 1e6, 1), "at": last.stat().st_mtime,
            "folder": str(last.parent)}
