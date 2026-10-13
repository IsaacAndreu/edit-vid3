"""What protects the home connection from YouTube right now, in one screen (never a key or cookie value):

    python main.py --comprobar-proteccion

The code running, each way out and its quarantine, the last «are you a bot» and the recovery window (searches only by
the API), whether an account is ever used for a bot check, which API keys are set (names only) and today's quota.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .context import RunContext


def report(root: Path) -> list[str]:
    from .sourcing.youtube import LAST_BLOCK, proxy_list, quarantined_until
    from .ytapi import YouTubeAPI, reset_text

    ctx = RunContext.create("_proteccion", root=root)
    yt = ctx.section("sourcing").get("youtube", {})
    head = subprocess.run(["git", "log", "--oneline", "-1"], cwd=root, capture_output=True, text=True).stdout.strip()
    lines = [f"Código: {head or '¿sin git?'}"]
    import os

    ways = proxy_list(os.environ.get("YOUTUBE_PROXY"), yt.get("proxies"), yt.get("proxy")) or [""]
    now = time.time()
    from .sourcing.common import HourlyBudget
    from .sourcing.youtube import BUDGET_SUFFIX, pacer_name

    per_hour = float(yt.get("requests_per_hour", 1500) or 0)
    for way in ways:
        until = quarantined_until(ctx.cache_dir, way)
        name = way.split("@")[-1] if way else "servidor (directo)"
        used = HourlyBudget(ctx.cache_dir / "videos" / (pacer_name(way) + BUDGET_SUFFIX), per_hour).used()
        lines.append(f"Conexión {name}: " + (f"EN CUARENTENA {int((until - now) / 60)} min más" if until > now else "libre")
                     + (f" · última hora {used:.0f}/{per_hour:.0f} peticiones" if per_hour else " · sin límite por hora"))
    lines.append("Si la API no tiene búsquedas: " + ("busca con yt-dlp (api_overflow: ytdlp)"
                 if str(yt.get("api_overflow", "esperar")).lower() == "ytdlp" else "el vídeo espera, nada por yt-dlp"))
    try:
        last = float((ctx.cache_dir / "videos" / LAST_BLOCK).read_text().strip())
        hours = float(yt.get("bot_recovery_hours", 72))
        ago = (now - last) / 3600
        lines.append(f"Último «no eres un bot»: hace {ago:.1f} h · "
                     + (f"recuperación {hours - ago:.0f} h más: búsquedas SOLO por la API" if ago < hours else "fuera de recuperación"))
    except (OSError, ValueError):
        lines.append("Último «no eres un bot»: ninguno registrado")
    paused = (root / "out" / "_pausa_youtube").is_file()
    lines.append(f"Cola pausada por YouTube: {'sí' if paused else 'no'} · pausa manual: "
                 f"{'sí' if (root / 'out' / '_pausa').is_file() else 'no'} · prueba cada "
                 f"{ctx.section('watch').get('youtube_probe_minutes', 60)} min")
    lines.append(f"Cookies: modo {yt.get('cookies', 'rotate')} · ante «no eres un bot»: "
                 + ("SÍ usa cuenta (cookies_on_bot: true)" if yt.get("cookies_on_bot") else "nunca"))
    names = [n for n in ("YOUTUBE_API_KEY", "YOUTUBE_API_KEYS", "YOUTUBE_API_KEY_DEV") if ctx.env(n, required=False)]
    many = len([k for k in ctx.env("YOUTUBE_API_KEYS", required=False).split(",") if k.strip()])
    lines.append("Claves de la API en .env: " + (", ".join(names) or "ninguna")
                 + (f" · YOUTUBE_API_KEYS: {many} claves, una tras otra" if many else ""))
    api = YouTubeAPI(ctx)
    if api.keys:
        q = api.quota()
        lines.append(f"Cuota de hoy: {q['searches']}/{q['searchesPerDay']} búsquedas, {q['used']}/{q['total']} unidades · "
                     f"se renueva {reset_text()}")
    return lines
