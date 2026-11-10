"""The studio's «Estado del servidor» (⚙️ ▾): what used to need SSH commands, in one page.

- The machine: RAM, disk, CPU and load right now (psutil if installed, else /proc).
- The YouTube API: searches left today, when they would run out at today's pace, when they come back.
- The paid metadata proxy: GB bought (Ajustes → «Proxy: GB comprados», with the day), GB spent since then estimated
  from the requests logged per video (sourcing.youtube.metadata_proxy_mb_per_request) and how many videos that
  leaves. The provider has no balance API, so it is an estimate: correct it with a new top-up from its panel.
- The ways out to YouTube (home, work…): free, in quarantine, not answering, and their requests this hour.
- The queue: what each video not finished is doing or waiting for — the API quota, YouTube blocking, a turn (another
  video holds the network or CPU turn), a failure, its voice or script.

`check_proxy` (every hour from the watcher) sends one Telegram message a day when the proxy balance covers fewer than
`sourcing.youtube.metadata_proxy_min_videos` (10) videos.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROXY_STATE = "out/_proxy_saldo.json"


def machine(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"cores": os.cpu_count() or 0}
    try:
        import psutil

        mem = psutil.virtual_memory()
        out.update(ramTotal=mem.total / 1e9, ramUsed=(mem.total - mem.available) / 1e9, cpu=psutil.cpu_percent(interval=0.3))
    except ImportError:
        try:
            info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
            total, available = int(info["MemTotal"].split()[0]) / 1e6, int(info["MemAvailable"].split()[0]) / 1e6
            out.update(ramTotal=total, ramUsed=total - available)
        except (OSError, KeyError, ValueError):
            pass
        try:
            def sample() -> tuple[int, int]:
                fields = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
                return fields[3] + fields[4], sum(fields)

            idle1, total1 = sample()
            time.sleep(0.3)
            idle2, total2 = sample()
            out["cpu"] = 100 * (1 - (idle2 - idle1) / max(1, total2 - total1))
        except (OSError, ValueError, IndexError):
            pass
    try:
        swap = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
        out["swapUsed"] = (int(swap["SwapTotal"].split()[0]) - int(swap["SwapFree"].split()[0])) / 1e6
    except (OSError, KeyError, ValueError):
        pass
    try:
        out["load"] = os.getloadavg()[0]
    except (OSError, AttributeError):
        pass
    disk = shutil.disk_usage(root)
    out.update(diskTotal=disk.total / 1e9, diskFree=disk.free / 1e9)
    return {k: round(v, 1) if isinstance(v, float) else v for k, v in out.items()}


def api_quota(root: Path, now: datetime | None = None) -> dict[str, Any] | None:
    """Searches left today and, at today's pace, at what time they run out."""

    from .context import RunContext
    from .ytapi import YouTubeAPI, next_reset, reset_text

    try:
        api = YouTubeAPI(RunContext.create("_servidor", root=root))
        if not api.keys:
            return None
        q = api.quota()
    except Exception:
        return None
    now = now or datetime.now(timezone.utc)
    reset = next_reset(now)
    started = reset - timedelta(days=1)
    hours = max(0.25, (now - started).total_seconds() / 3600)
    pace = q["searches"] / hours                     # searches per hour since the reset
    out = {**q, "reset": reset_text(now), "perHour": round(pace, 1)}
    if q["searchesLeft"] <= 0:
        out["runsOut"] = "agotada"
    elif pace > 0:
        when = now + timedelta(hours=q["searchesLeft"] / pace)
        out["runsOut"] = "no se acaba hoy" if when >= reset else _local(when)
    return out


def _local(moment: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        return f"hacia las {moment.astimezone(ZoneInfo('Europe/Madrid')):%H:%M}"
    except Exception:
        return f"hacia las {moment:%H:%M} UTC"


def proxy_balance(root: Path) -> dict[str, Any] | None:
    """GB bought (Ajustes) minus GB spent since that day, from the requests logged through the metadata proxy."""

    from .budget import settings
    from .context import RunContext

    try:
        yt = RunContext.create("_servidor", root=root).section("sourcing").get("youtube") or {}
    except Exception:
        yt = {}
    if not (os.environ.get("YOUTUBE_METADATA_PROXY") or yt.get("metadata_proxy")):
        return None
    cfg = settings(root)
    bought = float(cfg.get("proxy_gb") or 0)
    since = str(cfg.get("proxy_since") or "")
    mb = float(yt.get("metadata_proxy_mb_per_request", 0.6))
    try:
        start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp() if since else 0.0
    except ValueError:
        start = 0.0
    requests, videos = 0, set()
    for path in (root / "work").glob("*/youtube_downloads.jsonl"):
        try:
            lines = path.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"metadatos"' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("proxy") == "metadatos" and float(row.get("ts") or 0) >= start:
                requests += 1
                videos.add(path.parent.name)
    used = requests * mb / 1024
    per_video = used / len(videos) if videos else 0.1
    out = {"bought": bought or None, "since": since or None, "usedGb": round(used, 2), "requests": requests,
           "videos": len(videos), "perVideoGb": round(per_video, 3), "usdPerGb": float(yt.get("metadata_proxy_usd_per_gb", 4.5))}
    if bought:
        left = max(0.0, bought - used)
        out.update(leftGb=round(left, 2), videosLeft=int(left / per_video) if per_video else None)
    return out


def check_proxy(root: Path, now: float | None = None) -> dict[str, Any] | None:
    """Every hour: one Telegram message a day when the proxy balance covers fewer than metadata_proxy_min_videos."""

    now = time.time() if now is None else now
    path = root / PROXY_STATE
    try:
        state = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        state = {}
    if now - float(state.get("checked") or 0) < 3600:
        return None
    balance = proxy_balance(root)
    state["checked"] = now
    if balance and balance.get("videosLeft") is not None:
        from .context import RunContext

        try:
            ctx = RunContext.create("_servidor", root=root)
            minimum = float((ctx.section("sourcing").get("youtube") or {}).get("metadata_proxy_min_videos", 10))
        except Exception:
            ctx, minimum = None, 10.0
        state.update(leftGb=balance["leftGb"], videosLeft=balance["videosLeft"])
        if balance["videosLeft"] < minimum and now - float(state.get("alerted") or 0) > 20 * 3600 and ctx is not None:
            state["alerted"] = now
            try:
                from .notify import telegram

                telegram(ctx, f"🌐 Al proxy de metadatos le quedan unos {balance['leftGb']:.1f} GB: unos "
                              f"{balance['videosLeft']} vídeos. Recarga en su panel y apúntalo en Ajustes "
                              "(«Proxy: GB comprados»), o la búsqueda volverá a salir por casa.")
            except Exception:
                pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    return state


def ways(root: Path) -> list[dict[str, Any]]:
    """Each way out to YouTube: free / in quarantine / not answering, and its requests this hour."""

    from .context import RunContext
    from .sourcing.common import HourlyBudget
    from .sourcing.youtube import BUDGET_SUFFIX, pacer_name, proxy_list, proxy_reachable, quarantined_until

    ctx = RunContext.create("_servidor", root=root)
    yt = ctx.section("sourcing").get("youtube", {})
    per_hour = float(yt.get("requests_per_hour", 1500) or 0)
    out = []
    now = time.time()
    for way in proxy_list(os.environ.get("YOUTUBE_PROXY"), yt.get("proxies"), yt.get("proxy")) or [""]:
        until = quarantined_until(ctx.cache_dir, way)
        state = (f"en cuarentena {int((until - now) / 60)} min" if until > now
                 else "libre" if proxy_reachable(way, timeout=2) else "no responde")
        out.append({"name": (way.split("@")[-1] if way else "servidor (directo)"), "state": state,
                    "hour": round(HourlyBudget(ctx.cache_dir / "videos" / (pacer_name(way) + BUDGET_SUFFIX), per_hour).used()),
                    "perHour": int(per_hour)})
    return out


def queue(root: Path) -> list[dict[str, Any]]:
    """Every video not finished, with what it is doing or waiting for."""

    import main

    from . import agenda, ytpause
    from .context import find_video
    from .locks import GROUPS
    from .web import _json, running

    holders = {}
    for path in (root / "work").glob(".turno-*"):
        try:
            holders[path.read_text().split(maxsplit=1)[1].strip()] = path.name.split("-")[1]
        except (OSError, IndexError):
            pass
    failed = _json(root / "out" / "_vigilar.json") or {}
    paused = ytpause.paused(root)
    out = []
    for video in agenda.videos(root):
        if video["status"] in ("hecho", "subido"):
            continue
        slug = video["slug"]
        current = running(_json(root / "work" / slug / "current.json"))
        folder = find_video(root, slug)
        if current:
            stage = str(current.get("stage") or "")
            group = GROUPS.get(stage)
            if group and slug not in holders and group in holders.values():      # another video holds that turn
                why, kind = f"esperando turno de {'red' if group == 'red' else 'CPU'} ({stage})", "turno"
            else:
                why, kind = f"haciendo: {stage} ({current.get('number')}/{current.get('of')})", "haciendo"
        elif (until := main.quota_wait(folder)):
            reason = (folder / main.QUOTA_WAIT).read_text("utf-8").split("\n", 1)[1:] or ["cuota de la API de YouTube"]
            why, kind = f"espera: {reason[0].strip()} hasta las {datetime.fromtimestamp(until):%H:%M}", "cuota"
        elif video["status"] == "en pausa":
            why, kind = "quitado de la cola (en pausa)", "pausa"
        elif video["status"] in ("falta guion", "falta voz"):
            why, kind = video["status"], "falta"
        elif paused and main.needs_youtube(root, slug):
            why, kind = "espera: YouTube bloquea esta conexión (se prueba cada hora)", "youtube"
        elif slug in failed:
            why, kind = "falló: se reintenta cuando cambien sus archivos o en unas horas", "error"
        else:
            why, kind = "en cola", "cola"
        out.append({"slug": slug, "channel": video["channel"], "why": why, "kind": kind})
    order = {"haciendo": 0, "turno": 1, "cuota": 2, "youtube": 3, "cola": 4, "error": 5, "falta": 6, "pausa": 7}
    return sorted(out, key=lambda v: order.get(v["kind"], 9))


def status(root: Path) -> dict[str, Any]:
    def safe(fn: Any, default: Any) -> Any:
        try:
            return fn(root)
        except Exception as error:  # one broken part never hides the rest
            return {"error": str(error)[:200]} if isinstance(default, dict) else default

    return {"machine": safe(machine, {}), "api": safe(api_quota, None), "proxy": safe(proxy_balance, None),
            "ways": safe(ways, []), "queue": safe(queue, []), "at": datetime.now().strftime("%H:%M:%S")}
