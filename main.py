from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Harmless library chatter that buries the progress lines: OpenCV 5's "Targets are not supported by
# the new graph engine" and Hugging Face's "unauthenticated requests" (only a rate limit, never reached).
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from pipeline.config import PROJECT_ROOT, ConfigError
from pipeline.context import RunContext
from pipeline.qa import QABlocked
from pipeline.runner import STAGE_NAMES, StageNotImplemented, run_stages

QUEUE_LOCK = "work/.cola.lock"
QUEUE_REPORT = "out/_cola.md"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera un vídeo documental a partir de materiales/<slug>/{guion.txt, voz.mp3} (titulo.txt opcional)."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--slug", help="Carpeta dentro de materiales/, p. ej. Video1.")
    target.add_argument(
        "--all",
        action="store_true",
        help="Cola: procesa uno tras otro todos los vídeos de materiales/ que aún no tienen out/<slug>/video-final.mp4. "
        "Si uno falla, lo apunta y sigue con el siguiente. Resumen en out/_cola.md.",
    )
    target.add_argument("--ideas", action="store_true",
                        help="3 ideas de vídeo basadas en los outliers de la competencia y tus mejores vídeos "
                             "(out/_ideas/<fecha>.md, y por email/Telegram si está configurado).")
    target.add_argument("--check", metavar="SLUG",
                        help="Antes de grabar la voz: verifica los datos del guion de materiales/SLUG (→ out/SLUG/verificacion.md) "
                             "y si su arranque cumple lo que promete el título (→ out/SLUG/gancho.md).")
    target.add_argument("--shorts", metavar="SLUG",
                        help="Hace 3 Shorts verticales de un vídeo ya terminado → out/SLUG/shorts/.")
    target.add_argument("--dub", metavar="SLUG:IDIOMA",
                        help="Versión doblada reutilizando el vídeo hecho, p. ej. CarlosYulo:en con la voz en "
                             "materiales/CarlosYulo/voz-en.mp3 (+ guion-en.txt opcional) → out/CarlosYulo-en/.")
    target.add_argument("--editor", metavar="SLUG",
                        help="Editor antes del render: ver el montaje, cambiar planos, gráficos y textos, y renderizar "
                             "(http://127.0.0.1:8766). Mejor con el vídeo lanzado antes con --review.")
    target.add_argument("--panel", action="store_true",
                        help="Panel web local (outliers, análisis de canales, guardados, ideas) en http://127.0.0.1:8765.")
    parser.add_argument(
        "--force",
        action="append",
        default=[],
        metavar="ETAPA",
        help=f"Vuelve a ejecutar una etapa aunque esté al día (repetible, o 'all'). Etapas: {', '.join(STAGE_NAMES)}.",
    )
    parser.add_argument("--until", choices=STAGE_NAMES, help="Detiene el pipeline después de esta etapa.")
    parser.add_argument("--review", action="store_true", help="Se detiene tras la QA para revisar antes del render.")
    target.add_argument("--probar-youtube", action="store_true",
                        help="Comprueba en 1 minuto por qué YouTube descarga lento en esta máquina y qué hacer.")
    target.add_argument("--formatos", action="store_true",
                        help="Lista de formatos de vídeo (formatos/*.yaml): se eligen con format: en la config.yaml.")
    target.add_argument("--semana", metavar="CANAL",
                        help="Plan de la semana: 1 idea por cada serie del canal (canales/<canal>.yaml → series:), "
                             "en out/_ideas/<canal>/semana-<fecha>.md.")
    target.add_argument("--series", metavar="CANAL",
                        help="Qué serie del canal funciona mejor: visitas de tus vídeos publicados agrupadas por serie "
                             "(out/_series/<canal>-<fecha>.md).")
    parser.add_argument("--serie", help="Con --ideas: ideas de una sola serie del canal (p. ej. estafas).")
    parser.add_argument("--canal", help="Con --ideas / --panel: perfil de canal (canales/<canal>.yaml), p. ej. robots.")
    parser.add_argument("--limit", type=int, default=0, help="Con --all: como mucho N vídeos en esta ejecución.")
    target.add_argument("--vigilar", nargs="?", const=5.0, type=float, metavar="MIN",
                        help="Servidor: hace los vídeos de materiales/ en cuanto aparecen, mirando cada MIN minutos "
                             "(5); no repite en bucle uno que falló; se actualiza con git pull.")
    target.add_argument("--youtube-stats", nargs="?", const=7.0, type=float, metavar="DÍAS",
                        help="Cómo respondió YouTube en los últimos DÍAS (7 por defecto): peticiones, 403, bloqueos, "
                             "velocidad, con o sin cuenta → out/_youtube_stats.md.")
    target.add_argument("--web", nargs="?", const=8080, type=int, metavar="PUERTO",
                        help="Estudio web (sin comandos): subir guion y voz, ver cómo va cada vídeo, descargar, revisar "
                             "errores, competencia y tu canal → http://127.0.0.1:8080.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Con --web: dónde escucha (127.0.0.1 = solo este equipo; en la VPS lo publica Caddy).")
    target.add_argument("--bot", action="store_true",
                        help="Bot de Telegram: /estado, /gasto, /videos, /errores… y un parte cada hora (TELEGRAM_* en .env).")
    target.add_argument("--radar", action="store_true",
                        help="Radar de competencia de hoy: lo mejor de tus nichos y nichos nuevos medidos → out/_radar/.")
    target.add_argument("--mi-canal", metavar="CANAL",
                        help="Análisis de tu canal de YouTube de ese perfil (canales/<CANAL>.yaml) → out/_canal/<CANAL>.json.")
    return parser


def run_one(slug: str, *, force: set[str], until: str | None, review: bool, root: Path = PROJECT_ROOT) -> None:
    """One video, end to end. Raises on failure (the caller decides whether to stop)."""

    ctx = RunContext.create(slug, root=root)
    if not ctx.materials_dir.is_dir():
        raise FileNotFoundError(f"No existe {ctx.materials_dir}")
    from pipeline import budget

    budget.check(root, ctx.config)                       # budget.daily_usd: today's spending at the limit → wait
    with _one_process(ctx):                               # never two runs of one video at once
        _run_one(ctx, force=force, until=until, review=review)


class _one_process:
    """work/<slug>/.proceso holds the pid of the run making this video; a second run stops right away instead of
    rewriting the same files (two runs mixed their candidates and the judge crashed with a KeyError)."""

    def __init__(self, ctx: RunContext) -> None:
        self.path = ctx.work_dir / ".proceso"

    def __enter__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            other = int(self.path.read_text().split()[0]) if self.path.is_file() else 0
        except (OSError, ValueError, IndexError):
            other = 0
        if other and other != os.getpid():
            try:
                os.kill(other, 0)
                raise SystemExit(f"Este vídeo ya se está haciendo en otro proceso (pid {other}). "
                                 f"Si no es así, borra {self.path}")
            except ProcessLookupError:
                pass                                       # a run that died: take over
            except PermissionError:
                raise SystemExit(f"Este vídeo ya se está haciendo en otro proceso (pid {other}).") from None
        self.path.write_text(f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n")

    def __exit__(self, *exc) -> None:
        try:
            if int(self.path.read_text().split()[0]) == os.getpid():
                self.path.unlink(missing_ok=True)
        except (OSError, ValueError, IndexError):
            pass


def _run_one(ctx: RunContext, *, force: set[str], until: str | None, review: bool) -> None:
    from pipeline import diag

    # everything printed also goes to out/<slug>/log.txt; out/<slug>/diagnostico.md says what to improve
    with diag.logging(ctx):
        try:
            if ctx.section("dub").get("of"):            # a dubbed version reuses the original's edit
                from pipeline import dub

                dub.run(ctx)
            else:
                from pipeline import tts

                tts.ensure(ctx)                         # no voz.mp3 but a voice for the channel: GenAIPro makes it
                run_stages(ctx, force=force, until=until, review=review)
                if until is None and not review:
                    from pipeline import housekeeping

                    housekeeping.after_video(ctx)          # cleanup.after_video (a server's small disk)
        except BaseException as error:
            diag.write(ctx, error)
            from pipeline import ytpause

            if isinstance(error, ytpause.YouTubeBlocked):    # the whole queue waits (one message, not one per video)
                ytpause.pause(ctx.root, str(error))
            elif not isinstance(error, KeyboardInterrupt):
                from pipeline import notify as messages

                try:
                    messages.video_failed(ctx, error)       # to the phone: stage, error, link to the log
                except Exception:
                    pass
            raise
        diag.write(ctx)


def pending_slugs(root: Path = PROJECT_ROOT) -> list[str]:
    """materiales/<slug>/ with a script and a voice but no final video yet, oldest first."""

    from pipeline.context import video_folders

    materials = root / "materiales"
    ready, names = [], set()
    for d in video_folders(root):
        skipped = any(part.startswith(("_", ".")) for part in d.relative_to(materials).parts)   # _hechos/, _video
        if skipped or d.name in names or not (d / "guion.txt").is_file():
            continue
        if not (d / "voz.mp3").is_file():
            from pipeline import tts

            if not tts.has_auto_voice(root, d):      # its channel has a GenAIPro voice: made before the first stage
                continue
            if tts.generating(d):                # being made in the background: the next video goes first
                continue
        if (d / HOLD).is_file():           # «Quitar de la cola» in the studio
            continue
        names.add(d.name)                  # two videos with the same name: only the first (out/ is per name)
        from pipeline.housekeeping import is_done

        if not is_done(root, d.name):                       # final video, or uploaded and cleaned up
            ready.append(d)
    from pipeline import agenda

    due = agenda.priority(root) if ready else {}          # the video that goes out first is made first
    return [d.name for d in sorted(ready, key=lambda d: (due.get(d.name, "9999"), d.stat().st_mtime, d.name))]


HOLD = ".en-espera"                    # in a video's folder: out of the queue until «Volver a la cola»


def on_hold(root: Path, slug: str) -> bool:
    from pipeline.context import find_video

    return (find_video(root, slug) / HOLD).is_file()


REQUIRED_KEYS = ("LLM_API_KEY", "OPENAI_API_KEY")
MIN_FREE_GB = 20


def preflight(root: Path = PROJECT_ROOT) -> list[str]:
    """What would make tonight's queue fail, checked before it starts."""

    import requests

    problems: list[str] = []
    ctx = RunContext.create("_preflight", root=root, config={})   # only for .env access
    for name in REQUIRED_KEYS:
        if not ctx.env(name, required=False):
            problems.append(f"falta la clave {name} en .env")
    free_gb = shutil.disk_usage(root).free / 1e9
    if free_gb < MIN_FREE_GB:
        problems.append(f"solo quedan {free_gb:.0f} GB libres en disco (mínimo {MIN_FREE_GB})")
    for tool in ("ffmpeg", "ffprobe", "npx"):
        if not shutil.which(tool):
            problems.append(f"no encuentro '{tool}' en el PATH")
    try:
        if requests.get("https://www.youtube.com", timeout=15).status_code >= 500:
            problems.append("YouTube no responde")
    except requests.RequestException as error:
        problems.append(f"sin conexión con YouTube ({type(error).__name__})")
    return problems


WATCH_STATE = "out/_vigilar.json"
WAKE = "out/_despertar"          # the studio's «Reintentar todos ahora»: the watcher looks again without waiting


def _materials_signature(root: Path, slug: str) -> float:
    from pipeline.context import find_video

    folder = find_video(root, slug)
    files = [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []
    parent = folder.parent / "config.yaml"
    return max([p.stat().st_mtime for p in files + ([parent] if parent.is_file() else [])] or [0.0])


def _git_update(root: Path) -> bool:
    """git pull; True when it brought new code (the watcher then restarts with it)."""

    import subprocess

    def head() -> str:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
        return out.stdout.strip()

    before = head()
    pulled = subprocess.run(["git", "pull", "--ff-only", "-q"], cwd=root, capture_output=True, text=True, timeout=120)
    if pulled.returncode != 0:
        print(f"(git pull no se pudo: {(pulled.stderr or pulled.stdout).strip()[-200:]})")
        return False
    return bool(before) and head() != before


def watch(every_minutes: float = 5.0, root: Path = PROJECT_ROOT) -> None:
    """A server that makes videos all the time: whenever materiales/ has pending videos, the queue runs; otherwise
    it looks again every `every_minutes`. A video that failed is not retried until its files change or
    `watch.retry_hours` (6) pass. Between runs it updates the code (git pull) and restarts itself with it."""

    import json

    state_path = root / WATCH_STATE
    cfg = RunContext.create("_vigilar", root=root).section("watch") if (root / "config.yaml").is_file() else {}
    retry = float(cfg.get("retry_hours", 6)) * 3600
    print(f"Vigilando {root / 'materiales'} cada {every_minutes:g} min (Ctrl+C para parar)")
    idle_since = None

    def beat() -> None:                      # web «vigilando» / bot: alive also during a long video, not only between
        import threading

        def loop() -> None:
            while True:
                try:
                    (root / "out").mkdir(parents=True, exist_ok=True)
                    (root / "out" / "_vigilar.latido").write_text(datetime.now().isoformat(timespec="seconds"))
                except OSError:
                    pass
                time.sleep(60)

        threading.Thread(target=loop, name="latido", daemon=True).start()

    def voices() -> None:                    # GenAIPro narrations made as soon as a video appears, not on its turn
        import threading

        def loop() -> None:
            from pipeline import tts

            try:
                tts.clear_own_locks(root)
            except Exception:
                pass
            while True:
                try:
                    if not (root / "out" / "_pausa").is_file():
                        tts.prepare_all(root)
                except Exception as error:       # never stops the watcher
                    print(f"Voces en segundo plano: {type(error).__name__}: {error}")
                time.sleep(20)

        threading.Thread(target=loop, name="voces", daemon=True).start()

    beat()
    voices()
    while True:
        (root / "out").mkdir(parents=True, exist_ok=True)
        (root / "out" / "_vigilar.latido").write_text(datetime.now().isoformat(timespec="seconds"))   # web: «vigilando»
        if (root / "out" / "_pausa").is_file():                     # paused from the web studio
            time.sleep(60)
            continue
        from pipeline import ytpause

        if ytpause.paused(root):                                    # YouTube blocked: test it now and then
            if ytpause.due(root, float(cfg.get("youtube_probe_minutes", 60))):
                if ytpause.probe(root):
                    ytpause.resume(root)
                    state_path.unlink(missing_ok=True)              # what failed on the block goes again now
                    print(f"{datetime.now():%H:%M} · YouTube vuelve a dejar pasar: sigo con la cola")
                else:
                    print(f"{datetime.now():%H:%M} · YouTube sigue bloqueando: cola en pausa, pruebo en una hora")
            if ytpause.paused(root):
                time.sleep(60)
                continue
        try:
            state = json.loads(state_path.read_text("utf-8")) if state_path.is_file() else {}
        except ValueError:
            state = {}
        skip = {slug for slug, info in state.items()
                if info.get("sig") == _materials_signature(root, slug) and time.time() - info.get("at", 0) < retry}
        from pipeline import dub

        waiting = [slug for slug in pending_slugs(root) if slug not in skip] + [
            slug for slug, _ in dub.pending(root)]
        if waiting:
            idle_since = None
            LAST_RESULTS.clear()
            try:
                run_queue(force=set(), until=None, review=False, root=root, skip=skip)
            except Stopped:                          # systemctl stop / «Parar» in the studio: end now
                raise
            except SystemExit as stop:               # preflight said no (keys, disk…): look again later
                print(stop)
                time.sleep(30 * 60)
            waited = any(status == "en espera" for _, status, _, _ in LAST_RESULTS)
            for slug, status, _, _ in LAST_RESULTS:
                if status == "en espera":                            # budget: not a failure, it goes tomorrow
                    continue
                if status == "OK":
                    state.pop(slug, None)
                else:
                    state[slug] = {"sig": _materials_signature(root, slug), "at": time.time(), "status": status}
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
            if waited:
                time.sleep(30 * 60)                                  # over the daily budget: look again later
        elif idle_since is None:
            idle_since = time.time()
            print(f"{datetime.now():%H:%M} · nada pendiente"
                  + (f" ({len(skip)} con error esperando cambios: {', '.join(sorted(skip))})" if skip else "")
                  + f"; vuelvo a mirar cada {every_minutes:g} min")
        if not waiting:                                              # quiet moment: today's competition radar
            from pipeline import radar

            radar.run_if_due(root)
            from pipeline import housekeeping

            if time.time() - getattr(watch, "chores_at", 0) > 6 * 3600:    # every few hours, while idle
                watch.chores_at = time.time()                              # type: ignore[attr-defined]
                housekeeping.published_chores(root)
        from pipeline import tts
        from pipeline.context import video_folders

        voicing = any(tts.generating(d) for d in video_folders(root))       # never cut a narration being made
        if cfg.get("git_pull", True) and not voicing and _git_update(root):
            print("Código nuevo (git pull): reinicio con él")
            os.execv(sys.executable, [sys.executable, *sys.argv])
        if not waiting:
            wake = root / WAKE
            deadline = time.time() + every_minutes * 60
            while time.time() < deadline and not wake.is_file():      # «Reintentar todos» wakes it at once
                time.sleep(5)
            wake.unlink(missing_ok=True)


def update_ytdlp() -> None:
    """YouTube changes its protections every few weeks and yt-dlp follows: update it before the night."""

    import subprocess

    try:
        # [default] also updates yt-dlp-ejs, the part that solves YouTube's challenges: with an old one
        # next to a new yt-dlp, YouTube serves downloads at a crawl (hours for one video's clips)
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "--quiet", "yt-dlp[default]"],
                                capture_output=True, text=True, timeout=300)
        from importlib.metadata import PackageNotFoundError, version

        try:
            ejs = version("yt-dlp-ejs")
        except PackageNotFoundError:
            ejs = "FALTA"
        runtime = next((name for name in ("deno", "node", "bun") if shutil.which(name)), None)
        print(f"yt-dlp {version('yt-dlp')} · retos (yt-dlp-ejs) {ejs} · JavaScript: {runtime or 'NINGUNO'}"
              + ("" if result.returncode == 0 else " (no se pudo actualizar)"))
        if ejs == "FALTA" or runtime is None:
            print("AVISO: sin yt-dlp-ejs o sin deno/node las descargas de YouTube van lentísimas: "
                  "pip install -U \"yt-dlp[default]\" deno")
    except Exception as error:  # offline or pip missing: the queue still runs with the installed one
        print(f"yt-dlp: no se pudo actualizar ({type(error).__name__})")


def notify(root: Path, text: str) -> None:
    """Email and/or Telegram, whichever is configured in .env; silent otherwise."""

    from pipeline import notify as messages

    first_line = text.splitlines()[0] if text else "Cola"
    messages.send(RunContext.create("_notify", root=root, config={}), first_line, text)


def _describe(error: BaseException) -> str:
    if isinstance(error, QABlocked):
        return f"QA bloqueó el render: {error}"
    if isinstance(error, (StageNotImplemented, ConfigError, FileNotFoundError, RuntimeError, ValueError)):
        return str(error)
    return f"{type(error).__name__}: {error}"


def _clear_stale_lock(lock: Path) -> None:
    """A queue lock left by a process that no longer exists (killed by a restart, power cut) is removed: otherwise
    the watcher would think a queue is running and wait for ever."""

    from pipeline.locks import _alive

    try:
        pid = int(lock.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return
    if pid != os.getpid() and not _alive(pid):
        print(f"(Quito {QUEUE_LOCK}: era de un proceso que ya no existe, pid {pid})")
        lock.unlink(missing_ok=True)


LAST_RESULTS: list[tuple[str, str, float, str]] = []      # the last queue's (slug, status, seconds, detail)


def run_queue(*, force: set[str], until: str | None, review: bool, limit: int = 0, root: Path = PROJECT_ROOT,
              check: bool = True, skip: set[str] | None = None) -> int:
    """Process every pending video; never stop the night because one video failed. Returns failures."""

    lock = root / QUEUE_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    _clear_stale_lock(lock)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode())
        os.close(fd)
    except FileExistsError:
        raise SystemExit(f"Ya hay una cola en marcha ({lock.read_text().strip()}). "
                         f"Si no es así (p. ej. se apagó el PC), borra {QUEUE_LOCK} y vuelve a lanzarla.")
    results: list[tuple[str, str, float, str]] = []
    try:
        if not check:
            problems = []
        else:
            update_ytdlp()
            from pipeline import housekeeping

            try:
                housekeeping.old_cache(RunContext.create("_cola", root=root))   # cleanup.cache_days (a server's disk)
                housekeeping.published_chores(root)          # uploaded videos: their heavy files go
            except Exception as error:   # never stops the night
                print(f"(Limpieza de caché no hecha: {str(error)[:100]})")
            problems = preflight(root)
        if problems:
            message = "Cola NO iniciada:\n- " + "\n- ".join(problems)
            notify(root, message)
            raise SystemExit(message)
        slugs = pending_slugs(root)
        from pipeline import dub

        slugs += [dub.prepare(root, slug, lang) for slug, lang in dub.pending(root)
                  if dub.dub_slug(slug, lang) not in slugs]    # dubs of videos already finished
        slugs = [slug for slug in slugs if slug not in (skip or set())]   # --vigilar: failed lately, unchanged
        if limit > 0:
            slugs = slugs[:limit]
        print(f"Cola: {len(slugs)} vídeo(s) pendiente(s): {', '.join(slugs) or '—'}")
        workers = parallel_videos(root)
        if workers > 1 and len(slugs) > 1:
            results += run_parallel(slugs, workers, force=force, until=until, review=review, root=root)
            slugs = []
        from pipeline import ytpause

        for number, slug in enumerate(slugs, start=1):
            if ytpause.paused(root):
                print("YouTube bloqueado: la cola se para aquí (sigue sola cuando YouTube deje pasar)")
                break
            if on_hold(root, slug):
                print(f"{slug}: quitado de la cola, se salta")
                continue
            print(f"\n{'=' * 70}\n[{number}/{len(slugs)}] {slug} · {datetime.now():%H:%M}\n{'=' * 70}")
            started = time.monotonic()
            try:
                run_one(slug, force=force, until=until, review=review, root=root)
                results.append((slug, "OK", time.monotonic() - started, ""))
            except KeyboardInterrupt:
                results.append((slug, "interrumpido", time.monotonic() - started, "Ctrl+C"))
                raise
            except Stopped as stop:          # systemctl restart/stop: the whole queue stops, not just this video
                results.append((slug, "interrumpido", time.monotonic() - started, str(stop)))
                raise
            except BaseException as error:  # SystemExit too: one bad video must not end the queue
                from pipeline.budget import BudgetReached

                if isinstance(error, BudgetReached):            # not this video's fault: the rest wait too
                    results.append((slug, "en espera", time.monotonic() - started, str(error)))
                    print(f"⏸ {error}")
                    notify(root, f"⏸ {error}")
                    break
                traceback.print_exc()
                results.append((slug, "ERROR", time.monotonic() - started, _describe(error)))
                print(f"✗ {slug}: {_describe(error)} — sigo con el siguiente")
            _write_report(root, results)
    finally:
        lock.unlink(missing_ok=True)
        _write_report(root, results)
    LAST_RESULTS[:] = results
    failures = sum(1 for _, status, _, _ in results if status != "OK")
    print(f"\nCola terminada: {len(results) - failures} OK · {failures} con error · resumen en {QUEUE_REPORT}")
    if results:
        notify(root, f"Cola terminada: {len(results) - failures} OK · {failures} con error\n" + "\n".join(
            f"{'✅' if status == 'OK' else '❌'} {slug} · {seconds / 60:.0f} min" + (f" · {detail[:150]}" if detail else "")
            for slug, status, seconds, detail in results))
    return failures


def parallel_videos(root: Path) -> int:
    try:
        cfg = RunContext.create("_cola", root=root).section("queue")
    except ConfigError:
        return 1
    return max(1, int(cfg.get("parallel_videos", 1)))


def run_parallel(slugs: list[str], workers: int, *, force: set[str], until: str | None, review: bool,
                 root: Path) -> list[tuple[str, str, float, str]]:
    """Several videos at once, each in its own process. The heavy stages take turns (pipeline/locks.py):
    while one video downloads from YouTube, another one analyses or renders. Each video's lines are
    prefixed with its name and kept in out/_cola/<video>.log."""

    import subprocess
    import threading
    from collections import deque

    logs = root / "out" / "_cola"
    logs.mkdir(parents=True, exist_ok=True)
    pending = deque(slugs)
    results: list[tuple[str, str, float, str]] = []
    lock = threading.Lock()

    def run(slug: str) -> None:
        started = time.monotonic()
        args = [sys.executable, "-u", str(root / "main.py"), "--slug", slug, *[f"--force={f}" for f in force]]
        if until:
            args.append(f"--until={until}")
        if review:
            args.append("--review")
        tail: deque[str] = deque(maxlen=200)
        with (logs / f"{slug}.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       encoding="utf-8", errors="replace",
                                       env={**os.environ, "EDITVID_TURNS": "1", "PYTHONUNBUFFERED": "1",
                                            "PYTHONIOENCODING": "utf-8"})   # accents intact on Windows
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                line = line.rstrip()
                tail.append(line)
                if line and not line.startswith(("[h264", "libpng", "[ WARN")):
                    print(f"[{slug}] {line}", flush=True)
            code = process.wait()
        detail = "" if code == 0 else _error_line(list(tail), code)
        with lock:
            results.append((slug, "OK" if code == 0 else "ERROR", time.monotonic() - started, detail))
            _write_report(root, results)

    def worker() -> None:
        while True:
            with lock:
                if not pending:
                    return
                slug = pending.popleft()
            from pipeline import ytpause

            if ytpause.paused(root):
                return
            if on_hold(root, slug):
                print(f"{slug}: quitado de la cola, se salta")
                continue
            run(slug)

    print(f"Cola en paralelo: {workers} vídeos a la vez (red y CPU por turnos) · registros en out/_cola/")
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for thread in threads:
        thread.start()
        time.sleep(2)
    for thread in threads:
        thread.join()
    return results


NOISE = ("[h264", "[hevc", "[mov", "[aac", "libpng", "[ WARN", "frame=", "size=")


def _error_line(tail: list[str], code: int) -> str:
    """The line that says what failed, not ffmpeg's last decoder warning (e.g. «mmco: unref short failure»)."""

    lines = [l.strip() for l in tail if l.strip() and not l.strip().startswith(NOISE)]
    for line in reversed(lines):
        if re.search(r"Falló|Error|error:|Exception|Traceback", line) and not line.startswith("Traceback"):
            return line
    return lines[-1] if lines else f"código {code}"


def _write_report(root: Path, results: list[tuple[str, str, float, str]]) -> None:
    lines = [f"# Cola · {datetime.now():%Y-%m-%d %H:%M}", "",
             "| Vídeo | Estado | Tiempo | Detalle | Lo primero a mejorar |", "|---|---|---|---|---|"]
    for slug, status, seconds, detail in results:
        where = f"out/{slug}/video-final.mp4" if status == "OK" else detail.replace("|", "/")[:300]
        diag = root / "work" / slug / "diag.json"
        try:
            tips = json.loads(diag.read_text("utf-8")).get("consejos", [])
        except (OSError, ValueError):
            tips = []
        tip = (tips[0].replace("|", "/")[:160] + f" (+{len(tips) - 1} en out/{slug}/diagnostico.md)") if tips else "—"
        lines.append(f"| {slug} | {status} | {seconds / 60:.0f} min | {where} | {tip} |")
    report = root / QUEUE_REPORT
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Stopped(SystemExit):
    """The process was told to stop (closed SSH window, systemctl stop, kill): said in the log and the diagnosis
    instead of vanishing without a trace."""


def _more_open_files() -> None:
    """Linux gives a process 1024 open files by default; the analysis of a long video (hundreds of downloads through
    the proxy, threads, models) can need more. Raised to what the system allows, up to 65536."""

    try:
        import resource
    except ImportError:          # Windows: no such limit
        return
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        wanted = 65536 if hard == resource.RLIM_INFINITY else min(65536, hard)
        if soft != resource.RLIM_INFINITY and soft < wanted:
            resource.setrlimit(resource.RLIMIT_NOFILE, (wanted, hard))
    except (ValueError, OSError):
        pass


def _stop_signals() -> None:
    import signal

    names = {getattr(signal, n): n for n in ("SIGHUP", "SIGTERM") if hasattr(signal, n)}

    def stop(number, _frame):
        why = {"SIGHUP": "se cerró la ventana/sesión SSH desde la que se lanzó (usa tmux o el servicio)",
               "SIGTERM": "alguien o algo lo paró (systemctl stop, kill, reinicio)"}.get(names.get(number, ""), "")
        raise Stopped(f"Parado por la señal {names.get(number, number)}: {why}")

    for number in names:
        try:
            signal.signal(number, stop)
        except (ValueError, OSError):            # not the main thread / not supported here
            pass


def main() -> None:
    args = _parser().parse_args()
    _stop_signals()
    _more_open_files()
    if args.check:
        from pipeline import factcheck

        ctx = RunContext.create(args.check)
        if not (ctx.materials_dir / "guion.txt").is_file():
            raise SystemExit(f"No existe {ctx.materials_dir / 'guion.txt'}")
        factcheck.run(ctx)
        print(factcheck.summary(ctx))
        from pipeline import hook

        try:
            path = hook.run(ctx)                    # does the opening keep the title's promise? → gancho.md
            print(path.read_text("utf-8").split("\n")[2] + f" ({path.relative_to(ctx.root)})")
        except Exception as error:
            print(f"Gancho no revisado: {str(error)[:160]}")
        return
    if args.shorts:
        from pipeline import shorts

        ctx = RunContext.create(args.shorts)
        if not (ctx.out_dir / "video-final.mp4").is_file():
            raise SystemExit(f"Aún no existe {ctx.out_dir / 'video-final.mp4'}")
        ctx.config.setdefault("shorts", {})["enabled"] = True
        shorts.run(ctx)
        print(f"Shorts en {ctx.out_dir / shorts.DIR}")
        return
    if args.dub:
        from pipeline import dub

        slug, _, lang = args.dub.partition(":")
        if not lang:
            raise SystemExit("Usa --dub SLUG:IDIOMA, p. ej. --dub CarlosYulo:en")
        run_one(dub.prepare(PROJECT_ROOT, slug, lang), force=set(), until=None, review=False)
        return
    if args.editor:
        from pipeline import editor

        editor.serve(RunContext.create(args.editor))
        return
    if args.panel:
        from pipeline import panel

        panel.serve(RunContext.create("_panel", channel=args.canal))
        return
    if args.ideas:
        from pipeline import ideas

        path = ideas.run(RunContext.create("_ideas", channel=args.canal, series=args.serie))
        print(f"Ideas en {path}")
        return
    if args.vigilar is not None:
        watch(args.vigilar)
        return
    if args.web is not None:
        from pipeline import web

        web.serve(port=args.web, host=args.host)
        return
    if args.bot:
        from pipeline import bot

        bot.Bot().run()
        return
    if args.radar:
        from pipeline import radar

        print(f"Radar en {radar.run(PROJECT_ROOT, force=True)}")
        return
    if args.mi_canal:
        from pipeline import mychannel

        report = mychannel.run(PROJECT_ROOT, args.mi_canal)
        print("\n".join(report["tips"]) or "Hecho")
        print(f"Guardado en out/_canal/{args.mi_canal}.json")
        return
    if args.youtube_stats is not None:
        from pipeline import ytstats

        path = ytstats.report(PROJECT_ROOT, args.youtube_stats)
        print(path.read_text("utf-8"))
        print(f"Guardado en {path}")
        return
    if args.probar_youtube:
        from pipeline import ytcheck

        ytcheck.run(RunContext.create("_ytcheck"))
        return
    if args.formatos:
        from pipeline import formats

        print(formats.listing(PROJECT_ROOT))
        print("\nÚsalo con `format: <nombre>` en materiales/<vídeo>/config.yaml (o en el canal / la serie).")
        return
    if args.semana:
        from pipeline import ideas

        print(f"Plan de la semana en {ideas.weekly(args.semana)}")
        return
    if args.series:
        from pipeline import series_report

        try:
            path = series_report.report(args.series)
        except (ConfigError, ValueError) as error:
            raise SystemExit(f"Error: {error}") from error
        print(path.read_text("utf-8"))
        print(f"(guardado en {path})")
        return
    if args.all:
        failures = run_queue(force=set(args.force), until=args.until, review=args.review, limit=args.limit)
        sys.exit(1 if failures else 0)
    try:
        run_one(args.slug, force=set(args.force), until=args.until, review=args.review)
    except StageNotImplemented as error:
        raise SystemExit(f"Parada: {error}") from error
    except QABlocked as error:
        raise SystemExit(f"Render bloqueado por la QA: {error}. Revisa out/{args.slug}/qa/report.md") from error
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
