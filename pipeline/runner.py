"""Pipeline orchestration: one function per entry point of the CLI."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import preflight
from .analytics import write_timeline_manifest
from .build_props import build_props
from .cache import JsonCache, read_json
from .config import REMOTION_FPS, Settings, load_settings
from .fetch_media import MediaOptions, fetch_media
from .overrides import apply_overrides, load_overrides
from .postflight import (
    enforce_postflight,
    inspect_render,
    master_audio,
    write_postflight_report,
)
from .qa import enforce_qa, validate_scene_plan, write_qa_report
from .render import render_remotion
from .report import write_report
from .runlog import configure as configure_log
from .runlog import log
from .segment import segment_script
from .timing import METRICS
from .transcribe import transcribe_audio


@dataclass
class RunRequest:
    script_path: Path
    audio_path: Path
    output_path: Path
    avatar_dir: Path | None = None
    skip_render: bool = False
    skip_audio_master: bool = False
    skip_third_party: bool = False
    skip_preflight: bool = False
    # Ignore the transcript/segmentation cache and the media checkpoint.
    fresh: bool = False
    # 1-based scene numbers whose media must be resolved again.
    redo_scenes: frozenset[int] = field(default_factory=frozenset)
    overrides_path: Path | None = None
    media_concurrency: int | None = None
    render_concurrency: str | None = None
    verbose: bool = False


def sidecar(output_path: Path, kind: str) -> Path:
    """``video.mp4`` + ``props.json`` -> ``video.props.json``."""

    return output_path.with_suffix(f".{kind}")


def _copy_audio_to_public(audio_path: Path, assets_dir: Path, project_root: Path) -> str:
    target = assets_dir / "audio" / f"voice{audio_path.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_path, target)
    relative_path = target.resolve().relative_to((project_root / "public").resolve())
    return f"/{relative_path.as_posix()}"


def _run_preflight(request: RunRequest) -> None:
    checks = preflight.run_checks(
        need_third_party=not request.skip_third_party,
        need_render=not request.skip_render,
        need_audio_master=not request.skip_audio_master,
        audio_path=request.audio_path,
        script_path=request.script_path,
        output_path=request.output_path,
    )
    for check in checks:
        if check.status == preflight.WARNING:
            log.warning(f"Aviso: {check.name}: {check.detail}" + (f" ({check.fix})" if check.fix else ""))
    preflight.enforce(checks)


def _finish_render(
    output_path: Path,
    props_path: Path,
    settings: Settings,
    expected_duration_seconds: float,
    *,
    skip_audio_master: bool,
    render_concurrency: str | None,
) -> None:
    """Steps 6-8: render, loudness master and technical verification."""

    log.info("6/8 Renderizando con Remotion...")
    with METRICS.step("render"):
        render_remotion(props_path, output_path, settings, concurrency=render_concurrency)

    if not skip_audio_master:
        log.info("7/8 Masterizando audio a -16 LUFS...")
        with METRICS.step("audio_master"):
            master_audio(output_path)
    else:
        log.info("7/8 Masterización de audio omitida.")

    log.info("8/8 Ejecutando postflight técnico...")
    with METRICS.step("postflight"):
        postflight_issues = inspect_render(output_path, expected_duration_seconds)
        write_postflight_report(sidecar(output_path, "postflight.json"), postflight_issues)
    report_path = write_report(output_path, project_root=settings.project_root)
    if report_path:
        log.info(f"   Informe: {report_path}")
    enforce_postflight(postflight_issues)


def run_pipeline(request: RunRequest) -> Path:
    output_path = request.output_path.expanduser().resolve()
    script_path = request.script_path.expanduser().resolve()
    audio_path = request.audio_path.expanduser().resolve()
    request = RunRequest(**{**request.__dict__, "output_path": output_path, "script_path": script_path, "audio_path": audio_path})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    configure_log(sidecar(output_path, "log"), verbose=request.verbose)
    METRICS.reset(sidecar(output_path, "timing.json"), output=str(output_path), audio=str(audio_path))
    try:
        result = _run(request)
    except BaseException:
        METRICS.finish("error")
        raise
    METRICS.finish("ok")
    return result


def _run(request: RunRequest) -> Path:
    output_path = request.output_path
    script_path = request.script_path
    audio_path = request.audio_path

    if not request.skip_preflight:
        with METRICS.step("preflight"):
            _run_preflight(request)
    settings = load_settings()
    if not script_path.is_file():
        raise FileNotFoundError(f"No existe el guion: {script_path}")

    cache = JsonCache(enabled=not request.fresh)

    log.info("1/8 Transcribiendo audio con Whisper...")
    with METRICS.step("transcribe") as step:
        hits_before = METRICS.snapshot()["counters"].get("whisper.cache_hits", 0)
        transcript = transcribe_audio(audio_path, settings, cache=cache)
        step["cached"] = METRICS.snapshot()["counters"].get("whisper.cache_hits", 0) > hits_before
    log.info(f"   {len(transcript['words'])} palabras con timestamp")

    log.info("2/8 Segmentando el guion con DeepSeek...")
    with METRICS.step("segment") as step:
        hits_before = METRICS.snapshot()["counters"].get("segmentation.cache_hits", 0)
        script_text = script_path.read_text(encoding="utf-8")
        scenes = segment_script(script_text, transcript, settings, cache=cache)
        step["cached"] = METRICS.snapshot()["counters"].get("segmentation.cache_hits", 0) > hits_before
        step["scenes"] = len(scenes)
    log.info(f"   {len(scenes)} escenas")

    if request.overrides_path is not None:
        changed = apply_overrides(scenes, load_overrides(request.overrides_path))
        if changed:
            log.info(f"   Overrides aplicados a las escenas: {', '.join(str(number) for number in changed)}")

    run_id = output_path.stem
    assets_dir = settings.project_root / "public" / "pipeline-assets" / run_id
    _warn_if_assets_belong_to_other_audio(assets_dir, audio_path)
    audio_url = _copy_audio_to_public(audio_path, assets_dir, settings.project_root)

    log.info("3/8 Resolviendo material visual...")
    with METRICS.step("media"):
        scenes = fetch_media(
            scenes,
            settings,
            assets_dir=assets_dir,
            avatar_dir=request.avatar_dir,
            options=MediaOptions(
                third_party_enabled=not request.skip_third_party,
                concurrency=request.media_concurrency or settings.media_concurrency,
                download_stock=settings.download_stock,
                checkpoint_path=sidecar(output_path, "media.json"),
                resume=not request.fresh,
                redo_scenes=request.redo_scenes,
            ),
        )

    log.info("4/8 Ejecutando QA pre-render...")
    with METRICS.step("qa"):
        qa_issues = validate_scene_plan(scenes, transcript["duration_seconds"])
        write_qa_report(sidecar(output_path, "qa.json"), qa_issues)
    for issue in qa_issues:
        scene_label = f" escena {issue.scene_index}" if issue.scene_index is not None else ""
        log.info(f"   [{issue.level.upper()}]{scene_label} {issue.message}")

    # The timeline and the report are written even when QA blocks, so the
    # operator can see which scenes failed. props.json only exists for plans
    # that passed QA.
    timeline_path = sidecar(output_path, "timeline.json")
    write_timeline_manifest(scenes, timeline_path)
    report_path = write_report(output_path, project_root=settings.project_root)
    try:
        enforce_qa(qa_issues)
    except Exception:
        if report_path:
            log.info(f"   Informe con el detalle: {report_path}")
        raise

    props_path = sidecar(output_path, "props.json")
    log.info("5/8 Construyendo props.json...")
    with METRICS.step("props"):
        build_props(scenes, props_path, audio_url=audio_url)
    log.info(f"   Props: {props_path}")
    log.info(f"   Timeline: {timeline_path}")
    if report_path:
        log.info(f"   Informe: {report_path}")

    if request.skip_render:
        log.info("6/8 Render omitido por --skip-render.")
        return props_path

    _finish_render(
        output_path,
        props_path,
        settings,
        transcript["duration_seconds"],
        skip_audio_master=request.skip_audio_master,
        render_concurrency=request.render_concurrency,
    )
    log.info(f"Vídeo generado: {output_path}")
    return output_path


def _warn_if_assets_belong_to_other_audio(assets_dir: Path, audio_path: Path) -> None:
    """Two different videos sharing an output name would also share (and mix) assets."""

    previous = next(iter(sorted((assets_dir / "audio").glob("voice.*"))), None) if assets_dir.is_dir() else None
    if previous is None:
        return
    try:
        same = previous.stat().st_size == audio_path.stat().st_size
    except OSError:
        return
    if not same:
        log.warning(
            f"Aviso: {assets_dir} ya contiene los assets de otra narración. Si es otro vídeo, usa un "
            "--output con otro nombre para no mezclar material."
        )


def resolve_render_target(target: Path) -> tuple[Path, Path]:
    """Accept either the MP4 path or its ``.props.json``; return ``(output, props)``."""

    target = target.expanduser().resolve()
    if target.name.endswith(".props.json"):
        return target.with_name(target.name[: -len(".props.json")] + ".mp4"), target
    return target, sidecar(target, "props.json")


def render_only(
    target: Path,
    *,
    skip_audio_master: bool = False,
    render_concurrency: str | None = None,
    skip_preflight: bool = False,
    verbose: bool = False,
) -> Path:
    """Re-render from an existing props.json, then master and verify like a full run."""

    output_path, props_path = resolve_render_target(target)
    if not props_path.is_file():
        raise FileNotFoundError(
            f"No existe {props_path}. Genera primero el material con `python main.py <proyecto>`."
        )
    configure_log(sidecar(output_path, "log"), verbose=verbose)
    if not skip_preflight:
        checks = preflight.run_checks(
            need_third_party=False,
            need_render=True,
            need_audio_master=not skip_audio_master,
            output_path=output_path,
        )
        preflight.enforce(checks)
    settings = load_settings()

    props = read_json(props_path)
    if not isinstance(props, dict) or not isinstance(props.get("scenes"), list):
        raise ValueError(f"{props_path} no contiene un array 'scenes'.")
    scenes = [scene for scene in props["scenes"] if isinstance(scene, dict)]
    total_frames = sum(int(scene.get("durationInFrames", 0)) for scene in scenes)
    expected_duration_seconds = total_frames / REMOTION_FPS

    # Same gate as a full run: a hand-edited props.json must still pass QA
    # (including the five-second cap on third-party clips) before rendering.
    qa_issues = validate_scene_plan(scenes, expected_duration_seconds)  # type: ignore[arg-type]
    write_qa_report(sidecar(output_path, "qa.json"), qa_issues)
    enforce_qa(qa_issues)

    METRICS.reset(sidecar(output_path, "render-timing.json"), output=str(output_path), mode="render-only")
    try:
        _finish_render(
            output_path,
            props_path,
            settings,
            expected_duration_seconds,
            skip_audio_master=skip_audio_master,
            render_concurrency=render_concurrency,
        )
    except BaseException:
        METRICS.finish("error")
        raise
    METRICS.finish("ok")
    log.info(f"Vídeo generado: {output_path}")
    return output_path
