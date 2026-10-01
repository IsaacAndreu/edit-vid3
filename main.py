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
        description="Genera un vídeo documental a partir de materiales/<slug>/{titulo.txt, guion.txt, voz.mp3}."
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
                        help="Solo verifica los datos del guion de materiales/SLUG (antes de grabar la voz) → out/SLUG/verificacion.md.")
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
    return parser


def run_one(slug: str, *, force: set[str], until: str | None, review: bool, root: Path = PROJECT_ROOT) -> None:
    """One video, end to end. Raises on failure (the caller decides whether to stop)."""

    from pipeline import diag

    ctx = RunContext.create(slug, root=root)
    if not ctx.materials_dir.is_dir():
        raise FileNotFoundError(f"No existe {ctx.materials_dir}")
    # everything printed also goes to out/<slug>/log.txt; out/<slug>/diagnostico.md says what to improve
    with diag.logging(ctx):
        try:
            if ctx.section("dub").get("of"):            # a dubbed version reuses the original's edit
                from pipeline import dub

                dub.run(ctx)
            else:
                run_stages(ctx, force=force, until=until, review=review)
        except BaseException as error:
            diag.write(ctx, error)
            raise
        diag.write(ctx)


def pending_slugs(root: Path = PROJECT_ROOT) -> list[str]:
    """materiales/<slug>/ with a script and a voice but no final video yet, oldest first."""

    materials = root / "materiales"
    if not materials.is_dir():
        return []
    ready = [
        d for d in materials.iterdir()
        if d.is_dir() and not d.name.startswith((".", "_"))
        and (d / "guion.txt").is_file() and (d / "voz.mp3").is_file()
        and not (root / "out" / d.name / "video-final.mp4").is_file()
    ]
    return [d.name for d in sorted(ready, key=lambda d: (d.stat().st_mtime, d.name))]


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


def run_queue(*, force: set[str], until: str | None, review: bool, limit: int = 0, root: Path = PROJECT_ROOT,
              check: bool = True) -> int:
    """Process every pending video; never stop the night because one video failed. Returns failures."""

    lock = root / QUEUE_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
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
            problems = preflight(root)
        if problems:
            message = "Cola NO iniciada:\n- " + "\n- ".join(problems)
            notify(root, message)
            raise SystemExit(message)
        slugs = pending_slugs(root)
        from pipeline import dub

        slugs += [dub.prepare(root, slug, lang) for slug, lang in dub.pending(root)
                  if dub.dub_slug(slug, lang) not in slugs]    # dubs of videos already finished
        if limit > 0:
            slugs = slugs[:limit]
        print(f"Cola: {len(slugs)} vídeo(s) pendiente(s): {', '.join(slugs) or '—'}")
        workers = parallel_videos(root)
        if workers > 1 and len(slugs) > 1:
            results += run_parallel(slugs, workers, force=force, until=until, review=review, root=root)
            slugs = []
        for number, slug in enumerate(slugs, start=1):
            print(f"\n{'=' * 70}\n[{number}/{len(slugs)}] {slug} · {datetime.now():%H:%M}\n{'=' * 70}")
            started = time.monotonic()
            try:
                run_one(slug, force=force, until=until, review=review, root=root)
                results.append((slug, "OK", time.monotonic() - started, ""))
            except KeyboardInterrupt:
                results.append((slug, "interrumpido", time.monotonic() - started, "Ctrl+C"))
                raise
            except BaseException as error:  # SystemExit too: one bad video must not end the queue
                traceback.print_exc()
                results.append((slug, "ERROR", time.monotonic() - started, _describe(error)))
                print(f"✗ {slug}: {_describe(error)} — sigo con el siguiente")
            _write_report(root, results)
    finally:
        lock.unlink(missing_ok=True)
        _write_report(root, results)
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


def main() -> None:
    args = _parser().parse_args()
    if args.check:
        from pipeline import factcheck

        ctx = RunContext.create(args.check)
        if not (ctx.materials_dir / "guion.txt").is_file():
            raise SystemExit(f"No existe {ctx.materials_dir / 'guion.txt'}")
        factcheck.run(ctx)
        print(factcheck.summary(ctx))
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
