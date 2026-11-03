"""`python main.py --doctor`: what would make a video fail half way, checked in seconds and without asking anyone.

Nothing goes to YouTube, the AI providers or the voice service: keys are only looked for in .env (never shown), tools
on the PATH, the Python packages on disk, the proxy with a TCP connection to its port, the API quota from the local
ledger, and the services with systemctl. Each line is ✅ fine, ⚠️ works but worse, ❌ a video will fail. Also in the
studio's «Estado del servidor».
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Any

OK, WARN, FAIL = "ok", "aviso", "error"
ICON = {OK: "✅", WARN: "⚠️", FAIL: "❌"}

REQUIRED = {"LLM_API_KEY": "planificador, gráficos y textos", "OPENAI_API_KEY": "el juez de los clips (visión)"}
OPTIONAL = {"GENAIPRO_API_KEY": "voces automáticas", "YOUTUBE_API_KEY": "búsquedas de YouTube sin bloqueos",
            "SERPER_API_KEY": "fotos de Google Imágenes", "PEXELS_API_KEY": "vídeos de recurso",
            "PIXABAY_API_KEY": "fotos de Pixabay", "TELEGRAM_BOT_TOKEN": "avisos por Telegram",
            "WEB_PASSWORD": "contraseña de la web"}
PACKAGES = {"torch": "análisis CLIP", "open_clip": "análisis CLIP", "faster_whisper": "sincronizar la voz",
            "cv2": "fotogramas y hojas del juez", "yt_dlp": "YouTube", "scenedetect": "cortes de escena"}
SERVICES = ("edit-vid3", "edit-vid3-web", "edit-vid3-bot")
MIN_FREE_GB, LOW_FREE_GB = 20, 50
YTDLP_MAX_DAYS = 45                # YouTube changes often: an old yt-dlp is the usual cause of failed downloads
COOKIES_MAX_DAYS = 14


def _row(level: str, area: str, text: str) -> dict[str, str]:
    return {"level": level, "area": area, "text": text}


def keys(root: Path) -> list[dict[str, str]]:
    from .context import RunContext

    ctx = RunContext.create("_doctor", root=root, config={})
    rows = []
    for name, use in REQUIRED.items():
        rows.append(_row(OK if ctx.env(name, required=False) else FAIL, "claves", f"{name} ({use})"
                         + ("" if ctx.env(name, required=False) else ": falta en .env")))
    missing = []
    for name, use in OPTIONAL.items():
        present = ctx.env(name, required=False) or (name == "YOUTUBE_API_KEY" and ctx.env("YOUTUBE_API_KEYS", required=False))
        if not present:
            missing.append(f"{name} ({use})")
    rows.append(_row(WARN if missing else OK, "claves", "sin " + ", ".join(missing) if missing else "todas las opcionales están"))
    if ctx.env("TELEGRAM_BOT_TOKEN", required=False) and not ctx.env("TELEGRAM_CHAT_ID", required=False):
        rows.append(_row(WARN, "claves", "TELEGRAM_BOT_TOKEN sin TELEGRAM_CHAT_ID: el bot no sabe a quién avisar"))
    return rows


def ytdlp_age(version: str, today: date | None = None) -> int | None:
    try:
        y, m, d = (int(x) for x in version.split(".")[:3])
        return ((today or date.today()) - date(y, m, d)).days
    except (ValueError, TypeError):
        return None


def tools(root: Path) -> list[dict[str, str]]:
    rows = []
    missing = [t for t in ("ffmpeg", "ffprobe", "node", "npx") if not shutil.which(t)]
    rows.append(_row(FAIL if missing else OK, "herramientas", "falta " + ", ".join(missing) + " en el PATH" if missing
                     else "ffmpeg, ffprobe, node y npx"))
    remotion = (root / "node_modules" / "remotion").is_dir()
    rows.append(_row(OK if remotion else FAIL, "herramientas", "Remotion instalado" if remotion
                     else "no está node_modules/remotion: npm ci en la carpeta del proyecto"))
    deno = shutil.which("deno") or (Path.home() / ".deno" / "bin" / "deno").is_file()
    rows.append(_row(OK if deno else WARN, "herramientas", "deno (yt-dlp lo usa para YouTube)" if deno
                     else "sin deno: yt-dlp saca menos formatos de YouTube"))
    try:
        from yt_dlp.version import __version__ as version

        age = ytdlp_age(version)
        old = age is not None and age > YTDLP_MAX_DAYS
        rows.append(_row(WARN if old else OK, "herramientas", f"yt-dlp {version}"
                         + (f": tiene {age} días, actualízalo (pip install -U yt-dlp)" if old else "")))
    except ImportError:
        pass
    missing = sorted({use for pkg, use in PACKAGES.items() if importlib.util.find_spec(pkg) is None})
    rows.append(_row(FAIL if missing else OK, "python", "faltan paquetes para: " + ", ".join(missing)
                     + " (pip install -r requirements.txt)" if missing else "paquetes de Python instalados"))
    return rows


def machine(root: Path) -> list[dict[str, str]]:
    rows = []
    free = shutil.disk_usage(root).free / 1e9
    rows.append(_row(FAIL if free < MIN_FREE_GB else WARN if free < LOW_FREE_GB else OK, "disco",
                     f"{free:.0f} GB libres" + (" (la cola no arranca con menos de 20)" if free < MIN_FREE_GB else "")))
    try:
        info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
        available = int(info["MemAvailable"].split()[0]) / 1e6
        rows.append(_row(WARN if available < 3 else OK, "memoria", f"{available:.1f} GB de RAM libres"))
    except (OSError, KeyError, ValueError):
        pass
    return rows


def youtube(root: Path) -> list[dict[str, str]]:
    from . import servidor, ytpause
    from .context import RunContext
    from .sourcing.youtube import proxy_list, proxy_reachable

    rows = []
    paused = ytpause.paused(root)
    if paused:
        rows.append(_row(WARN, "youtube", f"YouTube en pausa: {paused.get('reason', 'bloqueado')} (se reintenta solo)"))
    cfg = RunContext.create("_doctor", root=root).section("sourcing").get("youtube", {})
    proxies = proxy_list(os.environ.get("YOUTUBE_PROXY"), cfg.get("proxies"), cfg.get("proxy"))
    down = [i + 1 for i, p in enumerate(proxies) if not proxy_reachable(p, timeout=3)]
    if proxies:
        rows.append(_row(FAIL if len(down) == len(proxies) else WARN if down else OK, "youtube",
                         f"{len(proxies) - len(down)} de {len(proxies)} salidas por proxy responden"
                         + (f" (no responde la {', '.join(map(str, down))})" if down else "")))
    quota = servidor.api_quota(root)
    if quota is not None:
        left = int(quota.get("searchesLeft", 0))
        rows.append(_row(WARN if left <= 0 else OK, "youtube", f"API: {left} búsquedas libres hoy"
                         + (f", vuelven {quota.get('reset')}" if left <= 0 else "")))
    files = [Path(str(cfg.get("cookies_file") or "")).expanduser()] if cfg.get("cookies_file") else []
    for folder in (root / "cookies", Path(str(cfg.get("cookies_dir") or "~/.config/edit-vid3/cookies")).expanduser()):
        files += sorted(folder.glob("*.txt")) if folder.is_dir() else []
    files = [f for f in files if f.is_file()]
    if files:
        oldest = max((time.time() - f.stat().st_mtime) / 86400 for f in files)
        rows.append(_row(WARN if oldest > COOKIES_MAX_DAYS else OK, "youtube",
                         f"{len(files)} archivo(s) de cookies, el más viejo de hace {oldest:.0f} días"
                         + (": si YouTube pide iniciar sesión, expórtalas otra vez" if oldest > COOKIES_MAX_DAYS else "")))
    return rows


def services(root: Path) -> list[dict[str, str]]:
    if not shutil.which("systemctl"):
        return []
    rows = []
    for name in SERVICES:
        try:
            state = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if state in ("", "unknown") or "could not be found" in state:
            continue
        rows.append(_row(OK if state == "active" else FAIL, "servicios", f"{name}: {state}"
                         + ("" if state == "active" else f" (journalctl -u {name} -n 50)")))
    if (root / "out" / "_pausa").is_file():
        rows.append(_row(WARN, "servicios", "la cola está en pausa (out/_pausa)"))
    return rows


def code(root: Path) -> list[dict[str, str]]:
    try:
        changed = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                                 capture_output=True, text=True, timeout=20).stdout.split("\n")
    except (OSError, subprocess.SubprocessError):
        return []
    changed = [line[3:] for line in changed if line.strip()]
    return [_row(WARN if changed else OK, "código", "cambios sin subir en el servidor: " + ", ".join(changed[:5])
                 + " (git pull puede fallar)" if changed else "sin cambios locales")]


CHECKS = (keys, tools, machine, youtube, services, code)


def run(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for check in CHECKS:
        try:
            rows += check(root)
        except Exception as error:     # one check that breaks never hides the others
            rows.append(_row(WARN, check.__name__, f"no se pudo revisar: {str(error)[:160]}"))
    return rows


def text(rows: list[dict[str, str]]) -> str:
    worst = FAIL if any(r["level"] == FAIL for r in rows) else WARN if any(r["level"] == WARN for r in rows) else OK
    head = {OK: "Todo listo", WARN: "Funciona, con avisos", FAIL: "Hay algo que hará fallar vídeos"}[worst]
    return "\n".join([f"{ICON[worst]} {head}", *(f"{ICON[r['level']]} {r['area']}: {r['text']}" for r in rows)])


def cached(root: Path, max_age: float = 600) -> dict[str, Any]:
    """The studio page refreshes every 15 s: the last check while it is younger than 10 minutes."""

    path = root / "out" / "_doctor.json"
    try:
        data = json.loads(path.read_text("utf-8"))
        if time.time() - float(data.get("at", 0)) < max_age:
            return data
    except (OSError, ValueError):
        pass
    data = {"at": time.time(), "rows": run(root)}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def main(root: Path) -> int:
    rows = run(root)
    print(text(rows))
    (root / "out").mkdir(exist_ok=True)
    (root / "out" / "_doctor.json").write_text(json.dumps({"at": time.time(), "rows": rows}, ensure_ascii=False),
                                              encoding="utf-8")
    return 1 if any(r["level"] == FAIL for r in rows) else 0
