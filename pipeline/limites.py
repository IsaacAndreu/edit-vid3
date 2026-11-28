"""What one partner may start: one background job of each kind at a time, at most `socios.trabajos_dia` jobs and new
videos a day, and at most `socios.disco_gb` of their own uploads on the disk. You (the owner) have no limits here.

    socios:
      trabajos_dia: 30     # trabajos (apertura, miniatura IA, reintento, CapCut…) y vídeos nuevos por socio al día
      disco_gb: 30         # lo que ocupan sus vídeos en materiales/ y sus subidas de apertura

The day's count is out/_tareas/socios.json, shared by every studio thread and process.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from .fileio import read_json, update_json

LEDGER = Path("out") / "_tareas" / "socios.json"
ARG = re.compile(r"--[a-z][a-z0-9-]*(?:=.*)?", re.S)


class Limit(ValueError):
    """A partner's limit: the studio answers 429 with this message."""


def settings(root: Path) -> dict[str, float]:
    from .context import load_config

    cfg = (load_config(root / "config.yaml").get("socios") or {}) if (root / "config.yaml").is_file() else {}
    return {"jobs": float(cfg.get("trabajos_dia", 30)), "disk_gb": float(cfg.get("disco_gb", 30))}


def kind(name: str) -> str:
    """The kind of a job from its name: «apertura-3fa2…» → apertura, «miniatura-ia-<vídeo>» → miniatura-ia."""

    match = re.match(r"miniatura-ia|[a-z]+", name)
    return match.group() if match else name


def check_args(args: list[str]) -> None:
    """Every value that reaches main.py's command line goes glued to its option (`--opción=valor`), so a value that
    starts with «-» is never read as an option of its own."""

    for arg in args:
        if not ARG.fullmatch(arg):
            raise ValueError("Argumento no válido para la tarea")


def charge(root: Path, who: str, running_kinds: list[str] | None = None, wanted: str = "") -> None:
    """Counts one job (or new video) of the partner `who` for today; raises Limit when one of that kind is already
    running or the day's limit is reached. Nothing for the owner ("")."""

    if not who:
        return
    if wanted and wanted in (running_kinds or []):
        raise Limit("Ya tienes una tarea de ese tipo en marcha: espera a que termine")
    most = int(settings(root)["jobs"])
    today = time.strftime("%Y-%m-%d")
    refused: list[bool] = []

    def add(ledger: Any) -> Any:
        ledger = ledger if isinstance(ledger, dict) else {}
        mine = ledger.get(who) if isinstance(ledger.get(who), dict) else {}
        count = int(mine.get("jobs") or 0) if mine.get("day") == today else 0
        if most > 0 and count >= most:
            refused.append(True)
            return None
        ledger[who] = {**mine, "day": today, "jobs": count + 1}
        return ledger

    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    update_json(path, add, {})
    if refused:
        raise Limit(f"Has llegado al máximo de {most} tareas por hoy: mañana se pueden lanzar más")


def own_upload(root: Path, who: str, ticket: str) -> None:
    """Remembers that the apertura upload `ticket` is this partner's (it counts in their disk)."""

    if not who:
        return

    def add(ledger: Any) -> Any:
        ledger = ledger if isinstance(ledger, dict) else {}
        mine = ledger.get(who) if isinstance(ledger.get(who), dict) else {}
        tickets = [t for t in mine.get("uploads") or [] if isinstance(t, str)][-500:]
        ledger[who] = {**mine, "uploads": [*tickets, ticket]}
        return ledger

    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    update_json(path, add, {})


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for folder, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.stat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


def disk_used(root: Path, who: str, mine: list[str]) -> int:
    """Bytes of the partner's own: the materials of the videos of their channels and their apertura uploads."""

    from .context import video_folders
    from .web import _channel_of

    total = sum(_size(folder) for folder in video_folders(root) if _channel_of(root, folder) in mine)
    tickets = (read_json(root / LEDGER, {}).get(who) or {}).get("uploads") or []
    folder = root / "out" / "_tareas"
    return total + sum(_size(folder / f"apertura-{t}.mp4") for t in tickets if re.fullmatch(r"[0-9a-f]{12}", str(t)))


def check_disk(root: Path, who: str, mine: list[str], adding: int) -> None:
    """Raises Limit when `adding` more bytes would take the partner past `socios.disco_gb`."""

    if not who:
        return
    quota = settings(root)["disk_gb"] * 1024 ** 3
    if quota > 0 and disk_used(root, who, mine) + adding > quota:
        raise Limit(f"Tu espacio está lleno ({settings(root)['disk_gb']:g} GB): archiva vídeos viejos para subir más")
