"""Web studio: everything without commands (python main.py --web).

- New video: channel, name, the script (pasted or a .txt) and the voice (.mp3) → materiales/<canal>/<nombre>/.
- Home: is the server making videos (watcher alive, paused, today's spending), what it is doing right now (video,
  stage N/15, minutes), what is waiting, finished and failed.
- A video: its stages with times, RAM and CPU, the log as it runs, the final video (plays in the browser and
  downloads), titles and thumbnails, the diagnosis and the fact check; retry a failed one.
- Statistics: YouTube (requests, 403, bot checks, speed) and spending per day.
- Errores: mark each clip of a video right / wrong (+ why) / doubtful; wrong clips are never used again and
  «Rehacer con correcciones» replaces them; «Para ir mejorando» says which part of the program makes the mistakes.
- Competencia: the daily radar (best videos of your niches now, new niches measured on YouTube).
- Mi canal: analysis of your channel (numbers, evolution, winners, best days and hours, titles, topics).
- Settings: pause / resume, daily spending limit, your channel per profile.

On the server it listens on 127.0.0.1 and Caddy puts HTTPS in front (scripts/vps/install-web.sh); every request that
does not come straight from this machine needs WEB_PASSWORD (.env). Standard library only: nothing to install.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .context import RunContext, find_video, load_config, video_folders

STATIC = Path(__file__).with_name("web_static")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$")
MAX_UPLOAD = 400 * 1024 * 1024                # a 15-min voice in mp3 is ~15-30 MB; leave room for wav


# --- what the pages show ----------------------------------------------------------------------------------------

def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def channels(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "canales").glob("*.yaml"))


def set_channel(root: Path, slug: str, channel: str) -> dict[str, Any]:
    """«Cambiar de canal»: canal: in materiales/<vídeo>/config.yaml (the rest of that file stays). A finished video
    is not made again: it only changes where it is counted (statistics, spend, «Para subir»)."""

    import yaml

    if channel not in channels(root):
        raise ValueError(f"No existe el canal {channel!r} (canales/{channel}.yaml)")
    folder = find_video(root, slug)
    if not folder.is_dir():
        raise FileNotFoundError(slug)
    path = folder / "config.yaml"
    current = (yaml.safe_load(path.read_text("utf-8")) if path.is_file() else None) or {}
    current["canal"] = channel
    path.write_text(yaml.safe_dump(current, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True, "video": slug, "channel": channel}


def formats(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "formatos").glob("*.yaml"))


def _channel_of(root: Path, folder: Path) -> str:
    for path in (folder / "config.yaml", folder.parent / "config.yaml"):
        cfg = _json_yaml(path)
        if cfg.get("canal"):
            return str(cfg["canal"])
    return str(load_config(root / "config.yaml").get("canal") or "")


def _json_yaml(path: Path) -> dict[str, Any]:
    try:
        return load_config(path) if path.is_file() else {}
    except Exception:
        return {}


def running(current: dict[str, Any] | None) -> dict[str, Any] | None:
    """current.json only while its process lives (a killed run leaves the file behind)."""

    if not current or current.get("ended"):          # a stage that stopped (error, waiting for quota)
        return None
    pid = current.get("pid")
    if not pid:
        return current
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return None
    except (PermissionError, OSError, ValueError):
        return current
    return current


def video_summary(root: Path, folder: Path, watch_state: dict[str, Any]) -> dict[str, Any]:
    slug = folder.name
    out, work = root / "out" / slug, root / "work" / slug
    current = running(_json(work / "current.json"))
    from .housekeeping import REMOVED, is_done, published

    done = is_done(root, slug)
    uploaded = published(root, slug)
    removed = _json(out / REMOVED)
    stages = sorted((work / ".stages").glob("*.json")) if (work / ".stages").is_dir() else []
    costs = _json(work / "costs.json") or {}
    failed = watch_state.get(slug)
    diag = _json(work / "diag.json") or {}
    from . import tts

    ready = (folder / "guion.txt").is_file() and ((folder / "voz.mp3").is_file() or tts.has_auto_voice(root, folder))
    # with the watcher running a failed video is not «error»: it goes back to the queue — now if the watcher never
    # tried it (an old failure), else after watch.retry_hours (or as soon as you change its files)
    retry_at = None
    queued_again = False
    held = (folder / HOLD).is_file()
    quota_wait = None                          # main.QUOTA_WAIT: the pilot waits for the API quota reset
    try:
        first, _, why = (folder / ".espera-cuota").read_text("utf-8").strip().partition("\n")
        until = float(first)
        if until > time.time():
            local = datetime.fromtimestamp(until, timezone.utc).astimezone()
            quota_wait = f"{why or 'cuota de la API de YouTube'} · hasta las {local:%H:%M}"
    except (OSError, ValueError):
        pass
    redo = (folder / REDO).is_file() and not held      # «Rehacer»: back in the queue although it has a final video
    waiting_quota = quota_wait is not None and not current   # the API's searches ran out: it waits, it did not fail
    if (ready and not done and not current and not held and not waiting_quota and (diag.get("error") or failed)
            and watcher_alive(root)):                          # done: an old error is history
        queued_again = True
        if failed and failed.get("at"):
            retry_at = float(failed["at"]) + _retry_hours(root) * 3600
            if retry_at <= time.time():
                retry_at = None
    voice = None                               # GenAIPro in the background (tts.prepare_all)
    if not (folder / "voz.mp3").is_file() and (folder / "guion.txt").is_file():
        if tts.generating(folder):
            voice = "generando"
        elif (folder / tts.FAILED).is_file():
            voice = "error: " + str((_json(folder / tts.FAILED) or {}).get("error") or "falló")[:200]
    status = ("haciendo" if current else "en cola" if redo else "hecho" if done else "en pausa" if held
              else "en cola" if queued_again or (waiting_quota and ready)
              else "error" if failed or diag.get("error") else "en cola" if ready else "incompleto")
    return {
        "slug": slug, "channel": _channel_of(root, folder), "status": status, "quotaWait": quota_wait,
        "archived": any(part.startswith("_") for part in folder.relative_to(root / "materiales").parts),
        "stage": current, "stagesDone": len(stages), "costUsd": round(float(costs.get("totalUsd") or 0), 2),
        "error": None if done or current or queued_again else diag.get("error") or ((failed or {}).get("status") and "falló"),
        "lastError": (diag.get("error") or "falló") if queued_again else None,
        "voice": voice,
        "retryAt": time.strftime("%H:%M", time.localtime(retry_at)) if retry_at else None,
        "updated": max([p.stat().st_mtime for p in [folder, *(out.glob("*") if out.is_dir() else [])]]),
        "hasVideo": (out / "video-final.mp4").is_file(), "published": uploaded or None, "removed": removed,
        "title": _first_line(folder / "titulo.txt"),
        "minutes": round(sum(float((_json(p) or {}).get("seconds") or 0) for p in stages) / 60),
    }


_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()


def cached(key: str, seconds: float, make: Any) -> Any:
    """`make()` at most once every `seconds` (the studio polls every 10-30 s from every open tab)."""

    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < seconds:
            return hit[1]
    value = make()
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
    return value


def _first_line(path: Path) -> str:
    try:
        return path.read_text("utf-8", errors="replace").strip().splitlines()[0][:200] if path.is_file() else ""
    except (OSError, IndexError):
        return ""


SEARCH_STOP = set("""de la el en y a los las del que se por un una con no es su al lo como más pero sus le ya o este
sí porque esta entre cuando muy sin sobre también me hasta hay donde quien desde todo nos durante todos uno les ni
contra otros ese eso ante ellos e esto mí antes algunos qué unos yo otro otras otra él tanto esa estos mucho quienes
nada muchos cual poco ella estar estas algunas algo nosotros mi mis tú te ti tu tus ellas nosotras vosotros fue era
han ha sido son está están ser hace hizo años año vez veces después aquí allí así solo cada este esta""".split())


def _words(text: str) -> list[str]:
    import unicodedata

    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return [w for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 2 and w not in SEARCH_STOP]


def search_videos(root: Path, query: str, limit: int = 20) -> dict[str, Any]:
    """«¿Ya lo hice?»: every video (also archived and uploaded) whose title, folder name or script matches. A few
    words look for those words; a pasted script (40+ words) is compared whole and gives a «parecido» percentage."""

    wanted = _words(query)
    if not wanted:
        return {"query": query, "results": []}
    whole = len(wanted) >= 40
    wanted_set = set(wanted)
    watch_state = _json(root / "out" / "_vigilar.json") or {}
    results = []
    for folder in video_folders(root):
        script_path = folder / "guion.txt"
        script = script_path.read_text("utf-8", errors="replace") if script_path.is_file() else ""
        title = _first_line(folder / "titulo.txt") or _first_line(root / "out" / folder.name / "youtube.txt")
        head = set(_words(f"{folder.name.replace('-', ' ')} {title}"))
        body = _words(script)
        if not body and not head:
            continue
        body_set = set(body)
        if whole:
            # distinctive words of both scripts in common (names, places, figures repeat across a topic)
            score = len(wanted_set & body_set) / max(1, min(len(wanted_set), len(body_set)))
            if score < 0.25:
                continue
        else:
            hits = [w for w in wanted_set if w in head or w in body_set]
            if len(hits) < max(1, round(len(wanted_set) * 0.6)):
                continue
            score = (len(hits) + sum(w in head for w in wanted_set)) / (2 * len(wanted_set))
        # the snippet: the first script line with most of the words
        lines = [ln.strip() for ln in script.splitlines() if ln.strip()]
        best = max(lines, key=lambda ln: len(wanted_set & set(_words(ln))), default="")
        summary = video_summary(root, folder, watch_state)
        results.append({"slug": folder.name, "title": title, "channel": summary["channel"], "status": summary["status"],
                        "archived": summary["archived"], "published": summary["published"],
                        "score": round(score, 3), "snippet": best[:260]})
    results.sort(key=lambda r: -r["score"])
    return {"query": query, "whole": whole, "results": results[:limit], "ideas": [] if whole else search_ideas(root, wanted_set)}


def search_ideas(root: Path, wanted: set[str], limit: int = 10) -> list[dict[str, Any]]:
    """The ideas not made yet that match too: the board's, the saved ones (radar, niches) and today's news drafts."""

    from . import agenda, niche_ideas

    try:
        ideas = [(i, "tablero") for i in agenda.settings(root).get("ideas") or []] + \
                [(i, "idea guardada") for i in niche_ideas.saved(root)]
    except Exception:
        ideas = []
    out = []
    for idea, where in ideas:
        text = " ".join(str(idea.get(k) or "") for k in ("title", "note", "angle", "protagonist", "hook", "outline"))
        found = set(_words(text))
        hits = [w for w in wanted if w in found]
        if len(hits) < max(1, round(len(wanted) * 0.6)):
            continue
        out.append({"title": str(idea.get("title") or ""), "channel": str(idea.get("channel") or ""), "where": where,
                    "note": " ".join(str(idea.get("note") or idea.get("angle") or "").split())[:200],
                    "score": round(len(hits) / max(1, len(wanted)), 3)})
    out.sort(key=lambda i: -i["score"])
    return out[:limit]


def _youtube_blocked(root: Path) -> str | None:
    """The queue paused itself because YouTube blocks the connection (pipeline/ytpause.py): since when."""

    from . import ytpause

    state = ytpause.paused(root)
    return time.strftime("%H:%M", time.localtime(float(state.get("at") or 0))) if state else None


def _lock_alive(lock: Path) -> bool:
    """The queue lock exists AND its process is alive (a restart can leave it behind)."""

    from .locks import _alive

    try:
        return _alive(int(lock.read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return False


def overview(root: Path) -> dict[str, Any]:
    from . import budget, ytstats

    watch_state = _json(root / "out" / "_vigilar.json") or {}
    beat = root / "out" / "_vigilar.latido"
    alive = beat.is_file() and time.time() - beat.stat().st_mtime < 15 * 60
    from .context import VIDEO_FILES

    # a folder with nothing but a config.yaml (an empty channel folder like materiales/atletismo/) is not a video
    folders = [f for f in video_folders(root) if any((f / n).is_file() for n in VIDEO_FILES) or (root / "out" / f.name).is_dir()]
    videos = [video_summary(root, f, watch_state) for f in folders]
    videos.sort(key=lambda v: -v["updated"])
    config = RunContext.create("_web", root=root).config
    since = time.time() - 7 * 86400
    # every download of the week, line by line: minutes of reading on a busy server, so once every 5 minutes
    def youtube_stats() -> dict[str, Any] | None:
        rows = [r for p in (root / "work").glob("*/youtube_downloads.jsonl") for r in ytstats.read(p, since)]
        if not rows:
            return None
        day = time.time() - 86400                 # per proxy: the last 24 h (which PCs are on changes by day)
        return {**ytstats.summary(rows), "byProxy": ytstats.by_proxy([r for r in rows if float(r.get("ts") or 0) >= day])}

    youtube = cached(f"yt:{root}", 300, youtube_stats)
    queue_running = _lock_alive(root / "work" / ".cola.lock")
    return {
        "service": {"watching": alive, "paused": (root / "out" / "_pausa").is_file(), "queueRunning": queue_running,
                    "youtubeBlocked": _youtube_blocked(root),
                    "lastBeat": beat.read_text().strip() if beat.is_file() else None, "code": code_version(root)},
        "budget": {"today": budget.spent_today(root), "limit": budget.limit(root, config)},
        "videos": videos, "channels": channels(root), "formats": formats(root),
        "youtube": youtube,
    }


def code_version(root: Path) -> dict[str, str] | None:
    """The code the server has: last change and when (the studio shows it, so nobody needs SSH to check)."""

    import subprocess

    try:
        out = subprocess.run(["git", "log", "-1", "--format=%h%x09%cI%x09%s"], cwd=root, capture_output=True,
                             text=True, timeout=10).stdout.strip().split("\t")
    except (OSError, subprocess.SubprocessError):
        return None
    return {"id": out[0], "at": out[1], "what": out[2][:120]} if len(out) == 3 else None


def update_code(root: Path) -> dict[str, Any]:
    """«Actualizar ahora»: git pull without waiting the 2 minutes. With new code the studio restarts with it (the
    page reloads itself) and the queue is woken to take it before its next video."""

    before = (code_version(root) or {}).get("id")
    pulled = subprocess.run(["git", "pull", "--ff-only", "-q"], cwd=root, capture_output=True, text=True, timeout=120)
    kept: list[str] = []
    if pulled.returncode != 0 and "untracked working tree files would be overwritten" in pulled.stderr:
        # a file made here (a channel created in the studio) that the new code also brings: it is kept next to
        # it as <file>.antes-de-actualizar and the pull goes on (atletismo.yaml blocked the update)
        listing = pulled.stderr.split("overwritten by merge:", 1)[-1].split("Please move", 1)[0]
        for rel in (line.strip() for line in listing.splitlines() if line.strip()):
            target = (root / rel).resolve()
            if root.resolve() in target.parents and target.is_file():
                target.rename(target.with_name(target.name + ".antes-de-actualizar"))
                kept.append(rel)
        if kept:
            pulled = subprocess.run(["git", "pull", "--ff-only", "-q"], cwd=root, capture_output=True, text=True, timeout=120)
    if pulled.returncode != 0:
        raise ValueError(f"git pull no se pudo: {(pulled.stderr or pulled.stdout).strip()[-300:]}")
    now = code_version(root) or {}
    if now.get("id") == before:
        return {"ok": True, "changed": False, "message": f"Ya estaba al día: {now.get('what', '')}"}
    if watcher_alive(root):
        (root / "out" / "_despertar").write_text(time.strftime("%H:%M:%S"), encoding="utf-8")
    threading.Timer(1.0, lambda: os.execv(sys.executable, [sys.executable, *sys.argv])).start()
    return {"ok": True, "changed": True, "message": f"Código nuevo: {now.get('what', '')}. El estudio se reinicia "
            "(unos segundos) y la cola lo coge antes de su próximo vídeo."
            + (f" Tus versiones de {', '.join(kept)} se guardaron como «….antes-de-actualizar»." if kept else "")}


def youtube_retry_now(root: Path) -> dict[str, Any]:
    """«Reintentar YouTube ahora»: you checked YouTube works again (private window at home): the pause for the block,
    the quarantine of every connection, the 72 h «only by the API» window and the videos waiting for the API quota
    are cleared, and the watcher looks at the queue at once. If YouTube still says «are you a bot», the first
    request puts it all back by itself."""

    from .context import RunContext, video_folders

    cache = RunContext.create("_youtube", root=root).cache_dir / "videos"
    removed = []
    for path in [root / "out" / "_pausa_youtube", root / "out" / "_vigilar.json",
                 *sorted(cache.glob(".ritmo*.cuarentena")), cache / ".ultimo-bloqueo",
                 *[d / ".espera-cuota" for d in video_folders(root)]]:
        if path.is_file():
            path.unlink()
            removed.append(path.name)
    (root / "out").mkdir(parents=True, exist_ok=True)
    (root / "out" / "_despertar").write_text("youtube", encoding="utf-8")
    return {"ok": True, "removed": removed,
            "message": "Listo: YouTube se vuelve a intentar ya. Si sale «no eres un bot», la cola se para sola otra vez."}


def restart_queue(root: Path) -> dict[str, Any]:
    """«Reiniciar la cola» from the phone: the watcher service starts again (a video being made resumes from its
    last finished stage). Only where the queue runs as the systemd service edit-vid3."""

    import shutil

    if not shutil.which("systemctl"):
        raise ValueError("Aquí la cola no es un servicio (systemctl): reiníciala a mano")
    done = subprocess.run(["systemctl", "restart", "edit-vid3"], capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise ValueError(f"No se pudo reiniciar: {(done.stderr or done.stdout).strip()[-200:]}")
    return {"ok": True, "message": "Cola reiniciada. Si estaba haciendo un vídeo, sigue desde la última etapa terminada."}


def for_claude(root: Path, slug: str) -> str:
    """Everything Claude needs to look at a video, in one text to paste in the chat (from the phone)."""

    detail = video_detail(root, slug)
    out = root / "out" / slug
    parts = [f"VÍDEO {slug} · {detail.get('channel')} · estado: {detail.get('status')} · {detail.get('costUsd')} $ · "
             f"{detail.get('minutes')} min"]
    if detail.get("error") or detail.get("lastError"):
        parts.append(f"ERROR: {detail.get('error') or detail.get('lastError')}")
    stages = " · ".join(f"{s['name']} {round((s.get('seconds') or 0) / 60, 1)} min" for s in detail.get("stages", []))
    if stages:
        parts.append(f"ETAPAS: {stages}")
    diagnosis = (out / "diagnostico.md").read_text("utf-8", errors="replace") if (out / "diagnostico.md").is_file() else ""
    if diagnosis:
        parts.append("DIAGNÓSTICO:\n" + diagnosis[:5000])
    log = detail.get("log") or ""
    if log:
        parts.append("ÚLTIMAS LÍNEAS DEL REGISTRO:\n" + "\n".join(log.splitlines()[-60:]))
    return "\n\n".join(parts)[:14000]


def audit_text(root: Path, slug: str) -> str | None:
    """scripts/auditoria.py's report (minute · narration · source · who chose it), to copy from the studio."""

    if not (root / "work" / slug / "timeline.json").is_file():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("auditoria", PROJECT_ROOT / "scripts" / "auditoria.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)                    # type: ignore[union-attr]
    module.ROOT = root
    return module.report(slug)


def video_detail(root: Path, slug: str) -> dict[str, Any]:
    folder = find_video(root, slug)
    out, work = root / "out" / slug, root / "work" / slug
    if not folder.is_dir() and not out.is_dir():
        raise FileNotFoundError(slug)
    summary = video_summary(root, folder, _json(root / "out" / "_vigilar.json") or {})
    stages = []
    for marker in sorted((work / ".stages").glob("*.json"), key=lambda p: p.stat().st_mtime) if (work / ".stages").is_dir() else []:
        info = _json(marker) or {}
        stages.append({"name": marker.stem, "seconds": info.get("seconds"), "ram": info.get("ramPeakGb"),
                       "cpu": info.get("cpuPeak"), "at": info.get("completedAt")})
    log = out / "log.txt"
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) if out.is_dir() else []
    read = lambda name: (out / name).read_text("utf-8", errors="replace") if (out / name).is_file() else None  # noqa: E731
    return {
        **summary,
        "stages": stages,
        "log": log.read_text("utf-8", errors="replace")[-12000:] if log.is_file() else "",
        "diagnosis": read("diagnostico.md"), "factcheck": read("verificacion.md"), "youtubeTxt": read("youtube.txt"),
        "graphics": read("graficos.md"), "hook": read("gancho.md"), "audit": audit_text(root, slug),
        "thumbnails": [f for f in files if f.startswith("miniaturas/") or re.match(r"miniatura", f)],
        "shorts": [f for f in files if f.startswith("shorts/") and f.endswith(".mp4")],
        "files": files,
        "preview": ensure_preview(root, slug) if summary.get("hasVideo") else False,
        "script": (folder / "guion.txt").read_text("utf-8", errors="replace")[:20000] if (folder / "guion.txt").is_file() else "",
        "format": _format_of(root, folder),
    }


PREVIEW = "preview.mp4"           # in out/<vídeo>/: a light copy to watch in the studio (the phone, a slow line)
_PREVIEWS: set[str] = set()
_PREVIEW_LOCK = threading.Lock()


def preview_ready(out: Path) -> bool:
    final, preview = out / "video-final.mp4", out / PREVIEW
    return preview.is_file() and final.is_file() and preview.stat().st_mtime >= final.stat().st_mtime


def ensure_preview(root: Path, slug: str) -> bool:
    """The final video is 1080p at high quality (1-1.5 GB for 10 min): in the browser, above all on the phone, it
    stalls or fails. A 720p copy (~2 Mbit/s, ~150 MB, starts at once) is made in the background the first time the
    video is opened, at the lowest priority; the page plays it once it exists. True when it is ready."""

    out = root / "out" / slug
    final = out / "video-final.mp4"
    if not final.is_file() or preview_ready(out):
        return preview_ready(out)
    with _PREVIEW_LOCK:
        if slug in _PREVIEWS:
            return False
        _PREVIEWS.add(slug)

    def make() -> None:
        tmp = out / ".preview.tmp.mp4"
        try:
            low = ["nice", "-n", "19"] if shutil.which("nice") else []      # Windows (the home PC): no nice
            subprocess.run([*low, "ffmpeg", "-y", "-v", "error", "-i", str(final), "-vf", "scale=-2:720",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-maxrate", "2500k", "-bufsize", "5000k",
                            "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", "-threads", "2", str(tmp)],
                           check=True, timeout=3 * 3600, capture_output=True)
            tmp.replace(out / PREVIEW)
        except Exception:
            tmp.unlink(missing_ok=True)
        finally:
            with _PREVIEW_LOCK:
                _PREVIEWS.discard(slug)

    threading.Thread(target=make, name=f"preview-{slug}", daemon=True).start()
    return False


def _format_of(root: Path, folder: Path) -> dict[str, Any] | None:
    """The video's format: its own config.yaml, else the channel's; with the reason when it was chosen from the script."""

    from .formats import AUTO

    auto = _json(folder / AUTO) or {}
    own = _json_yaml(folder / "config.yaml").get("format")
    name = own or auto.get("channel") or _json_yaml(folder.parent / "config.yaml").get("format") or ""
    if not name:
        try:
            from .context import RunContext

            name = str(RunContext.create(folder.name, root=root).config.get("format") or "")
        except Exception:
            name = ""
    return {"name": name, "auto": bool(auto) and auto.get("format") == name, "why": auto.get("why") or ""} if name else None


CHANNEL = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")


def _list(value: Any) -> list[str]:
    items = value if isinstance(value, list) else re.split(r"[,\n]", str(value or ""))
    return [str(v).strip() for v in items if str(v).strip()]


def create_channel(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    """canales/<nombre>.yaml from the studio: what it is about, competitors, searches, the default format, and the
    look (colours, music, graphics) copied from an existing channel if chosen. Never overwrites a channel."""

    import yaml

    from .context import deep_merge

    name = str(body.get("name") or "").strip().lower()
    if not CHANNEL.match(name):
        raise ValueError("El nombre del canal: minúsculas, números y guiones (2-31), p. ej. «coches» o «historia-f1»")
    path = root / "canales" / f"{name}.yaml"
    if path.exists():
        raise ValueError(f"Ya existe el canal {name}")
    about = str(body.get("about") or "").strip()
    if len(about) < 15:
        raise ValueError("Describe de qué va el canal (una frase)")
    base = str(body.get("base") or "").strip()
    profile: dict[str, Any] = {}
    if base:
        if base not in channels(root):
            raise ValueError(f"No existe el canal {base}")
        profile = load_config(root / "canales" / f"{base}.yaml")
    ideas = {"about": f"un canal de YouTube en español de {about}" if not about.lower().startswith("un canal") else about,
             "my_channel": str(body.get("my_channel") or "").strip(),
             "competitors": _list(body.get("competitors")), "niches": _list(body.get("niches")) or [name]}
    if str(body.get("pattern") or "").strip():
        ideas["pattern"] = str(body["pattern"]).strip()
    profile = deep_merge(profile, {"ideas": ideas, "lab": {"queries": _list(body.get("queries")) or [about[:60]]}})
    profile.pop("series", None)                       # the base channel's series are its own
    fmt = str(body.get("format") or "").strip()
    if fmt:
        if fmt not in formats(root):
            raise ValueError(f"No existe el formato {fmt}")
        profile["format"] = fmt
    header = (f"# Canal «{name}», creado desde el estudio ({time.strftime('%d-%m-%Y')})"
              + (f" con el aspecto de «{base}»" if base else "") + ".\n"
              "# Se mezcla encima de config.yaml: aquí solo lo propio de este canal (format, brand, music, ideas…).\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(profile, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    group = root / "materiales" / name
    group.mkdir(parents=True, exist_ok=True)
    if not (group / "config.yaml").exists():
        (group / "config.yaml").write_text(f"canal: {name}\n", encoding="utf-8")
    return {"channel": name}


def create_video(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    name = str(body.get("name") or "").strip()
    channel = str(body.get("channel") or "").strip()
    if not NAME.match(name):
        raise ValueError("El nombre solo puede llevar letras, números, puntos, guiones y _ (sin espacios)")
    if channel and channel not in channels(root):
        raise ValueError(f"No existe el canal {channel}")
    if any(f.name == name for f in video_folders(root)):
        raise ValueError(f"Ya hay un vídeo llamado {name}")
    from .tts import clean_script

    script = clean_script(str(body.get("script") or "")).strip()     # «[CAPÍTULO 1 — …]» → «## …», notes out
    if len(script) < 200:
        raise ValueError("El guion es demasiado corto")
    folder = root / "materiales" / channel / name if channel else root / "materiales" / name
    if channel:
        group = root / "materiales" / channel
        group.mkdir(parents=True, exist_ok=True)
        if not (group / "config.yaml").is_file():
            (group / "config.yaml").write_text(f"canal: {channel}\n", encoding="utf-8")
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "guion.txt").write_text(script + "\n", encoding="utf-8")
    if str(body.get("title") or "").strip():
        (folder / "titulo.txt").write_text(str(body["title"]).strip() + "\n", encoding="utf-8")
    if isinstance(body.get("idea"), dict):                 # made from a radar idea: the brief next to the script
        from .niche_ideas import brief

        (folder / "idea.md").write_text(brief(body["idea"]), encoding="utf-8")
    extra = {k: str(body[k]).strip() for k in ("serie", "format") if str(body.get(k) or "").strip()}
    if extra:
        (folder / "config.yaml").write_text("".join(f"{k}: {v}\n" for k, v in extra.items()), encoding="utf-8")
    return {"slug": name, "folder": str(folder.relative_to(root))}


def save_voice(root: Path, slug: str, data: bytes) -> dict[str, Any]:
    folder = find_video(root, slug)
    if not folder.is_dir():
        raise FileNotFoundError(slug)
    if len(data) < 10_000:
        raise ValueError("El audio está vacío o incompleto")
    tmp = folder / "voz.subiendo"
    tmp.write_bytes(data)
    if data[:3] != b"ID3" and data[:2] not in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        # not an mp3 (wav, m4a…): convert, the pipeline reads voz.mp3
        done = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-c:a", "libmp3lame", "-q:a", "2",
                               str(folder / "voz.mp3")], capture_output=True, text=True)
        tmp.unlink(missing_ok=True)
        if done.returncode != 0:
            raise ValueError(f"No entiendo ese audio: {done.stderr.strip()[-200:]}")
    else:
        tmp.replace(folder / "voz.mp3")
    return {"ok": True, "bytes": (folder / "voz.mp3").stat().st_size}


_RETRY: dict[str, tuple[float, float]] = {}


def _retry_hours(root: Path) -> float:
    """watch.retry_hours (6), read at most once a minute."""

    cached = _RETRY.get(str(root))
    if cached and time.time() - cached[0] < 60:
        return cached[1]
    try:
        hours = float(RunContext.create("_web", root=root).section("watch").get("retry_hours", 6))
    except Exception:
        hours = 6.0
    _RETRY[str(root)] = (time.time(), hours)
    return hours


def watcher_alive(root: Path) -> bool:
    beat = root / "out" / "_vigilar.latido"
    return beat.is_file() and time.time() - beat.stat().st_mtime < 15 * 60 and not (root / "out" / "_pausa").is_file()


def retry(root: Path, slug: str) -> dict[str, Any]:
    """«Reintentar» / «Hacer ahora»: with the watcher running, it takes the video on its next round; without it,
    the studio starts the video itself in the background (it survives closing the SSH window)."""

    find_video(root, slug)
    if running(_json(root / "work" / slug / "current.json")):
        raise ValueError("Este vídeo ya se está haciendo")
    path = root / "out" / "_vigilar.json"
    state = _json(path) or {}
    state.pop(slug, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    if watcher_alive(root):
        return {"ok": True, "message": "El vigilante lo vuelve a intentar en su próxima vuelta (unos minutos)."}
    background(root, f"video-{slug}", ["--slug", slug])
    return {"ok": True, "started": True, "message": "En marcha desde el estudio: sigue avanzando aunque cierres todo."}


def retry_all(root: Path) -> dict[str, Any]:
    """«Reintentar todos ahora»: every failed video back in the queue at once, without waiting for its retry time."""

    path = root / "out" / "_vigilar.json"
    state = _json(path) or {}
    count = len(state)
    from . import tts
    from .context import video_folders

    for folder in video_folders(root):                 # a voice GenAIPro failed: try it now too, not in 30 min
        (folder / tts.FAILED).unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    if watcher_alive(root):
        (root / "out" / "_despertar").write_text(time.strftime("%H:%M:%S"), encoding="utf-8")
        return {"ok": True, "count": count, "message": f"{count} vídeo(s) de vuelta a la cola: el vigilante empieza ya."}
    if _lock_alive(root / "work" / ".cola.lock"):
        return {"ok": True, "count": count, "message": "Hay una cola en marcha: los hará al acabar la actual."}
    start_queue(root)
    return {"ok": True, "count": count, "started": True, "message": "Cola en marcha desde el estudio."}


def download_name(root: Path, path: Path) -> str:
    """«pati12 - El caso Valieva.mp4» instead of «video-final.mp4»: many downloaded at once, each says which it is
    (the folder name first, then its title; shorts and other files keep their name after the folder's)."""

    parts = path.parts
    top = next((i for i in range(len(parts) - 2, -1, -1) if parts[i] in ("out", "materiales")), None)
    if top is None or top + 1 >= len(parts) - 1:
        return path.name
    slug = parts[top + 1]                      # out/<slug>/…, materiales/<slug>/… (also materiales/<canal>/<slug>)
    if parts[top] == "materiales" and top + 2 < len(parts) - 1:
        slug = parts[top + 2]
    title = ""
    try:
        title = (find_video(root, slug) / "titulo.txt").read_text("utf-8").strip().splitlines()[0]
    except (OSError, IndexError):
        pass
    clean = lambda text: " ".join(re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", text).split()).strip(" .")[:120]   # noqa: E731
    if path.name == "video-final.mp4":
        return f"{slug} - {clean(title)}.mp4" if title else f"{slug}.mp4"
    return f"{slug} - {path.name}"


HOLD = ".en-espera"        # = main.HOLD: the queue skips the video while this file is in its folder
REDO = ".rehacer"          # = main.REDO: a finished video made again from these stages


def redo(root: Path, slug: str, stages: list[str]) -> dict[str, Any]:
    """«Rehacer»: a finished video goes back to the queue and is made again from `stages` (planner by default); the
    final video it had stays until the new one replaces it."""

    from .runner import STAGE_NAMES

    chosen = [s for s in stages if s in STAGE_NAMES] or ["planner"]
    if running(_json(root / "work" / slug / "current.json")):
        raise ValueError("Este vídeo se está haciendo ahora: espera a que termine o páralo")
    (find_video(root, slug) / REDO).write_text("\n".join(chosen) + "\n", encoding="utf-8")
    state_path = root / "out" / "_vigilar.json"                 # a failed one goes now, not in 6 hours
    if (state := _json(state_path)) and slug in state:
        state.pop(slug)
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    if watcher_alive(root):
        (root / "out" / "_despertar").write_text(time.strftime("%H:%M:%S"), encoding="utf-8")
    return {"ok": True, "message": f"En la cola para rehacerse desde «{chosen[0]}». El vídeo actual sigue hasta que salga el nuevo."}


def hold(root: Path, slug: str, on: bool = True) -> dict[str, Any]:
    """«Quitar de la cola» / «Volver a la cola»: nothing is deleted, the video just waits."""

    marker = find_video(root, slug) / HOLD
    if on:
        marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
        return {"ok": True, "message": "Fuera de la cola: no se hará hasta que pulses «Volver a la cola»."}
    marker.unlink(missing_ok=True)
    if watcher_alive(root):
        (root / "out" / "_despertar").write_text(time.strftime("%H:%M:%S"), encoding="utf-8")
    return {"ok": True, "message": "De vuelta en la cola."}


def stop(root: Path, slug: str) -> dict[str, Any]:
    """«Parar»: the video being made stops now and leaves the queue. What it finished stays (it resumes from there
    with «Volver a la cola»). With the watcher as a service, the watcher restarts itself in about a minute."""

    import signal

    current = running(_json(root / "work" / slug / "current.json"))
    hold(root, slug, True)
    if not current or not current.get("pid"):
        return {"ok": True, "message": "No se estaba haciendo: queda fuera de la cola."}
    try:
        os.kill(int(current["pid"]), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, ValueError) as error:
        return {"ok": False, "message": f"No se pudo parar ({type(error).__name__}); queda fuera de la cola igualmente."}
    return {"ok": True, "message": "Parado y fuera de la cola. La cola sigue con el siguiente en un minuto."}


def archive(root: Path, slug: str) -> dict[str, Any]:
    """Out of the queue for good: materiales/_hechos/<slug>."""

    folder = find_video(root, slug)
    target = root / "materiales" / "_hechos" / slug
    target.parent.mkdir(parents=True, exist_ok=True)
    folder.rename(target)
    return {"ok": True}


def settings(root: Path, body: dict[str, Any] | None = None) -> dict[str, Any]:
    from . import budget

    path = root / "out" / "_ajustes.json"
    current = budget.settings(root)
    if body is not None:
        if "daily_usd" in body:
            current["daily_usd"] = max(0.0, float(body["daily_usd"] or 0))
        if "per_video_usd" in body:
            current["per_video_usd"] = max(0.0, float(body["per_video_usd"] or 0))
        if isinstance(body.get("my_channels"), dict):        # merged: an empty value removes that channel's entry
            mine = dict(current.get("my_channels") or {})
            for k, v in body["my_channels"].items():
                if k in channels(root):
                    if str(v).strip():
                        mine[str(k)] = str(v).strip()
                    else:
                        mine.pop(str(k), None)
            current["my_channels"] = mine
        if isinstance(body.get("channel_priority"), list):   # the queue makes these channels' videos first, in order
            known = channels(root)
            current["channel_priority"] = [str(c) for c in dict.fromkeys(body["channel_priority"]) if str(c) in known]
        if "proxy_gb" in body:                               # a proxy top-up: GB bought and the day (Estado del servidor)
            current["proxy_gb"] = max(0.0, float(body["proxy_gb"] or 0))
            current["proxy_since"] = str(body.get("proxy_since") or datetime.now().date().isoformat())[:10]
            datetime.fromisoformat(current["proxy_since"])
        if "paused" in body:
            flag = root / "out" / "_pausa"
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("pausa") if body["paused"] else flag.unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=1), encoding="utf-8")
    from .mychannel import handle_for

    mine = {c: handle_for(root, c) for c in channels(root)}
    return {**current, "paused": (root / "out" / "_pausa").is_file(), "channels": channels(root), "myChannels": mine}


_JOBS: dict[str, subprocess.Popen] = {}


def background(root: Path, name: str, args: list[str]) -> dict[str, Any]:
    """`python main.py <args>` in the background, one per name; its output in out/_tareas/<name>.log."""

    job = _JOBS.get(name)
    if job is not None and job.poll() is None:
        return {"ok": True, "running": True, "already": True}
    folder = root / "out" / "_tareas"
    folder.mkdir(parents=True, exist_ok=True)
    log = (folder / f"{name}.log").open("w", encoding="utf-8")
    _JOBS[name] = subprocess.Popen([sys.executable, str(root / "main.py"), *args], cwd=root, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    return {"ok": True, "running": True}


def job_state(root: Path, name: str) -> dict[str, Any]:
    job = _JOBS.get(name)
    log = root / "out" / "_tareas" / f"{name}.log"
    tail = log.read_text("utf-8", errors="replace")[-3000:] if log.is_file() else ""
    return {"running": job is not None and job.poll() is None,
            "failed": job is not None and job.poll() not in (None, 0), "log": tail}


def start_queue(root: Path) -> dict[str, Any]:
    """Runs the queue now in the background (when there is no watcher, e.g. on the home PC)."""

    return background(root, "cola", ["--all"])


def fix_video(root: Path, slug: str) -> dict[str, Any]:
    """«Rehacer con correcciones»: the shots marked wrong get a replacement and the video is made again."""

    from . import feedback

    find_video(root, slug)
    if not feedback.wrong_shots(root / "work" / slug):
        raise ValueError("No hay clips marcados como incorrectos en este vídeo")
    if running(_json(root / "work" / slug / "current.json")):
        raise ValueError("Este vídeo ya se está haciendo")
    return background(root, f"corregir-{slug}", ["--slug", slug, "--force", "fallback"])


def radar_state(root: Path) -> dict[str, Any]:
    from . import radar

    from . import niche_ideas

    niches = radar.niches(root)[:40]
    counts = niche_ideas.cached_ideas(root)
    for niche in niches:
        niche["ideas"] = counts.get(niche_ideas.seed_key({"kind": "niche", "query": niche["query"]}), 0)
        niche.pop("titles", None)
    from . import noticias

    news = noticias.latest(root)
    for name, stories in (news or {}).get("channels", {}).items():
        for story in stories:
            story["idea"] = noticias.idea_for(story, name)
    for name, stories in (news or {}).get("comebacks", {}).items():
        for story in stories:
            story["idea"] = {**noticias.idea_for(story, name), "format": "caida-y-regreso"}
    from . import huecos

    return {"latest": radar.latest(root), "niches": niches, "job": job_state(root, "radar"), "gaps": huecos.ranked(root),
            "saved": niche_ideas.saved(root), "channels": channels(root), "news": news,
            "newsJob": job_state(root, "noticias")}


def mychannel_state(root: Path, channel: str) -> dict[str, Any]:
    from . import mychannel

    if channel not in channels(root):
        raise FileNotFoundError(channel)
    return {"report": mychannel.saved(root, channel), "handle": mychannel.handle_for(root, channel),
            "job": job_state(root, f"canal-{channel}")}


def spending(root: Path, days: int = 14) -> list[dict[str, Any]]:
    per_day: dict[str, float] = {}
    for path in (root / "work").glob("*/costs.json"):
        for entry in (_json(path) or {}).get("entries", []):
            day = str(entry.get("at", ""))[:10]
            per_day[day] = per_day.get(day, 0.0) + float(entry.get("usd") or 0)
    return [{"day": d, "usd": round(v, 2)} for d, v in sorted(per_day.items())[-days:]]


# --- HTTP ---------------------------------------------------------------------------------------------------------

def _secret(password: str) -> bytes:
    return hashlib.sha256(("edit-vid3 web " + password).encode()).digest()


def make_handler(root: Path, password: str) -> type[BaseHTTPRequestHandler]:
    secret = _secret(password)
    failures: list[float] = []                       # wrong passwords lately (any client): 10 in 10 min → wait

    def token() -> str:
        stamp = str(int(time.time()))
        return stamp + "." + hmac.new(secret, stamp.encode(), hashlib.sha256).hexdigest()

    def valid(value: str) -> bool:
        stamp, _, sig = value.partition(".")
        if not stamp.isdigit() or time.time() - int(stamp) > 30 * 86400:
            return False
        return hmac.compare_digest(sig, hmac.new(secret, stamp.encode(), hashlib.sha256).hexdigest())

    class Handler(BaseHTTPRequestHandler):
        server_version = "edit-vid3"

        def log_message(self, *args: Any) -> None:  # quiet
            return

        # who may come in: this machine directly, or anyone with the session cookie
        def _local(self) -> bool:
            return self.client_address[0] in ("127.0.0.1", "::1") and not self.headers.get("X-Forwarded-For")

        def _authorised(self) -> bool:
            if self._local() and not password:
                return True
            cookie = self.headers.get("Cookie") or ""
            match = re.search(r"(?:^|;\s*)studio=([^;]+)", cookie)
            return bool(password) and bool(match) and valid(match.group(1))

        def handle_one_request(self) -> None:
            try:
                super().handle_one_request()
            except (BrokenPipeError, ConnectionResetError):   # the browser closed the page mid-answer: nothing to do
                self.close_connection = True

        def _send(self, code: int, body: bytes, kind: str = "application/json", headers: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            headers = {"Cache-Control": "no-store", **(headers or {})}
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _ok(self, data: Any, code: int = 200) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False, default=str).encode())

        def _fail(self, code: int, message: str) -> None:
            self._ok({"error": message}, code)

        def _file(self, path: Path) -> None:
            """A file, with Range support so the video plays and seeks in the browser."""

            size = path.stat().st_size
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or path.suffix in (".md", ".txt", ".log"):
                kind = "text/plain; charset=utf-8"
            start, end = 0, size - 1
            ranged = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if ranged and (ranged.group(1) or ranged.group(2)):
                if ranged.group(1):
                    start = int(ranged.group(1))
                    end = min(int(ranged.group(2)) if ranged.group(2) else size - 1, size - 1)
                else:
                    start = max(0, size - int(ranged.group(2)))
            self.send_response(206 if ranged else 200)
            self.send_header("Content-Type", kind)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if ranged:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if "download" in (self.path.split("?", 1)[1] if "?" in self.path else ""):
                name = download_name(root, path)
                ascii_name = name.encode("ascii", "ignore").decode() or path.name
                self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; '
                                                        f"filename*=UTF-8''{urllib.parse.quote(name)}")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = handle.read(min(1 << 20, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    left -= len(chunk)

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            url = urllib.parse.urlparse(self.path)
            path = url.path
            if path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/session":
                return self._ok({"authorised": self._authorised(), "needsPassword": bool(password) or not self._local()})
            if not self._authorised():
                return self._fail(401, "Inicia sesión")
            try:
                if path == "/api/overview":
                    return self._ok(overview(root))
                if path == "/api/stats":                   # «Estadísticas» (pipeline/estadisticas.py)
                    from . import estadisticas

                    return self._ok(estadisticas.report(root, bool(urllib.parse.parse_qs(url.query).get("refresh"))))
                if path == "/api/spending":
                    return self._ok(spending(root))
                if path == "/api/gasto":                   # «Gasto de API» (pipeline/gasto.py)
                    from . import gasto

                    return self._ok({**gasto.report(root), "allChannels": channels(root)})
                if path == "/api/servidor":                # «Estado del servidor» (pipeline/servidor.py)
                    from . import copia, servidor

                    return self._ok({**servidor.status(root), "backup": copia.info(root)})
                if path == "/api/copia":                   # the newest backup, to keep it on your PC / Drive
                    from . import copia

                    last = copia.latest(root)
                    if last is None:
                        return self._fail(404, "Aún no hay copia: espera a la semanal o pulsa «Hacer copia ahora»")
                    return self._send(200, last.read_bytes(), "application/gzip",
                                      {"Content-Disposition": f'attachment; filename="{last.name}"'})
                if path == "/api/experimentos":            # «Experimentos» (pipeline/experimentos.py)
                    from . import experimentos

                    return self._ok(experimentos.report(root))
                if path == "/api/settings":
                    return self._ok(settings(root))
                if path == "/api/agenda":                  # the publishing calendar (pipeline/agenda.py)
                    from . import agenda

                    listed = agenda.videos(root)
                    return self._ok({"settings": agenda.settings(root), "weekdays": agenda.WEEKDAYS,
                                     "plan": agenda.plan(root, days=28, listed=listed),
                                     "reserve": agenda.reserve(root, listed), "videos": listed})
                if path == "/api/voices":                  # GenAIPro voices per channel (pipeline/tts.py)
                    from . import tts

                    key = RunContext.create("_web", root=root).env("GENAIPRO_API_KEY", required=False)
                    return self._ok({"voices": tts.voices(root), "channels": channels(root), "models": list(tts.MODELS),
                                     "defaults": tts.DEFAULTS, "hasKey": bool(key),
                                     "dubbing": {c: tts.dubbing_for(root, c) for c in channels(root)},
                                     "dubLanguages": list(tts.DUB_LANGUAGES)})
                if path == "/api/voices/search":
                    from . import tts

                    query = urllib.parse.parse_qs(url.query)
                    key = RunContext.create("_web", root=root).env("GENAIPRO_API_KEY", required=False)
                    found = tts.GenAIPro(key).search((query.get("q") or [""])[0], (query.get("language") or [""])[0],
                                                     (query.get("gender") or [""])[0])
                    keep = ("voice_id", "name", "gender", "age", "accent", "language", "descriptive", "use_case",
                            "category", "preview_url", "description")
                    return self._ok([{k: v.get(k) for k in keep} for v in found if isinstance(v, dict)])
                if path == "/api/voices/credits":
                    from . import tts

                    key = RunContext.create("_web", root=root).env("GENAIPRO_API_KEY", required=False)
                    return self._ok(tts.GenAIPro(key).credits())
                if path == "/api/library":                 # «Biblioteca»: people and topics (pipeline/library.py)
                    from . import library

                    return self._ok({"entities": library.overview(root)})
                if match := re.fullmatch(r"/api/library/([a-z0-9-]+)", path):
                    from . import library

                    return self._ok(library.entity(root, match.group(1)))
                if path == "/api/library/clip":            # a clip that went on screen (?file=)
                    from . import library

                    found = library.clip_file(root, (urllib.parse.parse_qs(url.query).get("file") or [""])[0])
                    return self._file(found) if found else self._fail(404, "No existe")
                if match := re.fullmatch(r"/api/library/([a-z0-9-]+)/preview", path):
                    from . import library

                    found = library.preview(root, match.group(1), (urllib.parse.parse_qs(url.query).get("id") or [""])[0])
                    return self._file(found) if found else self._fail(404, "No existe")
                if path == "/api/upload/dates":            # Inicio: only the calendar day of each finished video
                    from . import organizar

                    return self._ok(cached(f"dates:{root}", 60, lambda: organizar.upload_dates(root)))
                if path == "/api/upload":                  # «Para subir» (pipeline/organizar.py)
                    from . import compilacion, organizar

                    return self._ok({"videos": organizar.to_upload(root), "compilations": compilacion.status(root),
                                     "compilationJob": job_state(root, "compilacion")})
                if path == "/api/scripts":                 # «Guiones»: what each channel's calendar still needs
                    from . import organizar

                    days = int((urllib.parse.parse_qs(url.query).get("days") or ["14"])[0])
                    return self._ok({"channels": organizar.scripts_needed(root, days), "days": days})
                if path == "/api/board":
                    from . import agenda

                    return self._ok({"columns": agenda.board(root), "channels": agenda.channels(root)})
                if path == "/api/notify":
                    from . import notify

                    return self._ok(notify.status(RunContext.create("_web", root=root)))
                if match := re.fullmatch(r"/api/video/([^/]+)", path):
                    return self._ok(video_detail(root, urllib.parse.unquote(match.group(1))))
                if match := re.fullmatch(r"/api/video/([^/]+)/voz\.mp3", path):     # to check it is the right voice
                    slug = urllib.parse.unquote(match.group(1))
                    voice = find_video(root, slug) / "voz.mp3"
                    if slug.startswith(".") or "/" in slug or not voice.is_file():
                        return self._fail(404, "No hay voz")
                    return self._file(voice)
                if match := re.fullmatch(r"/api/review/([^/]+)", path):
                    from . import feedback

                    slug = urllib.parse.unquote(match.group(1))
                    return self._ok({"shots": feedback.shots(root, slug), "reasons": feedback.REASONS,
                                     "job": job_state(root, f"corregir-{slug}")})
                if match := re.fullmatch(r"/api/review/([^/]+)/frame/([A-Za-z0-9_-]+)\.jpg", path):
                    from . import feedback

                    image = feedback.frame(root, urllib.parse.unquote(match.group(1)), match.group(2))
                    if image is None:
                        return self._fail(404, "Sin imagen")
                    return self._send(200, image.read_bytes(), "image/jpeg", {"Cache-Control": "max-age=86400"})
                if match := re.fullmatch(r"/api/decisions/([^/]+)", path):
                    from . import decisions

                    slug = urllib.parse.unquote(match.group(1))
                    return self._ok({"items": decisions.items(root, slug), "summary": decisions.summary(root),
                                     "job": job_state(root, f"corregir-{slug}")})
                if match := re.fullmatch(r"/api/decisions/([^/]+)/frame", path):
                    from . import decisions

                    query = urllib.parse.parse_qs(url.query)
                    image = decisions.frame(root, urllib.parse.unquote(match.group(1)), (query.get("shot") or [""])[0],
                                            (query.get("key") or [""])[0])
                    if image is None:
                        return self._fail(404, "Sin imagen")
                    return self._send(200, image.read_bytes(), "image/jpeg", {"Cache-Control": "max-age=86400"})
                if path == "/api/search":                  # ?q=…: «¿ya lo hice?» por título o guion
                    return self._ok(search_videos(root, (urllib.parse.parse_qs(url.query).get("q") or [""])[0][:20000]))
                if match := re.fullmatch(r"/api/video/([^/]+)/pilot", path):
                    from . import piloto

                    slug = urllib.parse.unquote(match.group(1))
                    registry = piloto._registry(root)
                    return self._ok({"pilot": registry.get(slug), "others": sorted(set(registry) - {slug}),
                                     "references": [v for v in piloto.finished(root) if v != slug],
                                     "report": _json(root / "out" / slug / "piloto.json")})
                if path == "/api/scenebench":              # the last per-shot vs scene search comparison
                    from . import scenebench

                    return self._ok({"result": _json(root / scenebench.OUTPUT),
                                     "job": job_state(root, "comparar-escenas")})
                if path == "/api/ytbench":                 # the last speed test of the ways to YouTube
                    from . import ytbench

                    found = _json(root / ytbench.OUTPUT)
                    return self._ok({"result": found, "job": job_state(root, "velocidad-youtube")})
                if path == "/api/errors":
                    from . import feedback

                    return self._ok(feedback.summary(root))
                if path == "/api/radar":
                    return self._ok(radar_state(root))
                if match := re.fullmatch(r"/api/mychannel/([^/]+)", path):
                    return self._ok(mychannel_state(root, urllib.parse.unquote(match.group(1))))
                if match := re.fullmatch(r"/files/([^/]+)/(.+)", path):
                    slug, rel = urllib.parse.unquote(match.group(1)), urllib.parse.unquote(match.group(2))
                    base = (root / "out" / slug).resolve()
                    target = (base / rel).resolve()
                    if base not in target.parents or not target.is_file():          # never outside out/<vídeo>/
                        return self._fail(404, "No existe")
                    return self._file(target)
            except FileNotFoundError:
                return self._fail(404, "No existe")
            except Exception as error:
                return self._fail(500, f"{type(error).__name__}: {error}")
            self._fail(404, "No existe")

        def do_POST(self) -> None:
            url = urllib.parse.urlparse(self.path)
            path = url.path
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                return self._fail(413, "Archivo demasiado grande")
            if path == "/api/login":
                body = json.loads(self.rfile.read(length) or b"{}")
                failures[:] = [t for t in failures if time.time() - t < 600]
                if len(failures) >= 10:
                    return self._fail(429, "Demasiados intentos: espera 10 minutos")
                if password and hmac.compare_digest(str(body.get("password") or ""), password):
                    secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                    return self._send(200, b'{"ok": true}', headers={
                        "Set-Cookie": f"studio={token()}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000{secure}"})
                failures.append(time.time())
                time.sleep(1.5)                                  # slows down guessing
                return self._fail(403, "Contraseña incorrecta")
            if not self._authorised():
                return self._fail(401, "Inicia sesión")
            if self.headers.get("Origin") and urllib.parse.urlparse(self.headers["Origin"]).netloc != self.headers.get("Host"):
                return self._fail(403, "Origen no permitido")
            try:
                if match := re.fullmatch(r"/api/video/([^/]+)/voz", path):
                    return self._ok(save_voice(root, urllib.parse.unquote(match.group(1)), self.rfile.read(length)))
                body = json.loads(self.rfile.read(length) or b"{}")
                if path == "/api/videos":
                    return self._ok(create_video(root, body))
                if path == "/api/copia":                   # «Hacer copia ahora»
                    from . import copia

                    return self._ok({"made": copia.make(root).name, "backup": copia.info(root)})
                if match := re.fullmatch(r"/api/experimentos/([^/]+)", path):     # {tags, retention30, retentionAvg, ctr}
                    from . import experimentos

                    slug = urllib.parse.unquote(match.group(1))
                    if not find_video(root, slug).is_dir():
                        raise ValueError("Vídeo desconocido")
                    return self._ok(experimentos.set_notes(root, slug, body))
                if match := re.fullmatch(r"/api/video/([^/]+)/(retry|archive|hold|unhold|stop|redo)", path):
                    slug, verb = urllib.parse.unquote(match.group(1)), match.group(2)
                    if verb in ("hold", "unhold"):
                        return self._ok(hold(root, slug, verb == "hold"))
                    if verb == "redo":
                        return self._ok(redo(root, slug, [str(x) for x in body.get("stages") or ["planner"]]))
                    action = {"retry": retry, "archive": archive, "stop": stop}[verb]
                    return self._ok(action(root, slug))
                if path == "/api/settings":
                    return self._ok(settings(root, body))
                if path == "/api/search":                  # {q}: a whole pasted script does not fit in a URL
                    return self._ok(search_videos(root, str(body.get("q") or "")[:30000]))
                if path == "/api/ytbench":
                    return self._ok(background(root, "velocidad-youtube", ["--velocidad-youtube"]))
                if path == "/api/scenebench":             # offline: not one request to YouTube
                    return self._ok(background(root, "comparar-escenas", ["--comparar-escenas"]))
                if path == "/api/restart-queue":
                    return self._ok(restart_queue(root))
                if path == "/api/youtube/retry":
                    return self._ok(youtube_retry_now(root))
                if match := re.fullmatch(r"/api/video/([^/]+)/for-claude", path):
                    return self._ok({"text": for_claude(root, urllib.parse.unquote(match.group(1)))})
                if match := re.fullmatch(r"/api/video/([^/]+)/pilot", path):     # {on, reference}: the scene pilot
                    from . import piloto

                    slug = urllib.parse.unquote(match.group(1))
                    if body.get("on") is False:
                        return self._ok(piloto.disable(root, slug))
                    if body.get("report"):
                        return self._ok(piloto.report(root, slug, body.get("reference") or None))
                    return self._ok(piloto.enable(root, slug, body.get("reference") or None))
                if path == "/api/update":
                    return self._ok(update_code(root))
                if path == "/api/queue":
                    return self._ok(start_queue(root))
                if path == "/api/queue/retry-all":
                    return self._ok(retry_all(root))
                if path == "/api/agenda":                  # days and time of a channel, options, pin a video to a day
                    from . import agenda

                    return self._ok(agenda.update(root, body))
                if path == "/api/voices":                  # {channel, voice_id, name, model_id, stability, …}
                    from . import tts

                    if str(body.get("channel") or "") not in channels(root):
                        raise ValueError("Canal desconocido")
                    return self._ok(tts.set_voice(root, str(body["channel"]), body))
                if path == "/api/dubbing":                 # {channel, languages, voices: {lang: {voice_id}}, existing}
                    from . import tts

                    if str(body.get("channel") or "") not in channels(root):
                        raise ValueError("Canal desconocido")
                    return self._ok(tts.set_dubbing(root, str(body["channel"]), body))
                if path == "/api/voices/test":             # {channel | voice_id, text}: a short sample to listen to
                    from . import tts

                    voice = tts.voice_for(root, str(body.get("channel") or "")) or {}
                    if body.get("voice_id"):
                        voice = {**tts.DEFAULTS, **voice, "voice_id": str(body["voice_id"])}
                    if not voice.get("voice_id"):
                        raise ValueError("Pon el ID de la voz")
                    text = str(body.get("text") or "").strip()[:600] or \
                        "Esta es una prueba de la voz del canal. Así sonará la narración de tus vídeos."
                    name = f"prueba-{re.sub(r'[^a-z0-9-]', '', str(body.get('channel') or 'voz').lower())}-{int(time.time())}.mp3"
                    key = RunContext.create("_web", root=root).env("GENAIPRO_API_KEY", required=False)
                    tts.generate(key, text, voice, root / "out" / "_voces" / name, log=lambda *_: None)
                    return self._ok({"url": f"/files/_voces/{name}"})
                if match := re.fullmatch(r"/api/library/([a-z0-9-]+)/remove", path):    # {id} or {} (all of it)
                    from . import library

                    library.remove(root, match.group(1), body.get("id") or None)
                    return self._ok({"ok": True})
                if path == "/api/scripts/similar":         # {slug, refresh?}: «más como este» (a video that worked)
                    from . import organizar

                    slug = str(body.get("slug") or "")
                    if not re.fullmatch(r"[\w-]{1,80}", slug):
                        raise ValueError("Vídeo no válido")
                    return self._ok(organizar.similar_ideas(root, slug, refresh=bool(body.get("refresh"))))
                if path == "/api/compilations":            # {channel}: a long compilation, in the background
                    channel = str(body.get("channel") or "")
                    if not CHANNEL.match(channel):
                        raise ValueError("Canal no válido")
                    return self._ok(background(root, "compilacion", ["--compilar", channel]))
                if path == "/api/scripts/draft":           # {channel, idea: {title, note…}} → a first draft
                    from . import organizar

                    return self._ok(organizar.draft_script(root, str(body.get("channel") or ""), body.get("idea") or {}))
                if path == "/api/board/idea":
                    from . import agenda

                    if body.get("delete"):
                        agenda.remove_idea(root, str(body["delete"]))
                        return self._ok({"ok": True})
                    return self._ok(agenda.add_idea(root, str(body.get("title") or ""), str(body.get("channel") or ""),
                                                    str(body.get("note") or ""), str(body.get("date") or "")))
                if path == "/api/channels":                # a new channel profile
                    return self._ok(create_channel(root, body))
                if path == "/api/hook":                    # {title, script, channel}: before recording
                    from . import hook

                    channel = str(body.get("channel") or "")
                    ctx = RunContext.create("_gancho", root=root, channel=channel if channel in channels(root) else None)
                    title = str(body.get("title") or "").strip()
                    if not title:
                        raise ValueError("Pon el título que vas a usar: el gancho se mide contra él")
                    return self._ok(hook.review(ctx, title, str(body.get("script") or "")))
                if path == "/api/notify":                  # {token?, studio_url?}: save, find the chat, send a test
                    from . import notify

                    return self._ok(notify.setup(RunContext.create("_web", root=root), str(body.get("token") or ""),
                                                 str(body.get("studio_url") or "")))
                if match := re.fullmatch(r"/api/review/([^/]+)/([A-Za-z0-9_-]+)", path):
                    from . import feedback

                    return self._ok(feedback.label(root, urllib.parse.unquote(match.group(1)), match.group(2),
                                                   body.get("verdict"), str(body.get("reason") or "")))
                if match := re.fullmatch(r"/api/video/([^/]+)/channel", path):      # {channel}
                    return self._ok(set_channel(root, urllib.parse.unquote(match.group(1)), str(body.get("channel") or "")))
                if match := re.fullmatch(r"/api/video/([^/]+)/published", path):    # {value: bool, url}
                    from .housekeeping import mark_published

                    return self._ok(mark_published(root, urllib.parse.unquote(match.group(1)), str(body.get("url") or ""),
                                                   bool(body.get("value", True))))
                if match := re.fullmatch(r"/api/decisions/([^/]+)/apply", path):
                    from . import decisions

                    slug = urllib.parse.unquote(match.group(1))
                    if (root / "work" / slug / "current.json").is_file() and running(_json(root / "work" / slug / "current.json")):
                        raise ValueError("Este vídeo se está haciendo ahora: espera a que termine")
                    count = decisions.apply(root, slug)
                    from .feedback import wrong_shots

                    if not count and not wrong_shots(root / "work" / slug):
                        raise ValueError("No has elegido ninguna opción todavía")
                    return self._ok({**background(root, f"corregir-{slug}", ["--slug", slug, "--force", "fallback"]),
                                     "applied": count})
                if match := re.fullmatch(r"/api/decisions/([^/]+)/([A-Za-z0-9_-]+)", path):
                    from . import decisions

                    return self._ok(decisions.decide(root, urllib.parse.unquote(match.group(1)), match.group(2),
                                                     ok=body.get("ok"), pick=body.get("pick")))
                if match := re.fullmatch(r"/api/video/([^/]+)/fix", path):
                    return self._ok(fix_video(root, urllib.parse.unquote(match.group(1))))
                if path == "/api/radar":
                    return self._ok(background(root, "radar", ["--radar"]))
                if path == "/api/radar/gap":               # {topic}: measure a topic you have in mind (~400 units)
                    from . import huecos

                    return self._ok(huecos.evaluate(root, str(body.get("topic") or "")))
                if path == "/api/news":                    # «Noticias del día» now, not tomorrow morning
                    return self._ok(background(root, "noticias", ["--noticias"]))
                if path == "/api/ideas":                   # {seed: {kind: niche|video, …}, more: bool}
                    from . import niche_ideas

                    seed = body.get("seed") or {}
                    if seed.get("kind") not in ("niche", "video"):
                        raise ValueError("¿Ideas de qué?")
                    return self._ok(niche_ideas.ideas(root, seed, more=bool(body.get("more"))))
                if path == "/api/ideas/save":
                    from . import niche_ideas

                    if body.get("remove"):
                        return self._ok(niche_ideas.unsave(root, str(body["remove"])))
                    return self._ok(niche_ideas.save(root, body.get("idea") or {}, str(body.get("channel") or "")))
                if path == "/api/niche-channel":
                    from . import niche_ideas

                    return self._ok(niche_ideas.make_profile(root, str(body.get("query") or ""), str(body.get("name") or "")))
                if match := re.fullmatch(r"/api/mychannel/([^/]+)", path):
                    channel = urllib.parse.unquote(match.group(1))
                    if channel not in channels(root):
                        return self._fail(404, "No existe")
                    return self._ok(background(root, f"canal-{channel}", ["--mi-canal", channel]))
            except (ValueError, FileExistsError) as error:
                return self._fail(400, str(error))
            except FileNotFoundError:
                return self._fail(404, "No existe")
            except Exception as error:
                return self._fail(500, f"{type(error).__name__}: {error}")
            self._fail(404, "No existe")

    return Handler


def _reload_on_new_code(root: Path, every: float = 120.0) -> None:
    """On the server the studio keeps itself up to date: it pulls the code every 2 minutes and, when it changed,
    restarts with it (the queue does the same between videos). No more `git pull && systemctl restart`."""

    import subprocess

    def head() -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()

    running_code = head()
    while running_code:
        time.sleep(every)
        try:
            subprocess.run(["git", "pull", "--ff-only", "-q"], cwd=root, capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            continue
        if head() not in ("", running_code):
            print("Código nuevo (git pull): el estudio se reinicia con él", flush=True)
            os.execv(sys.executable, [sys.executable, *sys.argv])


def serve(port: int = 8080, host: str = "127.0.0.1", root: Path = PROJECT_ROOT, open_browser: bool = True) -> None:
    ctx = RunContext.create("_web", root=root)
    password = ctx.env("WEB_PASSWORD", required=False) or ""
    if host not in ("127.0.0.1", "localhost", "::1") and not password:
        raise SystemExit("Para abrir el estudio fuera de este equipo pon WEB_PASSWORD=… en .env")
    server = ThreadingHTTPServer((host, port), make_handler(root, password))
    if host in ("127.0.0.1", "localhost") and not sys.platform.startswith(("win", "darwin")) and not os.environ.get("DISPLAY") \
            and ctx.section("watch").get("git_pull", True):
        threading.Thread(target=_reload_on_new_code, args=(root,), daemon=True).start()
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
    print(f"Estudio en {url}" + (" (con contraseña)" if password else "") + " · Ctrl+C para cerrar")
    desktop = sys.platform in ("win32", "darwin") or bool(os.environ.get("DISPLAY"))     # not on a server
    if open_browser and desktop and host in ("127.0.0.1", "localhost"):
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
