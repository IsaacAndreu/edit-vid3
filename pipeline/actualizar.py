"""`python main.py --actualizar [horas]`: update the server without cutting a third-party video half way.

1. Writes out/_actualizando: the queue stops STARTING third-party videos (simulations and drawn ones go on).
2. Waits, at most `horas` (3), until no third-party video is running (their downloads and renders are what a
   restart wastes). With no gap in time it gives up and changes nothing.
3. git pull --ff-only (local changes on the server are never overwritten: it stops and says which).
4. pip install -r requirements.txt only when it changed, npm ci only when package-lock.json changed.
5. Restarts edit-vid3, edit-vid3-web and edit-vid3-bot, and removes the mark (also when anything fails).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

FLAG = "out/_actualizando"
FLAG_MAX_AGE = 6 * 3600          # a mark left behind by a killed update never stops the queue for long
SERVICES = ("edit-vid3", "edit-vid3-web", "edit-vid3-bot")


def updating(root: Path) -> bool:
    path = root / FLAG
    return path.is_file() and time.time() - path.stat().st_mtime < FLAG_MAX_AGE


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def running(root: Path) -> list[tuple[str, str]]:
    """(video, stage) of every video a process is working on right now."""

    out = []
    for current in sorted((root / "work").glob("*/current.json")) if (root / "work").is_dir() else []:
        try:
            info = json.loads(current.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not info.get("ended") and _alive(int(info.get("pid") or 0)):
            out.append((current.parent.name, str(info.get("stage") or "?")))
    return out


def third_party(root: Path) -> list[tuple[str, str]]:
    import main

    return [(slug, stage) for slug, stage in running(root) if not main.is_drawn(root, slug)]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=300)


def main(root: Path, max_hours: float = 3.0, every: float = 60.0) -> int:
    flag = root / FLAG
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(str(time.time()))
    try:
        deadline = time.time() + max_hours * 3600
        said = None
        while True:
            busy = third_party(root)
            if not busy:
                break
            if time.time() > deadline:
                print(f"No hubo hueco en {max_hours:g} h ({', '.join(s for s, _ in busy)} sigue): no he tocado nada. "
                      "Prueba otra vez más tarde o con más horas: python main.py --actualizar 6")
                return 2
            line = ", ".join(f"{s} ({st})" for s, st in busy)
            if line != said:
                print(f"{time.strftime('%H:%M')} · espero a que acabe: {line}. Mientras, la cola no empieza "
                      "vídeos de terceros nuevos (las simulaciones siguen)")
                said = line
            flag.write_text(str(time.time()))          # still waiting: the mark stays fresh
            time.sleep(every)
        before = _git(root, "rev-parse", "HEAD").stdout.strip()
        pulled = _git(root, "pull", "--ff-only")
        if pulled.returncode != 0:
            print("git pull no se pudo (no he reiniciado nada):\n" + (pulled.stderr or pulled.stdout).strip()[-600:]
                  + "\nSi hay cambios locales en el servidor: git status, y guárdalos (git stash) o descártalos.")
            return 1
        after = _git(root, "rev-parse", "HEAD").stdout.strip()
        changed = set(_git(root, "diff", "--name-only", before, after).stdout.split()) if before != after else set()
        print(f"Código: {before[:7]} → {after[:7]}" if changed else "El código ya estaba al día")
        if "requirements.txt" in changed:
            print("requirements.txt cambió: pip install…")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=root, check=False)
        if "package-lock.json" in changed and shutil.which("npm"):
            print("package-lock.json cambió: npm ci…")
            subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=root, check=False)
        if shutil.which("systemctl"):
            names = [s for s in SERVICES if subprocess.run(["systemctl", "cat", s], capture_output=True).returncode == 0]
            flag.unlink(missing_ok=True)               # before the restart: the new watcher must not see it
            restarted = subprocess.run(["systemctl", "restart", *names], capture_output=True, text=True)
            print(("Reiniciado: " + ", ".join(names)) if restarted.returncode == 0
                  else f"systemctl restart falló: {restarted.stderr.strip()[-300:]}")
            return restarted.returncode
        print("Sin systemctl: reinicia el programa a mano")
        return 0
    finally:
        flag.unlink(missing_ok=True)
