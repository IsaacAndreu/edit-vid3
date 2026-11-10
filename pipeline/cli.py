"""Command line interface.

    python main.py materiales/Video1            # carpeta con guion.txt y voz.mp3
    python main.py --guion g.txt --voz v.mp3 --output out/v.mp4
    python main.py render out/Video1/Video1.mp4 # solo render + master + postflight
    python main.py doctor [--apis]              # comprobar el entorno
    python main.py report out/Video1/Video1.mp4 # regenerar el informe HTML
    python main.py studio out/Video1/Video1.mp4 # abrir Remotion Studio con ese run
    python main.py clean [--keep N] [--yes]     # borrar assets de runs antiguos
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import preflight
from .cache import default_cache_dir
from .config import ConfigError
from .fetch_media import MediaFetchError
from .overrides import OverridesError
from .postflight import RenderPostflightError
from .qa import PipelineQualityError
from .render import studio_command
from .report import write_report
from .runner import RunRequest, render_only, resolve_render_target, run_pipeline, sidecar
from .templates import PROJECT_ROOT


SUBCOMMANDS = {"run", "render", "doctor", "report", "studio", "clean"}
AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus")


class UsageError(ValueError):
    """The command line cannot be turned into a run."""


# ---------------------------------------------------------------------------
# parsers
# ---------------------------------------------------------------------------
def _run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Genera un vídeo Remotion a partir de un guion y una voz en off.",
        epilog="Otros comandos: render, doctor, report, studio, clean (cada uno admite --help).",
    )
    parser.add_argument(
        "proyecto",
        nargs="?",
        type=Path,
        help="Carpeta con guion.txt y voz.mp3. La salida va a out/<carpeta>/<carpeta>.mp4.",
    )
    parser.add_argument("--guion", type=Path, help="Fichero de guion UTF-8.")
    parser.add_argument("--voz", type=Path, help="Audio de voz en off.")
    parser.add_argument("--output", type=Path, help="Ruta del MP4 final.")
    parser.add_argument(
        "--avatar-dir",
        type=Path,
        help="Carpeta opcional con scene-001.mp4, scene-002.mp4, etc. para escenas avatar.",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Genera y guarda props.json, pero no lanza Remotion (útil para probar el pipeline).",
    )
    parser.add_argument(
        "--skip-audio-master",
        action="store_true",
        help="No normaliza el audio después del render de Remotion.",
    )
    parser.add_argument(
        "--skip-third-party",
        action="store_true",
        help="Desactiva yt-dlp/YouTube y prueba directamente Pexels/GPT Image.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignora la caché de transcripción/segmentación y el checkpoint de material: rehace todo.",
    )
    parser.add_argument(
        "--redo-scenes",
        metavar="N[,N...]",
        help="Vuelve a buscar material solo para esas escenas (números del informe), evitando el plano anterior.",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="JSON con correcciones por escena (por defecto, overrides.json en la carpeta del proyecto).",
    )
    parser.add_argument(
        "--media-concurrency",
        type=int,
        metavar="N",
        help="Escenas que buscan material de YouTube a la vez (por defecto MEDIA_CONCURRENCY o 3).",
    )
    parser.add_argument(
        "--render-concurrency",
        metavar="N|N%",
        help='Concurrencia del render de Remotion, p. ej. "6" o "75%%".',
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="No comprueba el entorno antes de empezar.",
    )
    parser.add_argument("--verbose", action="store_true", help="Muestra también los mensajes de depuración.")
    return parser


def _render_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py render",
        description="Renderiza de nuevo a partir de un props.json existente; después masteriza y verifica.",
    )
    parser.add_argument("target", type=Path, help="El MP4 de salida o su .props.json.")
    parser.add_argument("--skip-audio-master", action="store_true", help="No normaliza el audio.")
    parser.add_argument("--render-concurrency", metavar="N|N%", help="Concurrencia de Remotion.")
    parser.add_argument("--skip-preflight", action="store_true", help="No comprueba el entorno antes.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py doctor",
        description="Comprueba que el entorno puede ejecutar el pipeline. No hace llamadas de pago.",
    )
    parser.add_argument("proyecto", nargs="?", type=Path, help="Carpeta de proyecto a validar (opcional).")
    parser.add_argument("--apis", action="store_true", help="Verifica además las tres claves con peticiones gratuitas.")
    parser.add_argument("--skip-third-party", action="store_true", help="No exige yt-dlp ni Deno.")
    parser.add_argument("--skip-render", action="store_true", help="No exige Node ni Remotion.")
    return parser


def _target_parser(prog: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument("target", type=Path, help="El MP4 de salida o su .props.json.")
    return parser


def _clean_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py clean",
        description=(
            "Lista los assets descargados por run en public/pipeline-assets y, con --yes, los borra. "
            "Sin --yes solo muestra lo que borraría."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--keep", type=int, metavar="N", help="Conserva los N runs más recientes y borra el resto.")
    group.add_argument("--run", metavar="NOMBRE", help="Borra solo ese run.")
    group.add_argument("--older-than", type=int, metavar="DÍAS", help="Borra los runs sin cambios desde hace más de DÍAS.")
    parser.add_argument("--cache", action="store_true", help="Borra también la caché de transcripciones y segmentaciones.")
    parser.add_argument("--yes", action="store_true", help="Borra de verdad.")
    return parser


# ---------------------------------------------------------------------------
# project resolution
# ---------------------------------------------------------------------------
def _find_one(directory: Path, preferred: str, suffixes: tuple[str, ...], what: str) -> Path:
    preferred_matches = sorted(
        path for path in directory.iterdir() if path.is_file() and path.stem.lower() == preferred and path.suffix.lower() in suffixes
    )
    if preferred_matches:
        return preferred_matches[0]
    matches = sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in suffixes)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise UsageError(f"En {directory} no hay {what} ({preferred}{suffixes[0]}).")
    names = ", ".join(path.name for path in matches)
    raise UsageError(
        f"En {directory} hay varios candidatos a {what} ({names}). "
        f"Llama a uno {preferred}{matches[0].suffix} o indícalo con su opción."
    )


def resolve_project(directory: Path) -> tuple[Path, Path, Path]:
    """Return ``(guion, voz, output)`` for a project folder."""

    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        raise UsageError(f"{directory} no es una carpeta de proyecto.")
    script = _find_one(directory, "guion", (".txt",), "guion")
    voice = _find_one(directory, "voz", AUDIO_SUFFIXES, "audio de voz")
    output = PROJECT_ROOT / "out" / directory.name / f"{directory.name}.mp4"
    return script, voice, output


def _parse_scene_numbers(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()
    numbers: set[int] = set()
    for piece in raw.replace(" ", "").split(","):
        if not piece:
            continue
        try:
            if "-" in piece:
                first, last = (int(part) for part in piece.split("-", 1))
                if first > last:
                    raise ValueError
                numbers.update(range(first, last + 1))
            else:
                numbers.add(int(piece))
        except ValueError as error:
            raise UsageError(f"--redo-scenes: {piece!r} no es un número ni un rango (ej. 12,17,20-22).") from error
    if any(number < 1 for number in numbers):
        raise UsageError("--redo-scenes: las escenas se numeran desde 1.")
    return frozenset(numbers)


def build_run_request(args: argparse.Namespace) -> RunRequest:
    script, voice, output = args.guion, args.voz, args.output
    overrides = args.overrides
    if args.proyecto is not None:
        project_script, project_voice, project_output = resolve_project(args.proyecto)
        script = script or project_script
        voice = voice or project_voice
        output = output or project_output
        default_overrides = args.proyecto.expanduser().resolve() / "overrides.json"
        if overrides is None and default_overrides.is_file():
            overrides = default_overrides
    missing = [name for name, value in (("--guion", script), ("--voz", voice), ("--output", output)) if value is None]
    if missing:
        raise UsageError(
            "Faltan " + ", ".join(missing) + ". Indica una carpeta de proyecto "
            "(python main.py materiales/Video1) o las tres opciones."
        )
    if args.media_concurrency is not None and not 1 <= args.media_concurrency <= 8:
        raise UsageError("--media-concurrency debe estar entre 1 y 8.")
    if overrides is not None and not overrides.expanduser().is_file():
        raise UsageError(f"No existe el fichero de overrides {overrides}.")
    return RunRequest(
        script_path=script,
        audio_path=voice,
        output_path=output,
        avatar_dir=args.avatar_dir,
        skip_render=args.skip_render,
        skip_audio_master=args.skip_audio_master,
        skip_third_party=args.skip_third_party,
        skip_preflight=args.skip_preflight,
        fresh=args.fresh,
        redo_scenes=_parse_scene_numbers(args.redo_scenes),
        overrides_path=overrides.expanduser().resolve() if overrides is not None else None,
        media_concurrency=args.media_concurrency,
        render_concurrency=args.render_concurrency,
        verbose=args.verbose,
    )


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def _cmd_run(argv: list[str]) -> int:
    request = build_run_request(_run_parser().parse_args(argv))
    run_pipeline(request)
    return 0


def _cmd_render(argv: list[str]) -> int:
    args = _render_parser().parse_args(argv)
    render_only(
        args.target,
        skip_audio_master=args.skip_audio_master,
        render_concurrency=args.render_concurrency,
        skip_preflight=args.skip_preflight,
        verbose=args.verbose,
    )
    return 0


def _cmd_doctor(argv: list[str]) -> int:
    args = _doctor_parser().parse_args(argv)
    script = voice = output = None
    if args.proyecto is not None:
        script, voice, output = resolve_project(args.proyecto)
    checks = preflight.run_checks(
        need_third_party=not args.skip_third_party,
        need_render=not args.skip_render,
        audio_path=voice,
        script_path=script,
        output_path=output,
        check_apis=args.apis,
    )
    print(preflight.format_checks(checks))
    errors = sum(1 for check in checks if check.status == preflight.ERROR)
    warnings = sum(1 for check in checks if check.status == preflight.WARNING)
    if errors:
        print(f"\n{errors} problema(s) impedirían el run; {warnings} aviso(s).")
        return 1
    print(f"\nEntorno listo. {warnings} aviso(s).")
    return 0


def _cmd_report(argv: list[str]) -> int:
    args = _target_parser("main.py report", "Regenera el informe HTML de un run.").parse_args(argv)
    output_path, _props = resolve_render_target(args.target)
    report_path = write_report(output_path)
    if report_path is None:
        raise FileNotFoundError(f"No existe {sidecar(output_path, 'timeline.json')}; ese run no ha llegado a QA.")
    print(f"Informe: {report_path}")
    return 0


def _cmd_studio(argv: list[str]) -> int:
    args = _target_parser("main.py studio", "Abre Remotion Studio con los props de un run.").parse_args(argv)
    _output, props_path = resolve_render_target(args.target)
    if not props_path.is_file():
        raise FileNotFoundError(f"No existe {props_path}.")
    return subprocess.run(studio_command(props_path), cwd=PROJECT_ROOT, check=False).returncode


def _directory_stats(path: Path) -> tuple[int, float]:
    size = 0
    newest = path.stat().st_mtime
    for item in path.rglob("*"):
        try:
            stat = item.stat()
        except OSError:
            continue
        if item.is_file():
            size += stat.st_size
        newest = max(newest, stat.st_mtime)
    return size, newest


def _cmd_clean(argv: list[str]) -> int:
    args = _clean_parser().parse_args(argv)
    assets_root = PROJECT_ROOT / "public" / "pipeline-assets"
    runs = sorted(path for path in assets_root.iterdir() if path.is_dir()) if assets_root.is_dir() else []
    stats = {run: _directory_stats(run) for run in runs}
    ordered = sorted(runs, key=lambda run: stats[run][1], reverse=True)

    if args.run:
        doomed = [run for run in ordered if run.name == args.run]
        if not doomed:
            raise UsageError(f"No existe el run {args.run!r} en {assets_root}.")
    elif args.keep is not None:
        if args.keep < 0:
            raise UsageError("--keep no puede ser negativo.")
        doomed = ordered[args.keep :]
    elif args.older_than is not None:
        limit = time.time() - args.older_than * 86400
        doomed = [run for run in ordered if stats[run][1] < limit]
    else:
        doomed = []

    if not ordered:
        print(f"No hay assets de runs en {assets_root}.")
    for run in ordered:
        size, newest = stats[run]
        mark = "BORRAR" if run in doomed else "      "
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(newest))
        print(f"  {mark}  {size / 1024**2:9.1f} MB  {when}  {run.name}")

    cache_dir = default_cache_dir()
    if args.cache:
        print(f"  BORRAR  caché de transcripciones y segmentaciones: {cache_dir}")

    if not doomed and not args.cache:
        print("\nNada seleccionado. Usa --keep N, --run NOMBRE u --older-than DÍAS.")
        return 0
    freed = sum(stats[run][0] for run in doomed)
    if not args.yes:
        print(f"\nSimulación: se liberarían {freed / 1024**2:.1f} MB. Añade --yes para borrar.")
        return 0
    for run in doomed:
        shutil.rmtree(run)
    if args.cache and cache_dir.is_dir():
        shutil.rmtree(cache_dir)
    print(f"\nBorrado. {freed / 1024**2:.1f} MB liberados.")
    return 0


_COMMANDS = {
    "run": _cmd_run,
    "render": _cmd_render,
    "doctor": _cmd_doctor,
    "report": _cmd_report,
    "studio": _cmd_studio,
    "clean": _cmd_clean,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = "run"
    if argv and argv[0] in SUBCOMMANDS:
        command, argv = argv[0], argv[1:]
    try:
        return _COMMANDS[command](argv)
    except KeyboardInterrupt:
        print(
            "\nInterrumpido. Lo ya resuelto queda guardado: relanza el mismo comando para continuar.",
            file=sys.stderr,
        )
        return 130
    except (
        ConfigError,
        UsageError,
        OverridesError,
        FileNotFoundError,
        preflight.PreflightError,
        PipelineQualityError,
        RenderPostflightError,
        MediaFetchError,
        RuntimeError,
        ValueError,
        OSError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        # Network/SDK errors (requests, openai) have no common base with the above.
        print(f"Error inesperado ({type(error).__name__}): {error}", file=sys.stderr)
        print("El detalle completo está en el .log junto a la salida.", file=sys.stderr)
        return 1
