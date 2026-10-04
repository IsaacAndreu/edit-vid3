"""Telegram bot: ask the server how it is going, and an hourly report (python main.py --bot).

Only answers your chat (TELEGRAM_CHAT_ID); anybody else writing to the bot gets nothing. Commands:
  /estado            what it is doing now, the queue, today's spending, the disk
  /gasto             API spending: today, this hour, 7 days, per video and per service
  /videos            the latest videos and how they are
  /errores           videos that failed and why
  /video <nombre>    one video: stages, time, cost, error
  /youtube           how YouTube answered in the last 24 h
  /pausa · /seguir   stop starting new videos / start again
  /limite <dólares>  daily spending limit (0 = none)
  /reintentar <nombre>
Every hour (`bot.hourly`, except `bot.quiet_hours`) a report; and, whenever it happens, a warning when the watcher
stops giving signs of life, when the daily limit is reached or when the disk is almost full. A video that fails
already sends its own message (pipeline/notify.py).
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .config import PROJECT_ROOT
from .context import RunContext

STATE = "out/_bot.json"
STAGES = {"factcheck": "Verificar datos", "align": "Alinear la voz", "planner": "Planificar planos",
          "sourcing": "Buscar material", "analysis": "Analizar clips", "judge": "Elegir clips", "ingest": "Descargar en HD",
          "people": "Personas", "fallback": "Rellenar huecos", "coldopen": "Apertura", "timeline": "Montaje",
          "qa": "Revisión", "render": "Render", "shorts": "Shorts", "package": "Títulos"}
ICONS = {"hecho": "✅", "haciendo": "▶️", "en cola": "⏳", "error": "❌", "incompleto": "📝"}
COMMANDS = [("estado", "Qué está haciendo ahora"), ("gasto", "Gasto de API"), ("videos", "Últimos vídeos"),
            ("errores", "Vídeos con error"), ("youtube", "Cómo responde YouTube (24 h)"), ("pausa", "No empezar más vídeos"),
            ("seguir", "Volver a hacer vídeos"), ("ayuda", "Lista de comandos")]


def _money(usd: float) -> str:
    return f"{usd:.2f} $".replace(".", ",")


def _ago(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        when = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.astimezone()
    minutes = max(0, int((datetime.now(timezone.utc) - when).total_seconds() // 60))
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d} min"


# --- what the messages say ------------------------------------------------------------------------------------------

def cost_entries(root: Path) -> list[dict[str, Any]]:
    out = []
    for path in (root / "work").glob("*/costs.json"):
        try:
            entries = json.loads(path.read_text("utf-8")).get("entries", [])
        except (OSError, ValueError):
            continue
        out += [{**e, "slug": path.parent.name} for e in entries if isinstance(e, dict)]
    return out


def spending(root: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    entries = cost_entries(root)

    def since(delta: timedelta) -> list[dict[str, Any]]:
        limit = now - delta
        rows = []
        for e in entries:
            try:
                at = datetime.fromisoformat(str(e.get("at")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if at >= limit:
                rows.append(e)
        return rows

    today = [e for e in entries if str(e.get("at", "")).startswith(now.date().isoformat())]
    by = lambda rows, key: sorted(((k, sum(float(e.get("usd") or 0) for e in rows if (e.get(key) or "?") == k))   # noqa: E731
                                   for k in {e.get(key) or "?" for e in rows}), key=lambda kv: -kv[1])
    total = lambda rows: sum(float(e.get("usd") or 0) for e in rows)   # noqa: E731
    return {"today": total(today), "hour": total(since(timedelta(hours=1))), "week": total(since(timedelta(days=7))),
            "todayByVideo": by(today, "slug")[:6], "todayByService": by(today, "provider")[:5],
            "weekByVideo": by(since(timedelta(days=7)), "slug")[:6]}


def status_text(root: Path) -> str:
    from . import budget, web

    data = web.overview(root)
    s, b = data["service"], data["budget"]
    groups: dict[str, list[dict[str, Any]]] = {}
    for v in data["videos"]:
        if not v["archived"]:
            groups.setdefault(v["status"], []).append(v)
    lines = []
    state = ("⏸ En pausa" if s["paused"] else "🟢 Vigilando: hace los vídeos solo" if s["watching"]
             else "🟡 Cola en marcha" if s["queueRunning"] else "🔴 El vigilante no da señales")
    lines.append(state)
    for v in groups.get("haciendo", []):
        st = v.get("stage") or {}
        lines.append(f"▶️ {v['slug']} · {st.get('number', '?')}/{st.get('of', 15)} {STAGES.get(st.get('stage'), st.get('stage', ''))}"
                     f" · {_ago(st.get('started'))}" + (f" · {_money(v['costUsd'])}" if v.get("costUsd") else ""))
    if not groups.get("haciendo"):
        lines.append("Nada en marcha ahora.")
    lines.append(f"⏳ En cola: {len(groups.get('en cola', []))} · ❌ con error: {len(groups.get('error', []))} · "
                 f"✅ hechos: {len(groups.get('hecho', []))}")
    limit = budget.limit(root, RunContext.create("_bot", root=root).config)
    lines.append(f"💸 Hoy: {_money(b['today'])}" + (f" de {_money(limit)}" if limit else " (sin límite)"))
    lines.append(f"💾 Disco libre: {shutil.disk_usage(root).free / 1e9:.0f} GB")
    return "\n".join(lines)


def spending_text(root: Path) -> str:
    sp = spending(root)
    lines = [f"💸 Hoy: {_money(sp['today'])} · última hora: {_money(sp['hour'])} · 7 días: {_money(sp['week'])}"]
    if sp["todayByVideo"]:
        lines.append("\nHoy por vídeo:")
        lines += [f"  {slug}: {_money(usd)}" for slug, usd in sp["todayByVideo"]]
    if sp["todayByService"]:
        lines.append("\nHoy por servicio:")
        lines += [f"  {name}: {_money(usd)}" for name, usd in sp["todayByService"]]
    if sp["weekByVideo"]:
        lines.append("\n7 días por vídeo:")
        lines += [f"  {slug}: {_money(usd)}" for slug, usd in sp["weekByVideo"]]
    return "\n".join(lines)


def videos_text(root: Path, limit: int = 12) -> str:
    from . import web

    videos = [v for v in web.overview(root)["videos"] if not v["archived"]][:limit]
    if not videos:
        return "Aún no hay vídeos."
    return "\n".join(f"{ICONS.get(v['status'], '•')} {v['slug']} ({v['channel'] or '—'})"
                     + (f" · {(v.get('stage') or {}).get('number', '?')}/15" if v["status"] == "haciendo" else "")
                     + (f" · {_money(v['costUsd'])}" if v.get("costUsd") else "")
                     + (" · en YouTube" if v.get("published") else "") for v in videos)


def errors_text(root: Path) -> str:
    from . import web

    failed = [v for v in web.overview(root)["videos"] if v["status"] == "error" and not v["archived"]]
    if not failed:
        return "Ningún vídeo con error ✅"
    return "\n\n".join(f"❌ {v['slug']}\n{str(v.get('error') or 'falló')[:300]}\n→ /reintentar {v['slug']}" for v in failed[:8])


def video_text(root: Path, slug: str) -> str:
    from . import web

    try:
        v = web.video_detail(root, slug)
    except FileNotFoundError:
        return f"No encuentro el vídeo «{slug}»."
    lines = [f"{ICONS.get(v['status'], '•')} {v['slug']} · {v['status']} · {_money(v['costUsd'])} · {v['minutes']} min"]
    if v.get("stage"):
        st = v["stage"]
        lines.append(f"Ahora: {st.get('number')}/{st.get('of')} {STAGES.get(st.get('stage'), st.get('stage'))} · {_ago(st.get('started'))}")
    for stage in v["stages"]:
        seconds = float(stage.get("seconds") or 0)
        lines.append(f"  {STAGES.get(stage['name'], stage['name'])}: {seconds / 60:.1f} min")
    if v.get("error"):
        lines.append(f"Error: {str(v['error'])[:400]}")
    return "\n".join(lines)


def youtube_text(root: Path) -> str:
    from . import ytstats

    since = time.time() - 86400
    rows = [r for p in (root / "work").glob("*/youtube_downloads.jsonl") for r in ytstats.read(p, since)]
    lines = ytstats.lines(ytstats.summary(rows)) if rows else []
    return "YouTube, últimas 24 h:\n" + ("\n".join(lines) if lines else "sin peticiones")


def hourly_text(root: Path, since: float) -> str:
    """The hourly report: what it is doing, what finished or failed since `since`, spending, YouTube, disk."""

    from . import ytstats, web

    data = web.overview(root)
    done, failed = [], []
    for v in data["videos"]:
        final = root / "out" / v["slug"] / "video-final.mp4"
        if final.is_file() and final.stat().st_mtime >= since:
            done.append(v["slug"])
        diag = root / "work" / v["slug"] / "diag.json"
        if v["status"] == "error" and diag.is_file() and diag.stat().st_mtime >= since:
            failed.append(v["slug"])
    rows = [r for p in (root / "work").glob("*/youtube_downloads.jsonl") for r in ytstats.read(p, since)]
    yt = ytstats.summary(rows) if rows else None
    lines = [f"🕐 Parte de las {datetime.now():%H:%M}", status_text(root)]
    lines.append(f"✅ Terminados esta hora: {', '.join(done) or '—'}")
    lines.append(f"❌ Errores esta hora: {', '.join(failed) or '—'}")
    lines.append(f"💸 Gastado esta hora: {_money(spending(root)['hour'])}")
    if yt:
        lines.append(f"📥 YouTube: {yt['requests']} peticiones · {yt['failed']} fallidas"
                     + (f" ({', '.join(f'{k} {n}' for k, n in yt['errors'].items())})" if yt["errors"] else ""))
    return "\n".join(lines)


# --- the bot --------------------------------------------------------------------------------------------------------

class Bot:
    def __init__(self, root: Path = PROJECT_ROOT, session: Any = None) -> None:
        self.root = root
        ctx = RunContext.create("_bot", root=root)
        self.cfg = ctx.section("bot")
        self.token = ctx.env("TELEGRAM_BOT_TOKEN", required=False)
        self.chat = str(ctx.env("TELEGRAM_CHAT_ID", required=False) or "")
        if not self.token or not self.chat:
            raise SystemExit("Falta TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID: conéctalo en el estudio → Ajustes → Avisos al móvil")
        self.http = session or requests.Session()
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads((self.root / STATE).read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        path = self.root / STATE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.state, indent=1), encoding="utf-8")

    def send(self, text: str) -> None:
        try:
            self.http.post(f"{self.base}/sendMessage", data={"chat_id": self.chat, "text": text[:4000]}, timeout=30)
        except requests.RequestException as error:
            print(f"Telegram: {type(error).__name__}")

    def answer(self, text: str) -> str:
        """The reply to one message from your chat."""

        from . import web

        words = text.strip().split()
        if not words:
            return ""
        command, args = words[0].lstrip("/").split("@")[0].lower(), words[1:]
        if command in ("estado", "start", "status"):
            return status_text(self.root)
        if command in ("gasto", "coste", "dinero"):
            return spending_text(self.root)
        if command == "videos":
            return videos_text(self.root)
        if command == "errores":
            return errors_text(self.root)
        if command == "video":
            return video_text(self.root, args[0]) if args else "Dime cuál: /video <nombre>"
        if command == "youtube":
            return youtube_text(self.root)
        if command == "pausa":
            web.settings(self.root, {"paused": True})
            return "⏸ En pausa: no empieza vídeos nuevos (el que está en marcha termina). /seguir para volver."
        if command == "seguir":
            web.settings(self.root, {"paused": False})
            return "▶️ Seguimos: hará los vídeos pendientes."
        if command == "limite":
            try:
                usd = float(args[0].replace(",", "."))
            except (IndexError, ValueError):
                return "Escribe el límite en dólares: /limite 15 (0 = sin límite)"
            web.settings(self.root, {"daily_usd": usd})
            return f"Límite diario: {_money(usd)}" if usd else "Sin límite diario"
        if command == "reintentar":
            if not args:
                return "Dime cuál: /reintentar <nombre>"
            web.retry(self.root, args[0])
            return f"🔁 {args[0]} se vuelve a intentar en la próxima vuelta del vigilante (unos minutos)."
        return "Comandos:\n" + "\n".join(f"/{name} — {what}" for name, what in COMMANDS) + \
            "\n/video <nombre> — un vídeo\n/limite <dólares> — gasto máximo al día\n/reintentar <nombre>"

    def handle(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        if str((message.get("chat") or {}).get("id")) != self.chat:   # only your chat
            return
        try:
            reply = self.answer(str(message.get("text") or ""))
        except Exception as error:                       # a broken command must not stop the bot
            reply = f"No he podido: {type(error).__name__}: {str(error)[:200]}"
        if reply:
            self.send(reply)

    def chores(self, now: float | None = None) -> None:
        """Hourly report and the warnings, called every minute or so."""

        from . import budget

        now = now or time.time()
        hour = datetime.fromtimestamp(now).hour
        last = float(self.state.get("hourly") or 0)
        if self.cfg.get("hourly", True) and now - last >= 3600 - 30:
            self.state["hourly"] = now
            if hour not in [int(h) for h in self.cfg.get("quiet_hours") or []]:
                self.send(hourly_text(self.root, last or now - 3600))
        warnings = self.state.setdefault("warned", {})
        beat = self.root / "out" / "_vigilar.latido"
        paused = (self.root / "out" / "_pausa").is_file()
        stale = beat.is_file() and now - beat.stat().st_mtime > float(self.cfg.get("watcher_alert_minutes", 20)) * 60
        if stale and not paused and not warnings.get("watcher"):
            self.send("🔴 El vigilante no da señales desde hace "
                      f"{int((now - beat.stat().st_mtime) // 60)} min: no se están haciendo vídeos.\n"
                      "En el servidor: sudo systemctl status edit-vid3   (registro: journalctl -u edit-vid3 -n 50)")
        warnings["watcher"] = bool(stale)
        config = RunContext.create("_bot", root=self.root).config
        cap = budget.limit(self.root, config)
        over = bool(cap) and budget.spent_today(self.root) >= cap
        if over and warnings.get("budget") != datetime.now().date().isoformat():
            self.send(f"💸 Límite diario alcanzado ({_money(budget.spent_today(self.root))} de {_money(cap)}): "
                      "no empieza más vídeos hasta mañana. /limite <dólares> para cambiarlo.")
            warnings["budget"] = datetime.now().date().isoformat()
        free = shutil.disk_usage(self.root).free / 1e9
        low = free < float((config.get("cleanup") or {}).get("min_free_gb", 30))
        if low and not warnings.get("disk"):
            self.send(f"💾 Disco casi lleno: quedan {free:.0f} GB. Marca como subidos los vídeos que ya estén en YouTube "
                      "(estudio → el vídeo → «Ya está subido») para liberar espacio.")
        warnings["disk"] = low
        self._save()

    def run(self) -> None:
        try:
            self.http.post(f"{self.base}/setMyCommands", timeout=30,
                           json={"commands": [{"command": c, "description": d} for c, d in COMMANDS]})
        except requests.RequestException:
            pass
        print("Bot de Telegram en marcha (Ctrl+C para parar)")
        self.state.setdefault("hourly", time.time())        # the first report an hour from now
        if "offset" not in self.state:                      # first start: old messages are not commands for now
            try:
                old = self.http.get(f"{self.base}/getUpdates", params={"offset": -1}, timeout=30).json().get("result", [])
                self.state["offset"] = int(old[-1]["update_id"]) + 1 if old else 0
            except (requests.RequestException, ValueError, KeyError):
                self.state["offset"] = 0
        self.send("🤖 Bot en marcha. /estado, /gasto, /videos, /errores… (parte cada hora)")
        while True:
            try:
                data = self.http.get(f"{self.base}/getUpdates", timeout=60,
                                     params={"timeout": 50, "offset": int(self.state.get("offset") or 0)}).json()
                for update in data.get("result", []):
                    self.state["offset"] = int(update["update_id"]) + 1
                    self.handle(update)
            except (requests.RequestException, ValueError):
                time.sleep(15)
            try:
                self.chores()
            except Exception as error:                   # never stops the bot
                print(f"Bot: {type(error).__name__}: {str(error)[:160]}")
