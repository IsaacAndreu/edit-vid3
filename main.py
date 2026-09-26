from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from pipeline.build_props import build_props
from pipeline.config import ConfigError, Settings, load_settings
from pipeline.analytics import write_timeline_manifest
from pipeline.fetch_media import fetch_media
from pipeline.postflight import (
    RenderPostflightError,
    enforce_postflight,
    inspect_render,
    master_audio,
    write_postflight_report,
)
from pipeline.qa import PipelineQualityError, enforce_qa, validate_scene_plan, write_qa_report
from pipeline.segment import segment_script
from pipeline.transcribe import transcribe_audio


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera un vídeo Remotion a partir de un guion y una voz en off."
    )
    parser.add_argument("--guion", type=Path, required=True, help="Fichero de guion UTF-8.")
    parser.add_argument("--voz", type=Path, required=True, help="Audio de voz en off.")
    parser.add_argument("--output", type=Path, required=True, help="Ruta del MP4 final.")
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
    return parser


def _render_remotion(props_path: Path, output_path: Path, settings: Settings) -> None:
    executable = "npx.cmd" if os.name == "nt" else "npx"
    command = [
        executable,
        "remotion",
        "render",
        "src/index.ts",
        "YoutubeVideo",
        str(output_path),
        "--props",
        str(props_path),
    ]
    subprocess.run(command, cwd=settings.project_root, check=True)


def _copy_audio_to_public(audio_path: Path, assets_dir: Path, project_root: Path) -> str:
    target = assets_dir / "audio" / f"voice{audio_path.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_path, target)
    relative_path = target.resolve().relative_to((project_root / "public").resolve())
    return f"/{relative_path.as_posix()}"


def run_pipeline(args: argparse.Namespace) -> Path:
    settings = load_settings()
    script_path = args.guion.expanduser().resolve()
    audio_path = args.voz.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not script_path.is_file():
        raise FileNotFoundError(f"No existe el guion: {script_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("1/8 Transcribiendo audio con Whisper...")
    transcript = transcribe_audio(audio_path, settings)
    print(f"   {len(transcript['words'])} palabras con timestamp")

    print("2/8 Segmentando el guion con DeepSeek...")
    script_text = script_path.read_text(encoding="utf-8")
    scenes = segment_script(script_text, transcript, settings)
    print(f"   {len(scenes)} escenas")

    run_id = output_path.stem
    assets_dir = settings.project_root / "public" / "pipeline-assets" / run_id
    audio_url = _copy_audio_to_public(audio_path, assets_dir, settings.project_root)
    print("3/8 Resolviendo material visual...")
    scenes = fetch_media(
        scenes,
        settings,
        assets_dir=assets_dir,
        avatar_dir=args.avatar_dir,
        third_party_enabled=not args.skip_third_party,
    )

    print("4/8 Ejecutando QA pre-render...")
    qa_issues = validate_scene_plan(scenes, transcript["duration_seconds"])
    qa_path = output_path.with_suffix(".qa.json")
    write_qa_report(qa_path, qa_issues)
    for issue in qa_issues:
        scene_label = f" escena {issue.scene_index}" if issue.scene_index is not None else ""
        print(f"   [{issue.level.upper()}]{scene_label} {issue.message}")
    enforce_qa(qa_issues)

    props_path = output_path.with_suffix(".props.json")
    print("5/8 Construyendo props.json...")
    build_props(scenes, props_path, audio_url=audio_url)
    print(f"   Props: {props_path}")
    timeline_path = output_path.with_suffix(".timeline.json")
    write_timeline_manifest(scenes, timeline_path)
    print(f"   Timeline: {timeline_path}")

    if args.skip_render:
        print("6/8 Render omitido por --skip-render.")
        return props_path

    print("6/8 Renderizando con Remotion...")
    _render_remotion(props_path, output_path, settings)
    if not args.skip_audio_master:
        print("7/8 Masterizando audio a -16 LUFS...")
        master_audio(output_path)
    else:
        print("7/8 Masterización de audio omitida.")
    print("8/8 Ejecutando postflight técnico...")
    postflight_issues = inspect_render(output_path, transcript["duration_seconds"])
    postflight_path = output_path.with_suffix(".postflight.json")
    write_postflight_report(postflight_path, postflight_issues)
    enforce_postflight(postflight_issues)
    print(f"Vídeo generado: {output_path}")
    return output_path


def main() -> None:
    args = _parser().parse_args()
    try:
        run_pipeline(args)
    except (
        ConfigError,
        FileNotFoundError,
        PipelineQualityError,
        RenderPostflightError,
        RuntimeError,
        ValueError,
    ) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
