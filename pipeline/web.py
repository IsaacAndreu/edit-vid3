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

import gzip
import hashlib
import hmac
import json
import secrets
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
from email.utils import formatdate, parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from . import usuarios
from .context import RunContext, find_video, load_config, video_folders

STATIC = Path(__file__).with_name("web_static")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$")
MAX_UPLOAD = 400 * 1024 * 1024                # a 15-min voice in mp3 is ~15-30 MB; leave room for wav
STATIC_KINDS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2"}


# --- the page itself: index.html + css/js, each with an ETag; the assets carry a version in their URL ---------------

_STATIC: dict[str, tuple[tuple[int, int, str], bytes, bytes, str, float]] = {}   # name → (mtime, size, version), body, gzip, etag, mtime
_STATIC_LOCK = threading.Lock()


def static_version() -> str:
    """Changes when any file of the page changes (a `git pull` is enough: no build step)."""

    stamp = sorted((p.relative_to(STATIC).as_posix(), p.stat().st_mtime_ns, p.stat().st_size)
                   for p in STATIC.rglob("*") if p.is_file())
    return hashlib.sha256(repr(stamp).encode()).hexdigest()[:12]


def static_file(name: str) -> tuple[bytes, bytes, str, str, float] | None:
    """(body, gzipped body, ETag, content type, modified) of a file of web_static, read once per version of the file.

    index.html gets the version of the whole page in the URLs of its css and js ({{v}}), so the browser keeps those
    for good and asks again only when they change."""

    path = (STATIC / name).resolve()
    if STATIC.resolve() not in path.parents or not path.is_file() or path.suffix not in STATIC_KINDS:
        return None
    version = static_version() if name == "index.html" else ""
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size, version)
    with _STATIC_LOCK:
        hit = _STATIC.get(name)
    if not hit or hit[0] != key:
        body = path.read_bytes()
        if version:
            body = body.replace(b"{{v}}", version.encode())
        modified = max(p.stat().st_mtime for p in [STATIC, *STATIC.rglob("*")]) if version else stat.st_mtime   # a removed file moves its folder's date
        hit = (key, body, gzip.compress(body, 6, mtime=0), hashlib.sha256(body).hexdigest()[:16], modified)
        with _STATIC_LOCK:
            _STATIC[name] = hit
    return hit[1], hit[2], hit[3], STATIC_KINDS[path.suffix], hit[4]


# --- what the pages show ----------------------------------------------------------------------------------------

def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def channels(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "canales").glob("*.yaml"))


def channel_kinds(root: Path) -> dict[str, str]:
    """Each channel's kind for the new-video form: «simulacion», «stickman» or «metraje» (third-party footage), from
    its profile's visual.style (a channel built on another, `base:`, takes that one's)."""

    out: dict[str, str] = {}
    for name in channels(root):
        if _json_yaml(root / "canales" / f"{name}.yaml").get("oculto"):
            out[name] = "oculto"                 # a channel put away (`oculto: true`): not offered for new videos
            continue
        style = ""
        seen: set[str] = set()
        current = name
        while current and current not in seen:
            seen.add(current)
            data = _json_yaml(root / "canales" / f"{current}.yaml")
            style = str((data.get("visual") or {}).get("style") or "").lower()
            if style:
                break
            current = str(data.get("base") or "")
        out[name] = ("simulacion" if style in ("simulacion", "simulación", "simulation")
                     else "stickman" if style in ("stickman", "cine") else "mapas" if style in ("mapas", "atlas") else "metraje")
    return out


def _dub_options(root: Path, channel: str) -> list[dict[str, Any]]:
    try:
        from .doblaje import options

        return options(root, channel)
    except Exception:
        return []


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


_VERTICAL: dict[str, tuple[float, bool]] = {}


def is_short(root: Path, folder: Path, channel: str = "") -> bool:
    """A Short: one made from a long video (<slug>-shortN, `shorts.of`), a `serie: short`, a vertical format, or a
    video of a vertical channel (its profile 1080x1920, like the rules thrillers)."""

    if re.search(r"-short\d+$", folder.name):
        return True
    cfg = _json_yaml(folder / "config.yaml")
    if (cfg.get("shorts") or {}).get("of") or str(cfg.get("serie") or "") == "short" or str(cfg.get("format") or "") == "short":
        return True
    video = cfg.get("video") or {}
    if video.get("height") and video.get("width"):
        return int(video["height"]) > int(video["width"])
    if not channel:
        return False
    path = root / "canales" / f"{channel}.yaml"
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return False
    hit = _VERTICAL.get(channel)
    if not hit or hit[0] != stamp:
        size = (_json_yaml(path).get("video") or {})
        hit = (stamp, int(size.get("height") or 1080) > int(size.get("width") or 1920))
        _VERTICAL[channel] = hit
    return hit[1]


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


def _thumb(out: Path) -> str | None:
    """The video's first thumbnail (out/<slug>/miniatura*.png or miniaturas/*), for its card in the studio."""

    if not out.is_dir():
        return None
    for pattern in ("miniatura*", "miniaturas/*"):
        found = sorted(p for p in out.glob(pattern) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
        if found:
            return found[0].relative_to(out).as_posix()
    return None


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
    from . import sin_youtube

    if quota_wait is None and sin_youtube.waiting(root, slug):   # made without YouTube, short: waits for it (not a failure)
        problems = (_json(work / sin_youtube.STATE) or {}).get("problems") or []
        quota_wait = "espera a YouTube: " + "; ".join(problems)[:200]
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
    channel = _channel_of(root, folder)
    return {
        "slug": slug, "channel": channel, "status": status, "quotaWait": quota_wait, "short": is_short(root, folder, channel),
        "archived": any(part.startswith("_") for part in folder.relative_to(root / "materiales").parts),
        "stage": current, "stagesDone": len(stages), "costUsd": round(float(costs.get("totalUsd") or 0), 2),
        "error": None if done or current or queued_again else diag.get("error") or ((failed or {}).get("status") and "falló"),
        "lastError": (diag.get("error") or "falló") if queued_again else None,
        "voice": voice,
        "retryAt": time.strftime("%H:%M", time.localtime(retry_at)) if retry_at else None,
        "updated": max([p.stat().st_mtime for p in [folder, *(out.glob("*") if out.is_dir() else [])]]),
        "hasVideo": (out / "video-final.mp4").is_file(), "published": uploaded or None, "removed": removed,
        "thumb": _thumb(out),
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
            # distinctive words of both scripts in common (names, places, figures repeat across a topic), against
            # both sizes: over the smaller one alone, a 1-hour script (patiICE) «contained» any new script
            score = len(wanted_set & body_set) / max(1.0, (len(wanted_set) * len(body_set)) ** 0.5)
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
        # yours: a partner's videos count against their own caps (usuarios.py), not these
        "budget": {"today": budget.spent_today(root, ""), "limit": budget.limit(root, config),
                   "proxyGbToday": cached(f"proxyday:{root}", 60, lambda: budget.proxy_gb_today(root, "")),
                   "proxyGbLimit": budget.proxy_limit(root, config)},
        "videos": videos, "channels": channels(root), "channelKinds": channel_kinds(root), "formats": formats(root),
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
        ask_retry(root, "_todos")
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
    stages = " · ".join(f"{s['name']} {round((s.get('seconds') or 0) / 60, 1)} min" for s in (detail.get("stages") or []))
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
        "graphics": read("graficos.md"), "hook": read("gancho.md"), "retention": read("retencion.md"), "rhythm": read("qa/ritmo.md"), "audit": audit_text(root, slug),
        "thumbnails": [f for f in files if f.startswith("miniaturas/") or re.match(r"miniatura", f)],
        "scenesPreview": "vista-previa.jpg" if "vista-previa.jpg" in files else "",
        "shorts": [f for f in files if f.startswith("shorts/") and f.endswith(".mp4")],
        "files": files,
        "preview": ensure_preview(root, slug) if summary.get("hasVideo") else False,
        "script": (folder / "guion.txt").read_text("utf-8", errors="replace")[:20000] if (folder / "guion.txt").is_file() else "",
        "format": _format_of(root, folder),
        "dubs": _dubs(root, slug),
        "youtube": _video_youtube(work),
        "costs": _costs_by_stage(root, slug),
    }


def proxy_report(root: Path, days: float = 7.0) -> dict[str, Any]:
    """What the proxies carried in the last `days` (work/*/youtube_downloads.jsonl): per proxy, requests, success,
    errors by kind, sessions, GB, GB and $ per finished video, the most frequent error words; plus GB per day."""

    from . import ytstats
    from .housekeeping import is_done

    since = time.time() - days * 86400
    per_video = {p.parent.name: ytstats.read(p, since) for p in sorted((root / "work").glob("*/youtube_downloads.jsonl"))}
    per_video = {slug: rows for slug, rows in per_video.items() if rows}
    finished = {slug for slug in per_video if is_done(root, slug)}
    usd = ytstats._usd_per_gb(root)
    proxies = ytstats.proxy_summary(per_video, finished, usd)
    per_day: dict[str, float] = {}
    for rows in per_video.values():
        for row in rows:
            day = time.strftime("%Y-%m-%d", time.localtime(float(row.get("ts") or 0)))
            per_day[day] = per_day.get(day, 0.0) + int(row.get("proxy_bytes") or 0) / 1e9
    total_gb = round(sum(p["gb"] for p in proxies), 3)
    return {"days": days, "proxies": proxies, "usdPerGb": usd, "totalGb": total_gb, "usd": round(total_gb * usd, 2),
            "videos": len(per_video), "finished": len(finished),
            "gbPerFinished": round(total_gb / len(finished), 3) if finished else None,
            "perDay": [{"day": d, "gb": round(g, 3)} for d, g in sorted(per_day.items())]}


def _video_youtube(work: Path) -> dict[str, Any] | None:
    """This video's requests to YouTube (work/<slug>/youtube_downloads.jsonl): how many, how many failed and why,
    the GB the proxy carried and the most frequent error words, for the video page."""

    import time

    from . import ytstats

    everything = ytstats.read(work / "youtube_downloads.jsonl")
    if not everything:
        return None
    # the last two days, not the video's whole history: a video retried over a week carries thousands of requests
    # of proxies and bugs long gone (gym6.0: 11,064 requests at 4 %, of which 9,185 to a dead proxy)
    hours = 48
    rows = [r for r in everything if float(r.get("ts") or 0) >= time.time() - hours * 3600] or everything
    summary = ytstats.summary(rows)
    summary["hours"] = hours if len(rows) < len(everything) else None
    if len(rows) < len(everything):
        whole = ytstats.summary(everything)
        summary["allTime"] = {"requests": whole["requests"], "ok": whole["ok"], "proxy_gb": whole.get("proxy_gb", 0),
                              "files_ok": whole["files_ok"], "files": whole["files"]}
    details: dict[str, int] = {}
    for row in rows:
        if not row.get("ok") and row.get("detail"):
            text = re.sub(r"^yt-dlp [^:]+: (ERROR: )?", "", str(row["detail"]))[:140]
            details[text] = details.get(text, 0) + 1
    summary["details"] = sorted(details.items(), key=lambda kv: -kv[1])[:4]
    summary["proxy"] = sorted({str(r["proxy"]) for r in rows if r.get("proxy")})
    return summary


def _costs_by_stage(root: Path, slug: str) -> dict[str, float]:
    """API dollars per stage (work/<slug>/costs.json), for the video page's timeline."""

    out: dict[str, float] = {}
    for entry in (_json(root / "work" / slug / "costs.json") or {}).get("entries") or []:
        if isinstance(entry, dict):
            stage = str(entry.get("stage") or "")
            out[stage] = round(out.get(stage, 0.0) + float(entry.get("usd") or 0), 3)
    return out


def _dubs(root: Path, slug: str) -> list[dict[str, Any]]:
    try:
        from . import doblaje

        return doblaje.status(root, slug)
    except Exception:             # a video of a deleted channel, a broken config: no dubbing box
        return []


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
    opening = None
    if isinstance(body.get("opening"), dict) and body["opening"].get("candidate"):   # the opening clip you chose
        from . import apertura

        chosen = body["opening"]
        opening = apertura.choice(chosen["candidate"], apertura._seconds(chosen.get("start")), apertura._seconds(chosen.get("end")),
                                  subtitles=chosen.get("subtitles") is not False, credit=str(chosen.get("credit") or ""))
        upload = root / "out" / "_tareas" / f"apertura-{opening['file']}.mp4" if opening.get("file") else None
        if upload is not None and not upload.is_file():
            raise ValueError("El vídeo subido para la apertura ya no está: vuelve a subirlo y buscar")
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
    if str(body.get("scenes") or "").strip():             # the scene list for a simulation video (simulacion.DIRECTOR)
        (folder / "escenas.txt").write_text(str(body["scenes"]).strip() + "\n", encoding="utf-8")
    if opening:
        if opening.get("file"):                            # your uploaded video goes with the video's materials
            shutil.move(str(root / "out" / "_tareas" / f"apertura-{opening['file']}.mp4"), str(folder / "apertura.mp4"))
            opening["file"] = "apertura.mp4"
        (folder / "apertura.json").write_text(json.dumps(opening, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if isinstance(body.get("idea"), dict):                 # made from a radar idea: the brief next to the script
        from .niche_ideas import brief

        (folder / "idea.md").write_text(brief(body["idea"]), encoding="utf-8")
    extra = {k: str(body[k]).strip() for k in ("serie", "format") if str(body.get(k) or "").strip()}
    lang = str(body.get("language") or "es").strip()
    if lang not in ("es", "en", "pt", "fr", "it", "de"):
        raise ValueError(f"Idioma desconocido: {lang}")
    lines = "".join(f"{k}: {v}\n" for k, v in extra.items())
    if lang != "es":                       # a video made directly in another language: its voice, texts and titles
        lines += f"align:\n  language: {lang}\n"
    if lines:
        (folder / "config.yaml").write_text(lines, encoding="utf-8")
    if isinstance(body.get("dub"), list):                  # a simulation channel: the languages you UNticked
        from . import doblaje

        ticked = [str(l) for l in body["dub"]]
        offered = [o["lang"] for o in doblaje.options(root, str(body.get("channel") or "")) if o.get("voice")]
        skip = [l for l in offered if l not in ticked]         # one without a voice yet is dubbed once it has one
        if skip:
            with (folder / "config.yaml").open("a", encoding="utf-8") as f:
                f.write(f"dub_skip: [{', '.join(skip)}]\n")
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


RETRY_DIR = "out/_reintentar"          # «Reintentar» while a round goes on: main.run_parallel takes it again then


def ask_retry(root: Path, slug: str) -> None:
    folder = root / RETRY_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / slug).write_text(time.strftime("%H:%M:%S"), encoding="utf-8")


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
        ask_retry(root, slug)
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
        ask_retry(root, "_todos")
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
        ask_retry(root, "_todos")
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
        ask_retry(root, "_todos")
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

    if running(_json(root / "work" / slug / "current.json")):
        return {"ok": False, "message": "Se está haciendo ahora: pulsa «Parar» primero y luego quítalo de la lista."}
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
        if "proxy_gb_per_day" in body:
            current["proxy_gb_per_day"] = max(0.0, float(body["proxy_gb_per_day"] or 0))
        if "server_usd_month" in body:                     # what the server costs a month: split by hours of work
            current["server_usd_month"] = max(0.0, float(body["server_usd_month"] or 0))
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
            with _CACHE_LOCK:
                _CACHE.pop(f"servidor:{root}", None)             # «Estado del servidor» shows the top-up at once
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


def spending(root: Path, days: int = 14, owner: str | None = None) -> list[dict[str, Any]]:
    from .budget import owner_of_work

    per_day: dict[str, float] = {}
    for path in (root / "work").glob("*/costs.json"):
        if owner is not None and owner_of_work(root, path.parent.name) != owner:
            continue
        for entry in (_json(path) or {}).get("entries", []):
            day = str(entry.get("at", ""))[:10]
            per_day[day] = per_day.get(day, 0.0) + float(entry.get("usd") or 0)
    return [{"day": d, "usd": round(v, 2)} for d, v in sorted(per_day.items())[-days:]]


# --- partners: a closed list of what they may open, and only their channels ------------------------------------

# Everything not listed here answers 403 to a partner (usuarios.py). The video routes also need the video to be in
# one of their channels; the ones with a channel in the body (a new video, moving one), that channel too.
PARTNER_GET = ("/api/overview", "/api/gasto", "/api/search", "/api/upload", "/api/upload/dates", "/api/factura.csv",
               "/api/voices", "/api/voices/search", "/api/cuenta", "/api/agenda", "/api/scripts", "/api/board", "/api/radar",
               "/api/stats", "/api/spending", "/api/canales")
PARTNER_POST = ("/api/videos", "/api/search", "/api/apertura", "/api/apertura/subir", "/api/hook", "/api/scenes",
                "/api/voices", "/api/voices/test", "/api/channels", "/api/telegram/link", "/api/telegram/unlink",
                "/api/agenda", "/api/scripts/draft", "/api/scripts/similar", "/api/board/idea", "/api/board/temas",
                "/api/ideas", "/api/ideas/save")
PARTNER_WITH_CHANNEL = ("/api/videos", "/api/apertura", "/api/hook", "/api/scenes", "/api/voices", "/api/voices/test",
                        "/api/scripts/draft", "/api/board/temas")
PARTNER_VIDEO_GET = (r"/api/video/([^/]+)", r"/api/video/([^/]+)/(?:repeticion|porque|capcut|exportar|voz\.mp3)",
                     r"/api/review/([^/]+)", r"/api/review/([^/]+)/frame/[A-Za-z0-9_-]+\.jpg",
                     r"/api/decisions/([^/]+)", r"/api/decisions/([^/]+)/frame", r"/files/([^/]+)/.+")
PARTNER_VIDEO_POST = (r"/api/video/([^/]+)/(?:voz|retencion|doblaje|retry|archive|hold|unhold|stop|redo|for-claude|porque"
                      r"|capcut|exportar|published|fix|channel)",
                      r"/api/review/([^/]+)/[A-Za-z0-9_-]+", r"/api/decisions/([^/]+)/[A-Za-z0-9_-]+")


def video_channel(root: Path, slug: str) -> str | None:
    """The channel a video belongs to, or None when there is no such video."""

    try:
        return _channel_of(root, find_video(root, slug))
    except Exception:
        return None


def partner_may(root: Path, mine: list[str], method: str, path: str) -> bool:
    """May this partner (their channels: `mine`) open this path? The body's channel is checked apart."""

    if path in (PARTNER_GET if method == "GET" else PARTNER_POST):
        return True
    if match := re.fullmatch(r"/api/mychannel/([^/]+)(?:/handle)?", path):     # «Mi canal» of one of their channels
        return urllib.parse.unquote(match.group(1)) in mine
    if method == "GET" and re.fullmatch(r"/api/apertura/[0-9a-f]{12}", path):
        return True
    for pattern in (PARTNER_VIDEO_GET if method == "GET" else PARTNER_VIDEO_POST):
        if match := re.fullmatch(pattern, path):
            return video_channel(root, urllib.parse.unquote(match.group(1))) in mine
    return False


def _bot_name(token: str) -> str:
    """The bot's @username (getMe), for the t.me link a partner opens to connect their Telegram."""

    import requests

    try:
        return str((requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json().get("result") or {})
                   .get("username") or "")
    except Exception:
        return ""


def channels_health(root: Path, mine: list[str] | None = None) -> dict[str, Any]:
    """«Canales»: each channel at a glance — its cushion of finished videos, the next two weeks of its calendar, what
    is in the works or failed, and how its uploads did (YouTube views of the videos it published each of the last 8
    weeks: the views of those videos so far, not the channel's views that week)."""

    from datetime import date, timedelta

    from . import agenda, estadisticas

    listed = agenda.videos(root)
    cfg = agenda.settings(root)
    plan = agenda.plan(root, days=14, listed=listed)
    reserve = agenda.reserve(root, listed)
    try:
        stats = estadisticas.report(root)
    except Exception:                                   # no YouTube data yet: the rest still says a lot
        stats = {"videos": [], "channels": []}
    kinds = channel_kinds(root)
    today = date.today()
    weeks = [today - timedelta(days=7 * (8 - i)) for i in range(1, 9)]      # the start of each of the last 8 weeks
    names = [c for c in channels(root) if mine is None or c in mine]
    out = []
    for name in names:
        rule = cfg["schedule"].get(name) or {"enabled": False, "days": [], "time": ""}
        mine_videos = [v for v in listed if v["channel"] == name]
        slots = {s["date"]: s for s in plan if s["channel"] == name}
        next14 = []
        for n in range(14):
            day = (today + timedelta(days=n)).isoformat()
            s = slots.get(day)
            kind = None if not s else "late" if s["late"] else "ok" if s["ok"] else "gap" if s["gap"] else "work"
            next14.append({"date": day, "kind": kind, "video": s["video"]["slug"] if s and s.get("video") else None})
        views = [0] * 8
        for row in stats["videos"]:
            if row.get("channel") != name or not row.get("youtube") or not row.get("publishedDay"):
                continue
            try:
                published = date.fromisoformat(str(row["publishedDay"])[:10])
            except ValueError:
                continue
            for i, start in enumerate(weeks):
                if start <= published < start + timedelta(days=7):
                    views[i] += int(row["youtube"].get("views") or 0)
        before, after = sum(views[:4]), sum(views[4:])
        c = next((x for x in stats["channels"] if x.get("channel") == name), {})
        out.append({
            "channel": name, "kind": kinds.get(name, "metraje"), "publishes": bool(rule.get("enabled")),
            "days": rule.get("days") or [], "time": rule.get("time") or "",
            "reserve": reserve.get(name), "buffer": cfg["buffer"],
            "making": sum(1 for v in mine_videos if v["status"] == "haciendo"),
            "queued": sum(1 for v in mine_videos if v["status"] == "en cola"),
            "missing": sum(1 for v in mine_videos if v["status"] in ("falta guion", "falta voz")),
            "errors": sum(1 for v in mine_videos if v["status"] == "error"),
            "next": next14, "gaps": sum(1 for d in next14 if d["kind"] in ("gap", "late")),
            "late": sum(1 for d in next14 if d["kind"] == "late"),
            "views": c.get("views") or 0, "median": c.get("median"), "published": c.get("published") or 0,
            "weeks": views, "trend": round((after - before) / before, 2) if before else None,
        })
    return {"channels": out, "weekdays": agenda.WEEKDAYS, "buffer": cfg["buffer"], "today": today.isoformat()}


def partner_agenda(root: Path, mine: list[str]) -> dict[str, Any]:
    """The publishing calendar of their channels only (days, slots, their videos, their ideas)."""

    from . import agenda

    listed = [v for v in agenda.videos(root) if v.get("channel") in mine]
    cfg = agenda.settings(root)
    cfg = {**cfg, "schedule": {c: r for c, r in cfg["schedule"].items() if c in mine},
           "assigned": {k: v for k, v in cfg["assigned"].items() if video_channel(root, k) in mine},
           "ideas": [i for i in cfg["ideas"] if i.get("channel") in mine]}
    return {"settings": cfg, "weekdays": agenda.WEEKDAYS,
            "plan": [s for s in agenda.plan(root, days=28, listed=listed) if s.get("channel") in mine],
            "reserve": {c: n for c, n in agenda.reserve(root, listed).items() if c in mine}, "videos": listed}


def partner_board(root: Path, mine: list[str]) -> dict[str, Any]:
    from . import agenda

    columns = {k: [x for x in items if x.get("channel") in mine] for k, items in agenda.board(root).items()}
    return {"columns": columns, "channels": [c for c in agenda.channels(root) if c in mine],
            "kinds": {k: v for k, v in channel_kinds(root).items() if k in mine}}


def partner_radar(root: Path, mine: list[str]) -> dict[str, Any]:
    """The radar of their channels: their competitors' videos that work, the day's news of their channels, their saved
    ideas. Not the server-wide discoveries (new niches, small rising channels, measured gaps): those are yours."""

    state = radar_state(root)
    latest = state.get("latest") or None
    if latest:
        latest = {**latest, "channels": {k: v for k, v in (latest.get("channels") or {}).items() if k in mine},
                  "rising": [], "gaps": [], "niches": []}
    news = state.get("news") or None
    if news:
        news = {**news, "channels": {k: v for k, v in (news.get("channels") or {}).items() if k in mine},
                "comebacks": {k: v for k, v in (news.get("comebacks") or {}).items() if k in mine}, "errors": []}
    return {**state, "latest": latest, "niches": [], "gaps": [], "news": news, "channels": mine,
            "saved": [i for i in state.get("saved") or [] if i.get("channel") in mine], "partner": True}


def partner_idea_is_theirs(root: Path, mine: list[str], idea_id: str) -> bool:
    from . import agenda, niche_ideas

    found = [i for i in [*agenda.settings(root)["ideas"], *niche_ideas.saved(root)] if i.get("id") == idea_id]
    return bool(found) and all((i.get("channel") or "") in mine for i in found)     # every idea a delete would take


def partner_overview(root: Path, name: str, mine: list[str]) -> dict[str, Any]:
    """Inicio and the video lists for a partner: their channels' videos only, nothing of the server's or the others'."""

    from . import budget

    data = overview(root)
    videos = [v for v in data["videos"] if v.get("channel") in mine]
    today = datetime.now(timezone.utc).date().isoformat()
    spent = 0.0
    for v in videos:
        try:
            entries = json.loads((root / "work" / v["slug"] / "costs.json").read_text("utf-8")).get("entries") or []
        except (OSError, ValueError):
            continue
        spent += sum(float(e.get("usd") or 0) for e in entries if str(e.get("at", "")).startswith(today))
    service = data["service"]
    return {"service": {"watching": service["watching"], "paused": service["paused"], "queueRunning": service["queueRunning"],
                        "youtubeBlocked": service["youtubeBlocked"], "lastBeat": None, "code": None},
            "budget": {"today": round(spent, 3), "limit": 0, "proxyGbToday": None, "proxyGbLimit": 0},
            "videos": videos, "channels": [c for c in data["channels"] if c in mine],
            "channelKinds": {k: v for k, v in data["channelKinds"].items() if k in mine},
            "formats": data["formats"], "youtube": None, "partner": name}


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

        def _who(self) -> str | None:
            """None: nobody logged in; "" (usuarios.ADMIN): you; a name: that partner."""

            if self._local() and not password:
                return usuarios.ADMIN
            cookie = self.headers.get("Cookie") or ""
            match = re.search(r"(?:^|;\s*)studio=([^;]+)", cookie)
            if not password or not match:
                return None
            if valid(match.group(1)):
                return usuarios.ADMIN
            return usuarios.check(root, secret, match.group(1))

        def _authorised(self) -> bool:
            return self._who() is not None

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

        def _static(self, name: str, forever: bool = False) -> None:
            """A file of the page: 304 when the browser already has it, gzip when it takes it."""

            found = static_file(name)
            if not found:
                return self._fail(404, "No existe")
            body, packed, tag, kind, modified = found
            zipped = "gzip" in (self.headers.get("Accept-Encoding") or "")
            etag = f'"{tag}{"-gz" if zipped else ""}"'
            headers = {"ETag": etag, "Last-Modified": formatdate(modified, usegmt=True), "Vary": "Accept-Encoding",
                       "Cache-Control": "public, max-age=31536000, immutable" if forever else "no-cache"}
            # ETag first; Last-Modified too, because Chromium revalidates an HTTP/1.0 answer (this server's) only by date
            asked_tag, asked_date = self.headers.get("If-None-Match"), self.headers.get("If-Modified-Since")
            try:
                same_date = not asked_tag and bool(asked_date) and int(modified) <= parsedate_to_datetime(asked_date).timestamp()
            except (TypeError, ValueError):
                same_date = False
            if (asked_tag and etag in asked_tag) or same_date:
                self.send_response(304)
                for k, v in headers.items():
                    self.send_header(k, v)
                return self.end_headers()
            if zipped:
                headers["Content-Encoding"] = "gzip"
            self._send(200, packed if zipped else body, kind, headers)

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
                return self._static("index.html")
            if path.startswith("/static/"):              # css and js: kept for good when asked with the current ?v=
                asked = urllib.parse.parse_qs(url.query).get("v", [""])[0]
                return self._static(urllib.parse.unquote(path[8:]), forever=asked == static_version())
            if path == "/api/session":
                who = self._who()
                return self._ok({"authorised": who is not None, "needsPassword": bool(password) or not self._local(),
                                 "partner": who or None, "channels": usuarios.channels_of(root, who) if who else None})
            who = self._who()
            if who is None:
                return self._fail(401, "Inicia sesión")
            if who:                                        # a partner: their channels, a closed list of pages
                mine = usuarios.channels_of(root, who)
                if not partner_may(root, mine, "GET", path):
                    return self._fail(403, "No disponible")
                try:
                    if path == "/api/overview":
                        return self._ok(partner_overview(root, who, mine))
                    if path == "/api/gasto":
                        from . import gasto

                        months = [{**m, "hours": None, "people": [p for p in m["people"] if p["who"] == who]}
                                  for m in gasto.invoices(root)]
                        return self._ok({**gasto.report(root, channels=set(mine)), "allChannels": mine, "partner": who,
                                         "invoices": months})
                    if path == "/api/search":
                        found = search_videos(root, (urllib.parse.parse_qs(url.query).get("q") or [""])[0][:20000])
                        return self._ok({**found, "results": [r for r in found["results"] if r.get("channel") in mine], "ideas": []})
                    if path == "/api/agenda":
                        return self._ok(partner_agenda(root, mine))
                    if path == "/api/canales":
                        return self._ok(cached(f"canales:{root}:{','.join(mine)}", 30, lambda: channels_health(root, mine)))
                    if path == "/api/radar":
                        return self._ok(partner_radar(root, mine))
                    if path == "/api/spending":
                        return self._ok(spending(root, owner=who))
                    if path == "/api/stats":               # «Estadísticas» of their videos only
                        from . import estadisticas

                        full = estadisticas.report(root, bool(urllib.parse.parse_qs(url.query).get("refresh")))
                        rows = [r for r in full["videos"] if r.get("channel") in mine]
                        chans = [c for c in full["channels"] if c.get("channel") in mine]
                        totals = {k: (round(sum(c.get(k) or 0 for c in chans), 2) if k == "usd" else sum(c.get(k) or 0 for c in chans))
                                  for k in ("views", "watchHours", "published", "made", "usd")}
                        return self._ok({**full, "videos": rows, "channels": chans, "totals": totals})
                    if path == "/api/board":
                        return self._ok(partner_board(root, mine))
                    if path == "/api/scripts":
                        from . import organizar

                        days = int((urllib.parse.parse_qs(url.query).get("days") or ["14"])[0])
                        rows = [{**e, "ideas": [i for i in e.get("ideas") or [] if i.get("channel") in mine]}
                                for e in organizar.scripts_needed(root, days) if e.get("channel") in mine]
                        return self._ok({"channels": rows, "days": days})
                    if path == "/api/cuenta":              # «Mi cuenta»: their caps, today, Telegram
                        from . import budget

                        return self._ok({"name": who, "channels": mine, "telegram": bool(usuarios.telegram_of(root, who)),
                                         "limits": usuarios.limits_of(root, who), "spentToday": budget.spent_today(root, who),
                                         "proxyGbToday": budget.proxy_gb_today(root, who)})
                    if path == "/api/voices":
                        from . import tts

                        key = RunContext.create("_web", root=root).env("GENAIPRO_API_KEY", required=False)
                        return self._ok({"voices": {c: v for c, v in tts.voices(root).items() if c in mine}, "channels": mine,
                                         "models": list(tts.MODELS), "defaults": tts.DEFAULTS, "hasKey": bool(key),
                                         "dubbing": {c: tts.dubbing_for(root, c) for c in mine},
                                         "dubLanguages": list(tts.DUB_LANGUAGES),
                                         "speaks": {c: tts.voice_for(root, c) is not None for c in mine},
                                         "dubOptions": {c: _dub_options(root, c) for c, k in channel_kinds(root).items()
                                                        if k == "simulacion" and c in mine}, "partner": who})
                    if path == "/api/upload/dates":
                        from . import organizar

                        return self._ok({k: v for k, v in organizar.upload_dates(root).items() if video_channel(root, k) in mine})
                    if path == "/api/upload":
                        from . import organizar

                        return self._ok({"videos": [v for v in organizar.to_upload(root) if video_channel(root, v["slug"]) in mine],
                                         "compilations": [], "compilationJob": None})
                except Exception as error:
                    return self._fail(500, f"{type(error).__name__}: {error}")
            try:
                if path == "/api/overview":
                    return self._ok(overview(root))
                if path == "/api/users":                   # Ajustes → «Personas»: names and channels, no hashes
                    return self._ok({"users": usuarios.listing(root)})
                if path == "/api/stats":                   # «Estadísticas» (pipeline/estadisticas.py)
                    from . import estadisticas

                    return self._ok(estadisticas.report(root, bool(urllib.parse.parse_qs(url.query).get("refresh"))))
                if path == "/api/spending":
                    return self._ok(spending(root))
                if path == "/api/factura.csv":             # one person's month (a partner: only their own)
                    from . import gasto

                    query = urllib.parse.parse_qs(url.query)
                    month, person = (query.get("month") or [""])[0], (who or (query.get("who") or [""])[0])
                    found = next((m for m in gasto.invoices(root, 12) if m["month"] == month), None)
                    if found is None:
                        return self._fail(404, "Mes sin datos")
                    name = f"factura-{person or 'yo'}-{month}.csv"
                    return self._send(200, ("\ufeff" + gasto.invoice_csv(found, person)).encode(), "text/csv; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="{name}"'})
                if path == "/api/gasto":                   # «Gasto de API» (pipeline/gasto.py)
                    from . import gasto

                    from .budget import settings as saved

                    return self._ok({**gasto.report(root), "allChannels": channels(root), "invoices": gasto.invoices(root),
                                     "serverUsdMonth": float(saved(root).get("server_usd_month") or 0)})
                if path == "/api/doctor":                  # python main.py --doctor, every 10 min at most
                    from . import chequeo

                    return self._ok(chequeo.cached(root, 0 if urllib.parse.parse_qs(url.query).get("refresh") else 600))
                if path == "/api/servidor":                # «Estado del servidor» (pipeline/servidor.py)
                    from . import copia, servidor

                    status = cached(f"servidor:{root}", 5, lambda: servidor.status(root))    # every tab asks every 15 s
                    return self._ok({**status, "backup": copia.info(root)})
                if path == "/api/proxy":                   # the paid proxy, last days: success, GB, $ per finished video
                    days = float((urllib.parse.parse_qs(url.query).get("days") or ["7"])[0])
                    return self._ok(cached(f"proxy:{root}:{days}", 120, lambda: proxy_report(root, days)))
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
                if path == "/api/canales":                 # «Canales»: the health of every channel, 30 s in memory
                    return self._ok(cached(f"canales:{root}", 30, lambda: channels_health(root)))
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
                                     "dubLanguages": list(tts.DUB_LANGUAGES),
                                     # who speaks a new video with no mp3: its own voice or its base channel's
                                     "speaks": {c: tts.voice_for(root, c) is not None for c in channels(root)},
                                     # a simulation channel's dubbing: each language and the GenAIPro voice it would use
                                     "dubOptions": {c: _dub_options(root, c) for c, k in channel_kinds(root).items() if k == "simulacion"}})
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

                    return self._ok({"columns": agenda.board(root), "channels": agenda.channels(root), "kinds": channel_kinds(root)})
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
                if match := re.fullmatch(r"/api/video/([^/]+)/repeticion", path):    # title, thumbnail and footage vs the channel
                    from . import repeticion

                    return self._ok(repeticion.check(root, urllib.parse.unquote(match.group(1))))
                if match := re.fullmatch(r"/api/video/([^/]+)/porque", path):        # views against the channel's normal
                    from . import porque

                    slug = urllib.parse.unquote(match.group(1))
                    curves = porque._read(root / porque.CURVES) or {}
                    return self._ok({"curve": porque.compare(curves, slug) if slug in curves else None,
                                     "report": porque.saved(root, slug)})
                if path == "/api/piloto":                 # «Piloto automático»: switches, candidates, what it made
                    from . import autopilot

                    data = autopilot.overview(root)
                    for c in data["channels"]:
                        c["job"] = job_state(root, f"piloto-{c['channel']}")
                    return self._ok(data)
                if match := re.fullmatch(r"/api/apertura/([0-9a-f]{12})", path):   # the opening clip search
                    token = match.group(1)
                    found = root / "out" / "_tareas" / f"apertura-{token}.resultado.json"
                    return self._ok({"job": job_state(root, f"apertura-{token}"),
                                     "result": json.loads(found.read_text("utf-8")) if found.is_file() else None})
                if match := re.fullmatch(r"/api/video/([^/]+)/capcut", path):       # the CapCut project
                    slug = urllib.parse.unquote(match.group(1))
                    archive = root / "out" / slug / f"{slug}-capcut.zip"
                    return self._ok({"job": job_state(root, f"capcut-{slug}"), "zip": archive.name if archive.is_file() else None,
                                     "mb": round(archive.stat().st_size / 1e6) if archive.is_file() else None})
                if match := re.fullmatch(r"/api/video/([^/]+)/exportar", path):     # the Premiere / DaVinci project
                    slug = urllib.parse.unquote(match.group(1))
                    archive = root / "out" / slug / f"{slug}-premiere.zip"
                    return self._ok({"job": job_state(root, f"exportar-{slug}"), "zip": archive.name if archive.is_file() else None,
                                     "mb": round(archive.stat().st_size / 1e6) if archive.is_file() else None})
                if match := re.fullmatch(r"/api/video/([^/]+)/pilot", path):
                    from . import piloto

                    slug = urllib.parse.unquote(match.group(1))
                    registry = piloto._registry(root)
                    return self._ok({"pilot": registry.get(slug), "others": sorted(set(registry) - {slug}),
                                     "references": [v for v in piloto.finished(root) if v != slug],
                                     "report": _json(root / "out" / slug / "piloto.json")})
                if path == "/api/tiempos":                 # where the hours go, stage by stage (pipeline/tiempos.py)
                    from . import tiempos

                    return self._ok({"markdown": tiempos.markdown(tiempos.report(root))})
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
                given = str(body.get("password") or "")
                partner = usuarios.find(root, given) if password and given else None
                if (password and hmac.compare_digest(given.encode(), password.encode())) or partner:
                    secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                    value = usuarios.token(root, secret, partner) if partner else token()
                    return self._send(200, b'{"ok": true}', headers={
                        "Set-Cookie": f"studio={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000{secure}"})
                failures.append(time.time())
                time.sleep(1.5)                                  # slows down guessing
                return self._fail(403, "Contraseña incorrecta")
            if path == "/api/logout":                      # anyone, even with an old cookie: it goes
                return self._send(200, b'{"ok": true}', headers={
                    "Set-Cookie": "studio=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            who = self._who()
            if who is None:
                return self._fail(401, "Inicia sesión")
            if self.headers.get("Origin") and urllib.parse.urlparse(self.headers["Origin"]).netloc != self.headers.get("Host"):
                return self._fail(403, "Origen no permitido")
            mine = usuarios.channels_of(root, who) if who else []
            if path == "/api/password":                    # a partner changes their own password
                if not who:
                    return self._fail(400, "Tu contraseña es WEB_PASSWORD, en el .env del servidor")
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if usuarios.find(root, str(body.get("current") or "")) != who:
                        time.sleep(1.5)
                        return self._fail(403, "La contraseña actual no es esa")
                    usuarios.save(root, who, usuarios.channels_of(root, who), str(body.get("new") or ""), password)
                except ValueError as error:
                    return self._fail(400, str(error))
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                return self._send(200, b'{"ok": true}', headers={    # the new password closed the old session: a new one
                    "Set-Cookie": f"studio={usuarios.token(root, secret, who)}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000{secure}"})
            if who and not partner_may(root, mine, "POST", path):
                return self._fail(403, "No disponible")
            if path == "/api/users":                       # partners, from Ajustes: only you
                if who:
                    return self._fail(403, "No disponible")
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if body.get("remove"):
                        return self._ok(usuarios.remove(root, str(body["remove"])))
                    unknown = [c for c in body.get("channels") or [] if c not in channels(root)]
                    if unknown:
                        raise ValueError(f"No existe el canal {unknown[0]}")
                    saved = usuarios.save(root, str(body.get("name") or ""), list(body.get("channels") or []),
                                          str(body.get("password") or ""), password)
                    if isinstance(body.get("limits"), dict):       # their own daily caps: API $ and proxy GB
                        usuarios.set_limits(root, str(body.get("name") or "").strip().lower(), body["limits"])
                        saved = {"users": usuarios.listing(root)}
                    return self._ok(saved)
                except ValueError as error:
                    return self._fail(400, str(error))
            try:
                if path == "/api/apertura/subir":          # your own video for the opening: streamed to disk
                    ticket = secrets.token_hex(6)
                    folder = root / "out" / "_tareas"
                    folder.mkdir(parents=True, exist_ok=True)
                    for old in folder.glob("apertura-*.mp4"):          # uploads never used, after a day
                        if time.time() - old.stat().st_mtime > 86400:
                            old.unlink(missing_ok=True)
                    with (folder / f"apertura-{ticket}.mp4").open("wb") as f:
                        left = length
                        while left > 0:
                            chunk = self.rfile.read(min(left, 1 << 20))
                            if not chunk:
                                break
                            f.write(chunk)
                            left -= len(chunk)
                    return self._ok({"file": ticket})
                if match := re.fullmatch(r"/api/video/([^/]+)/voz", path):
                    return self._ok(save_voice(root, urllib.parse.unquote(match.group(1)), self.rfile.read(length)))
                body = json.loads(self.rfile.read(length) or b"{}")
                if who:                                    # a partner: the channel named in the body is theirs too
                    if path in PARTNER_WITH_CHANNEL and str(body.get("channel") or "") not in mine:
                        return self._fail(403, "Ese canal no es tuyo")
                    if re.fullmatch(r"/api/video/[^/]+/channel", path) and str(body.get("channel") or "") not in mine:
                        return self._fail(403, "Ese canal no es tuyo")
                    if path == "/api/agenda":              # their channels' days and hours, pinning their videos
                        if any(k in body for k in ("lead_hours", "buffer", "morning_hour")):
                            return self._fail(403, "Eso es de todo el estudio")
                        if body.get("channel") and str(body["channel"]) not in mine:
                            return self._fail(403, "Ese canal no es tuyo")
                        if body.get("assign") and video_channel(root, str(body["assign"])) not in mine:
                            return self._fail(403, "Ese vídeo no es tuyo")
                        from . import agenda

                        agenda.update(root, body)
                        return self._ok(partner_agenda(root, mine)["settings"])
                    if path == "/api/scripts/similar" and video_channel(root, str(body.get("slug") or "")) not in mine:
                        return self._fail(403, "Ese vídeo no es tuyo")
                    if path == "/api/ideas/save":          # their saved ideas: only to their channels
                        from . import niche_ideas

                        if body.get("remove"):
                            if not partner_idea_is_theirs(root, mine, str(body["remove"])):
                                return self._fail(403, "Esa idea no es tuya")
                            niche_ideas.unsave(root, str(body["remove"]))
                        elif str(body.get("channel") or "") not in mine:
                            return self._fail(403, "Elige uno de tus canales")
                        else:
                            idea_id = str((body.get("idea") or {}).get("id") or "")
                            if any(i.get("id") == idea_id and i.get("channel") not in mine for i in niche_ideas.saved(root)):
                                return self._fail(403, "Esa idea ya la guardó otra persona")   # saving replaces by id
                            niche_ideas.save(root, body.get("idea") or {}, str(body["channel"]))
                        return self._ok([i for i in niche_ideas.saved(root) if i.get("channel") in mine])
                    if path == "/api/board/idea":
                        if body.get("delete"):
                            if not partner_idea_is_theirs(root, mine, str(body["delete"])):
                                return self._fail(403, "Esa idea no es tuya")
                        elif str(body.get("channel") or "") not in mine:
                            return self._fail(403, "Elige uno de tus canales")
                    if path == "/api/telegram/link":       # a code for «/start <code>» to the bot (bot.py links it)
                        bot_token = RunContext.create("_web", root=root).env("TELEGRAM_BOT_TOKEN", required=False)
                        if not bot_token:
                            raise ValueError("El estudio aún no tiene bot de Telegram: pídeselo a quien lo administra")
                        code = usuarios.link_code(root, who)
                        bot = cached(f"botname:{bot_token[:8]}", 3600, lambda: _bot_name(bot_token))
                        return self._ok({"code": code, "bot": bot, "url": f"https://t.me/{bot}?start={code}" if bot else ""})
                    if path == "/api/telegram/unlink":
                        usuarios.unlink_chat(root, who)
                        return self._ok({"ok": True})
                    if path == "/api/channels":            # their new channel: its look only from one of theirs
                        if str(body.get("base") or "") and str(body["base"]) not in mine:
                            return self._fail(403, "Ese canal no es tuyo")
                        made = create_channel(root, body)
                        usuarios.add_channel(root, who, made["channel"])
                        return self._ok(made)
                    if path == "/api/search":
                        found = search_videos(root, str(body.get("q") or "")[:200000])
                        return self._ok({**found, "results": [r for r in found["results"] if r.get("channel") in mine], "ideas": []})
                if path == "/api/videos":
                    return self._ok(create_video(root, body))
                if path == "/api/copia":                   # «Hacer copia ahora»
                    from . import copia

                    return self._ok({"made": copia.make(root).name, "backup": copia.info(root)})
                if match := re.fullmatch(r"/api/video/([^/]+)/retencion", path):   # {csv}: YouTube Studio's export
                    from . import retencion

                    slug = urllib.parse.unquote(match.group(1))
                    find_video(root, slug)
                    ctx = RunContext.create(slug, root=root)
                    if not (ctx.work_dir / "timeline.json").is_file():
                        raise ValueError("Este vídeo aún no tiene montaje")
                    text = str(body.get("csv") or "")
                    (ctx.out_dir / "retencion.csv").write_text(text, encoding="utf-8")
                    return self._ok(retencion.analyse(ctx, text))
                if match := re.fullmatch(r"/api/video/([^/]+)/doblaje", path):   # {lang, script, title} | {lang, manual}
                    from . import doblaje

                    slug, lang = urllib.parse.unquote(match.group(1)), str(body.get("lang") or "")
                    if lang not in doblaje.NAMES:
                        raise ValueError("Idioma desconocido")
                    if "on" in body:                       # «Doblar a …» / «No doblar a …»
                        return self._ok(doblaje.choose(root, slug, lang, bool(body["on"])))
                    if "manual" in body:
                        return self._ok(doblaje.mark_manual(root, slug, lang, bool(body["manual"])))
                    if body.get("approve"):                # the adapted script checked: the voice can be read
                        return self._ok(doblaje.approve(root, slug, lang))
                    return self._ok(doblaje.set_script(root, slug, lang, str(body.get("script") or ""),
                                                       str(body.get("title") or "")))
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
                if match := re.fullmatch(r"/api/video/([^/]+)/porque", path):        # analyse it again now
                    from . import porque

                    return self._ok({"report": porque.analyse(root, urllib.parse.unquote(match.group(1)))})
                if match := re.fullmatch(r"/api/piloto/([\w-]+)", path):          # {on, perDay}
                    from . import autopilot

                    if match.group(1) not in channels(root):
                        raise ValueError("No existe ese canal")
                    return self._ok(autopilot.configure(root, match.group(1), body.get("on"), body.get("perDay")))
                if match := re.fullmatch(r"/api/piloto/([\w-]+)/(hacer|saltar)", path):   # {id}
                    from . import autopilot

                    channel, video_id = match.group(1), str(body.get("id") or "")
                    if channel not in channels(root) or not re.fullmatch(r"[\w-]{0,20}", video_id):
                        raise ValueError("Canal o vídeo no válido")
                    if match.group(2) == "saltar":
                        return self._ok(autopilot.skip(root, channel, video_id))
                    return self._ok(background(root, f"piloto-{channel}", ["--autopiloto", f"{channel}:{video_id}"]))
                if match := re.fullmatch(r"/api/video/([^/]+)/capcut", path):
                    slug = urllib.parse.unquote(match.group(1))
                    if not (root / "out" / slug / "video-final.mp4").is_file():
                        raise ValueError("Primero tiene que estar el vídeo terminado")
                    (root / "out" / slug / f"{slug}-capcut.zip").unlink(missing_ok=True)
                    return self._ok(background(root, f"capcut-{slug}", ["--capcut", slug]))
                if match := re.fullmatch(r"/api/video/([^/]+)/exportar", path):
                    slug = urllib.parse.unquote(match.group(1))
                    if not (root / "out" / slug / "video-final.mp4").is_file():
                        raise ValueError("Primero tiene que estar el vídeo terminado")
                    (root / "out" / slug / f"{slug}-premiere.zip").unlink(missing_ok=True)
                    return self._ok(background(root, f"exportar-{slug}", ["--exportar", slug]))
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
                if path == "/api/board/temas":             # {channel}: two weeks of topics its worlds can show
                    from . import temas

                    channel = str(body.get("channel") or "")
                    if channel not in channels(root):
                        raise ValueError("Elige un canal de simulación")
                    return self._ok({"added": temas.calendar(root, channel, int(body.get("count") or 10),
                                                             serie=str(body.get("serie") or ""))})
                if path == "/api/board/idea":
                    from . import agenda

                    if body.get("delete"):
                        agenda.remove_idea(root, str(body["delete"]))
                        return self._ok({"ok": True})
                    return self._ok(agenda.add_idea(root, str(body.get("title") or ""), str(body.get("channel") or ""),
                                                    str(body.get("note") or ""), str(body.get("date") or "")))
                if path == "/api/channels":                # a new channel profile
                    return self._ok(create_channel(root, body))
                if path == "/api/apertura":                # {channel, title, script, ask, url|file, start, end, language}
                    ticket = str(body.get("file") or "") if re.fullmatch(r"[0-9a-f]{12}", str(body.get("file") or "")) \
                        else secrets.token_hex(6)          # an uploaded video keeps its ticket
                    folder = root / "out" / "_tareas"
                    folder.mkdir(parents=True, exist_ok=True)
                    keep = ("channel", "title", "script", "ask", "url", "start", "end", "language", "subtitles")
                    request = {k: body.get(k) for k in keep}
                    if body.get("file"):
                        request["file"] = str(folder / f"apertura-{ticket}.mp4")
                    (folder / f"apertura-{ticket}.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
                    (folder / f"apertura-{ticket}.resultado.json").unlink(missing_ok=True)
                    background(root, f"apertura-{ticket}", ["--apertura", str(folder / f"apertura-{ticket}.json")])
                    return self._ok({"token": ticket})
                if path == "/api/hook":                    # {title, script, channel}: before recording
                    from . import hook

                    channel = str(body.get("channel") or "")
                    ctx = RunContext.create("_gancho", root=root, channel=channel if channel in channels(root) else None)
                    title = str(body.get("title") or "").strip()
                    if not title:
                        raise ValueError("Pon el título que vas a usar: el gancho se mide contra él")
                    return self._ok(hook.review(ctx, title, str(body.get("script") or "")))
                if path == "/api/scenes":                  # {script, channel}: the lines no simulated world can show
                    from . import simulacion

                    channel = str(body.get("channel") or "")
                    ctx = RunContext.create("_escenas", root=root, channel=channel if channel in channels(root) else None)
                    if not simulacion.active(ctx):
                        raise ValueError("Ese canal no es de simulación")
                    return self._ok(simulacion.review_script(ctx, str(body.get("script") or "")))
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
                if match := re.fullmatch(r"/api/mychannel/([^/]+)/handle", path):    # {handle}: @TheirChannel
                    channel = urllib.parse.unquote(match.group(1))
                    if channel not in channels(root):
                        return self._fail(404, "No existe")
                    settings(root, {"my_channels": {channel: str(body.get("handle") or "").strip()}})
                    return self._ok({"ok": True})
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
