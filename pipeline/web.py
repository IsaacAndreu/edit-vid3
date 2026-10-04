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
import subprocess
import sys
import time
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


def video_summary(root: Path, folder: Path, watch_state: dict[str, Any]) -> dict[str, Any]:
    slug = folder.name
    out, work = root / "out" / slug, root / "work" / slug
    current = _json(work / "current.json")
    done = (out / "video-final.mp4").is_file()
    stages = sorted((work / ".stages").glob("*.json")) if (work / ".stages").is_dir() else []
    costs = _json(work / "costs.json") or {}
    failed = watch_state.get(slug)
    diag = _json(work / "diag.json") or {}
    status = ("hecho" if done else "error" if failed or diag.get("error") and not current else
              "haciendo" if current else "en cola" if (folder / "guion.txt").is_file() and (folder / "voz.mp3").is_file()
              else "incompleto")
    return {
        "slug": slug, "channel": _channel_of(root, folder), "status": status,
        "archived": any(part.startswith("_") for part in folder.relative_to(root / "materiales").parts),
        "stage": current, "stagesDone": len(stages), "costUsd": round(float(costs.get("totalUsd") or 0), 2),
        "error": None if done else diag.get("error") or ((failed or {}).get("status") and "falló"),
        "updated": max([p.stat().st_mtime for p in [folder, *(out.glob("*") if out.is_dir() else [])]]),
        "hasVideo": done, "minutes": round(sum(float((_json(p) or {}).get("seconds") or 0) for p in stages) / 60),
    }


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
    rows = [r for p in (root / "work").glob("*/youtube_downloads.jsonl") for r in ytstats.read(p, since)]
    queue_running = (root / "work" / ".cola.lock").is_file()
    return {
        "service": {"watching": alive, "paused": (root / "out" / "_pausa").is_file(), "queueRunning": queue_running,
                    "lastBeat": beat.read_text().strip() if beat.is_file() else None},
        "budget": {"today": budget.spent_today(root), "limit": budget.limit(root, config)},
        "videos": videos, "channels": channels(root), "formats": formats(root),
        "youtube": ytstats.summary(rows) if rows else None,
    }


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
        "graphics": read("graficos.md"),
        "thumbnails": [f for f in files if f.startswith("miniaturas/") or re.match(r"miniatura", f)],
        "shorts": [f for f in files if f.startswith("shorts/") and f.endswith(".mp4")],
        "files": files,
        "script": (folder / "guion.txt").read_text("utf-8", errors="replace")[:20000] if (folder / "guion.txt").is_file() else "",
    }


def create_video(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    name = str(body.get("name") or "").strip()
    channel = str(body.get("channel") or "").strip()
    if not NAME.match(name):
        raise ValueError("El nombre solo puede llevar letras, números, puntos, guiones y _ (sin espacios)")
    if channel and channel not in channels(root):
        raise ValueError(f"No existe el canal {channel}")
    if any(f.name == name for f in video_folders(root)):
        raise ValueError(f"Ya hay un vídeo llamado {name}")
    script = str(body.get("script") or "").strip()
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


def retry(root: Path, slug: str) -> dict[str, Any]:
    path = root / "out" / "_vigilar.json"
    state = _json(path) or {}
    state.pop(slug, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return {"ok": True}


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
        if isinstance(body.get("my_channels"), dict):
            current["my_channels"] = {str(k): str(v).strip() for k, v in body["my_channels"].items()
                                      if k in channels(root) and str(v).strip()}
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
    if (root / "work" / slug / "current.json").is_file():
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
    return {"latest": radar.latest(root), "niches": niches, "job": job_state(root, "radar"),
            "saved": niche_ideas.saved(root), "channels": channels(root)}


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
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
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
                if path == "/api/spending":
                    return self._ok(spending(root))
                if path == "/api/settings":
                    return self._ok(settings(root))
                if path == "/api/notify":
                    from . import notify

                    return self._ok(notify.status(RunContext.create("_web", root=root)))
                if match := re.fullmatch(r"/api/video/([^/]+)", path):
                    return self._ok(video_detail(root, urllib.parse.unquote(match.group(1))))
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
                if match := re.fullmatch(r"/api/video/([^/]+)/(retry|archive)", path):
                    action = retry if match.group(2) == "retry" else archive
                    return self._ok(action(root, urllib.parse.unquote(match.group(1))))
                if path == "/api/settings":
                    return self._ok(settings(root, body))
                if path == "/api/queue":
                    return self._ok(start_queue(root))
                if path == "/api/notify":                  # {token?, studio_url?}: save, find the chat, send a test
                    from . import notify

                    return self._ok(notify.setup(RunContext.create("_web", root=root), str(body.get("token") or ""),
                                                 str(body.get("studio_url") or "")))
                if match := re.fullmatch(r"/api/review/([^/]+)/([A-Za-z0-9_-]+)", path):
                    from . import feedback

                    return self._ok(feedback.label(root, urllib.parse.unquote(match.group(1)), match.group(2),
                                                   body.get("verdict"), str(body.get("reason") or "")))
                if match := re.fullmatch(r"/api/video/([^/]+)/fix", path):
                    return self._ok(fix_video(root, urllib.parse.unquote(match.group(1))))
                if path == "/api/radar":
                    return self._ok(background(root, "radar", ["--radar"]))
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


def serve(port: int = 8080, host: str = "127.0.0.1", root: Path = PROJECT_ROOT, open_browser: bool = True) -> None:
    ctx = RunContext.create("_web", root=root)
    password = ctx.env("WEB_PASSWORD", required=False) or ""
    if host not in ("127.0.0.1", "localhost", "::1") and not password:
        raise SystemExit("Para abrir el estudio fuera de este equipo pon WEB_PASSWORD=… en .env")
    server = ThreadingHTTPServer((host, port), make_handler(root, password))
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
