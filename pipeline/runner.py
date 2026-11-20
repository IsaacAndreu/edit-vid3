"""Stage orchestration: idempotent, resumable, no in-memory state between stages.

A stage is skipped when its outputs exist, validate, and were produced from the
same inputs (files + the stage's config section). The fingerprint lives in
work/<slug>/.stages/<stage>.json, so changing guion.txt or config.yaml
automatically invalidates the affected stage, and a re-run stage invalidates the
stages that read its output.
"""

from __future__ import annotations

from contextlib import nullcontext

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import (align, analysis, coldopen, factcheck, fallback, ingest, judge, package, people, planner, qa, render, revisor,
               shorts, sourcing, timeline)
from .context import RunContext
from .locks import turn


@dataclass(frozen=True)
class Stage:
    name: str
    outputs: Callable[[RunContext], list[Path]]
    inputs: Callable[[RunContext], list[Path]]
    run: Callable[[RunContext], None] | None
    validate: Callable[[RunContext], bool] | None = None
    config_sections: tuple[str, ...] = ()
    retry_if: Callable[[RunContext], bool] | None = None   # True → outputs are valid but worth redoing


def _work(*names: str) -> Callable[[RunContext], list[Path]]:
    return lambda ctx: [ctx.work_dir / name for name in names]


# Order matters: each stage reads the outputs of the stages before it.
STAGES: list[Stage] = [
    Stage("factcheck", _work(factcheck.OUTPUT), factcheck.inputs, factcheck.run, factcheck.validate, ("factcheck",)),
    Stage("align", _work(align.OUTPUT), align.inputs, align.run, align.validate, ("align",)),
    Stage("planner", _work(planner.OUTPUT), planner.inputs, planner.run, planner.validate, ("planner",)),
    Stage("sourcing", _work(sourcing.OUTPUT), sourcing.inputs, sourcing.run, sourcing.validate, ("sourcing", "content"), sourcing.retry_if),
    Stage("analysis", _work(analysis.OUTPUT), analysis.inputs, analysis.run, analysis.validate, ("analysis",)),
    Stage("judge", _work(judge.OUTPUT), judge.inputs, judge.run, judge.validate, ("judge", "content")),
    Stage("ingest", _work(ingest.OUTPUT), ingest.inputs, ingest.run, ingest.validate, ("ingest",), ingest.retry_if),
    Stage("people", _work(people.OUTPUT), people.inputs, people.run, people.validate, ("people", "sourcing")),
    Stage("fallback", _work(fallback.OUTPUT), fallback.inputs, fallback.run, fallback.validate, ("fallback", "content")),
    Stage("coldopen", _work(coldopen.OUTPUT), coldopen.inputs, coldopen.run, coldopen.validate, ("timeline", "judge", "quotes")),
    Stage("timeline", _work(timeline.OUTPUT), timeline.inputs, timeline.run, timeline.validate, ("timeline", "video", "graphics", "brand")),
    # bloque 3.3 (revisor.enabled, off): the edit reviewed before the render; its config section is not in the
    # fingerprint, so turning it on changes the videos that reach this stage from then on, never one already past it
    Stage("revisor", lambda ctx: [ctx.out_dir / revisor.OUT_DIR / "revisor.json"], revisor.stage_inputs, revisor.stage_run,
          None, ()),
    Stage("qa", lambda ctx: [ctx.out_dir / "qa" / "report.md", ctx.out_dir / "manifest.json", ctx.out_dir / "creditos.txt"],
          qa.inputs, qa.run, qa.validate, ("qa", "judge")),
    Stage("render", lambda ctx: [ctx.out_dir / render.OUTPUT], render.inputs, render.run, render.validate, ("render", "video")),
    Stage("shorts", shorts.outputs, shorts.inputs, shorts.run, shorts.validate,
          ("shorts",)),
    Stage("package", package.outputs, package.inputs, package.run,
          package.validate, ("package",)),
]
STAGE_NAMES = [stage.name for stage in STAGES]


class StageNotImplemented(RuntimeError):
    pass


def _hash_path(digest: "hashlib._Hash", path: Path) -> None:
    digest.update(str(path.name).encode())
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                digest.update(str(child.relative_to(path)).encode())
                digest.update(child.read_bytes())
    elif path.is_file():
        digest.update(path.read_bytes())
    else:
        digest.update(b"<missing>")


# How fast or by which road, never what: changing these must not make a stage run again (raising the YouTube
# downloads at once on 05-10 re-ran every video's searches — and that load got the connection blocked).
SPEED_KEYS = frozenset({
    "parallel", "concurrency", "concurrency_with_accounts", "min_interval", "rate_backoff", "sleep_requests",
    "account_switch_pause", "rate_limit", "proxy", "proxies", "proxy_rest_minutes", "proxy_bot_rest_minutes",
    "player_client", "force_ipv4", "cookies", "cookies_on_bot",
    "cookies_file", "cookies_dir", "cookies_from_browser", "browser_accounts", "po_token", "pot_provider_url",
    "pot_keep_clients", "batch_size", "precompute_during_sourcing", "browser_executable", "timeout_seconds",
    "bot_quarantine_minutes", "bot_recovery_hours", "api_overflow", "requests_per_hour", "bot_breaker_videos",
    "bot_breaker_minutes", "bot_breaker_share", "range_stall_seconds", "region", "metadata_proxy", "metadata_proxy_light", "metadata_proxy_mb_per_request",
    "metadata_proxy_usd_per_gb",
    "metadata_proxy_retries", "query_merge", "max_details_per_shot",
    "proxy_session_minutes", "proxy_session_rotations", "proxy_session_suffix", "info_expiry_margin_minutes",   # residential proxy sessions
    "player_client_residential", "max_fps", "proxy_usd_per_gb", "whole_max_minutes_residential", "whole_max_mb_residential", "prefetch_whole_residential",
    "refused_hours_residential", "cpu_threads",
    "ideas",                  # planner.ideas: turned on in a channel, only the videos planned from then on change
    "timeout_retries_residential",
    "whole_min_rate_kb", "whole_deadline_seconds_per_mb", "fragment_retries", "byte_ranges",
    "pace_per_session", "session_min_interval", "session_concurrency", "proxy_connections_max",
    "captions_min_interval", "captions_retry_minutes", "player_skip", "overflow_searches_per_hour",
    "hls_segment_workers", "hls_segment_retries", "hls_format_test", "transient_retries", "youtube_update_probe",
    "hd_windows_top",   # analysis: the same windows, only in HD: never a reason to analyse again     # plazos de las descargas enteras
    "max_height",       # ingest: the HD clips already downloaded are not downloaded again at the new height
    # the judge outside the hook (judge.py): only for the shots judged from now on, never a reason to judge again
    "rounds_rest", "model_rest", "usd_per_mtok_rest", "lessons_refresh",
})


def _without_speed(value):
    if isinstance(value, dict):
        return {k: _without_speed(v) for k, v in value.items() if k not in SPEED_KEYS}
    if isinstance(value, list):
        return [_without_speed(v) for v in value]
    return value


def _stat_signature(paths: list[Path], sections: list[str]) -> str:
    """Names, sizes and modification times of every input file (no bytes read) plus the config text: when it is the
    same as last time, so are the bytes, and the fingerprint is too."""

    digest = hashlib.sha256()
    for path in paths:
        digest.update(f"\0{path}".encode())
        children = sorted(c for c in path.rglob("*") if c.is_file()) if path.is_dir() else [path] if path.is_file() else []
        for child in children:
            info = child.stat()
            digest.update(f"|{child}|{info.st_size}|{info.st_mtime_ns}|{info.st_ino}".encode())
    for text in sections:
        digest.update(text.encode())
    return digest.hexdigest()


_FINGERPRINTS: dict[tuple[str, str], tuple[str, str]] = {}     # (work dir + stage, legacy) → (signature, fingerprint)
_FINGERPRINTS_LOCK = threading.Lock()


def fingerprint(ctx: RunContext, stage: Stage, legacy: bool = False) -> str:
    """What a stage's result depends on: its input files and its config sections, minus the speed knobs
    (`legacy`: with them, as markers written before SPEED_KEYS existed were hashed).

    Fase 4.4: the bytes are read only when a file's name, size or modification time changed since the last
    fingerprint of this stage (kept in work/<slug>/.stages/huellas.cache): the stage's own inputs include whole
    folders (remotion/, assets/) re-read on every check. The value is the same as before: markers stay valid."""

    paths = list(stage.inputs(ctx))
    sections = [json.dumps(ctx.section(name) if legacy else _without_speed(ctx.section(name)), sort_keys=True)
                for name in stage.config_sections]
    work_dir, name = getattr(ctx, "work_dir", None), getattr(stage, "name", None)
    key = f"{name}{'@legacy' if legacy else ''}"
    store = Path(work_dir or ".") / ".stages" / "huellas.cache"     # not .json: readers take every .json as a marker
    try:
        signature = _stat_signature(paths, sections) if work_dir and name else ""   # no work folder: plain hash
    except OSError:
        signature = ""
    with _FINGERPRINTS_LOCK:
        memo = _FINGERPRINTS.get((str(work_dir), key))
        if signature and memo and memo[0] == signature:
            return memo[1]
        try:
            saved = json.loads(store.read_text("utf-8")).get(key) or {}
        except (OSError, ValueError, AttributeError):
            saved = {}
        if signature and saved.get("signature") == signature and saved.get("fingerprint"):
            _FINGERPRINTS[(str(work_dir), key)] = (signature, str(saved["fingerprint"]))
            return str(saved["fingerprint"])
    digest = hashlib.sha256()
    for path in paths:
        _hash_path(digest, path)
    for text in sections:
        digest.update(text.encode())
    value = digest.hexdigest()
    if signature and signature == _stat_signature(paths, sections):     # nothing changed while it was being read
        with _FINGERPRINTS_LOCK:
            _FINGERPRINTS[(str(work_dir), key)] = (signature, value)
            try:
                from .fileio import atomic_write_text

                try:
                    every = json.loads(store.read_text("utf-8"))
                except (OSError, ValueError):
                    every = {}
                every = every if isinstance(every, dict) else {}
                every[key] = {"signature": signature, "fingerprint": value}
                store.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(store, json.dumps(every, indent=1))
            except OSError:
                pass
    return value


def mark_done(ctx: RunContext, stage: Stage, seconds: float = 0.0) -> None:
    """A stage done again from inside another one (the reviewer redoing the fill-in and the edit): its marker with
    today's fingerprint, so the next run does not do it a third time."""

    marker = _marker(ctx, stage)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"stage": stage.name, "inputsHash": fingerprint(ctx, stage),
                                  "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "seconds": round(seconds, 1), "redoneBy": "revisor"}, indent=2) + "\n", encoding="utf-8")


def _turn_group(ctx: RunContext, stage: str) -> str:
    """Whisper through the OpenAI API uses no CPU here: that transcription takes no turn (several at once)."""

    if stage == "align" and str(ctx.section("align").get("provider", "local")) == "openai":
        return "align-api"
    return stage


def _marker(ctx: RunContext, stage: Stage) -> Path:
    return ctx.work_dir / ".stages" / f"{stage.name}.json"


def is_up_to_date(ctx: RunContext, stage: Stage) -> bool:
    marker = _marker(ctx, stage)
    if not marker.is_file() or not all(path.exists() for path in stage.outputs(ctx)):
        return False
    try:
        recorded_marker = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    recorded = recorded_marker.get("inputsHash")
    from . import sin_youtube

    if recorded_marker.get("withoutYouTube") and not sin_youtube.active():
        # done during YouTube's pause: again now, and inside the stage only what missed YouTube is redone
        print(f"   {stage.name}: se hizo sin YouTube; se rehace con YouTube (solo lo que faltaba)")
        return False
    if recorded != fingerprint(ctx, stage) and recorded != fingerprint(ctx, stage, legacy=True):
        return False
    if stage.validate is not None:
        try:
            if not stage.validate(ctx):
                return False
        except Exception as error:  # an invalid output simply means "run again"
            print(f"   Salida de {stage.name} no válida ({error}); se regenera.")
            return False
    if stage.retry_if is not None and stage.retry_if(ctx):
        print(f"   {stage.name}: la última ejecución quedó incompleta; se reintenta.")
        return False
    return True


def _failures_path(ctx: RunContext, stage: Stage) -> Path:
    # .jsonl, not .json: the readers of .stages/*.json (tiempos, the studio) take every .json as a stage marker
    return ctx.work_dir / ".stages" / f"{stage.name}.fallos.jsonl"


def _record_failure(ctx: RunContext, stage: Stage, error: BaseException, queued: float, started: float | None) -> None:
    """A failed (or interrupted) attempt of a stage, with what it cost: the marker is only written on success, so
    without this the hours of an attempt that died (11 videos, 3.5-7 h each, on 17-11) were invisible."""

    now = time.monotonic()
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": type(error).__name__,
           "detail": str(error).replace("\n", " ")[:300],
           "waitSeconds": round((started or now) - queued, 1), "seconds": round(now - started, 1) if started else 0.0}
    try:
        path = _failures_path(ctx, stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _failed_attempts(ctx: RunContext, stage: Stage) -> dict:
    rows = []
    try:
        for line in _failures_path(ctx, stage).read_text("utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return {}
    if not rows:
        return {}
    return {"failedAttempts": rows[-20:], "failedSeconds": round(sum(float(r.get("seconds") or 0) for r in rows), 1),
            "failedWaitSeconds": round(sum(float(r.get("waitSeconds") or 0) for r in rows), 1)}


PROXY_STAGES = ("sourcing", "analysis", "ingest", "fallback")   # the stages that ask YouTube through the proxy


def run_stages(
    ctx: RunContext,
    *,
    force: set[str] | None = None,
    until: str | None = None,
    review: bool = False,
) -> list[str]:
    """Run stages in order. Returns the names of the stages actually executed."""

    force = set(force or ())
    unknown = force - set(STAGE_NAMES) - {"all"}
    if unknown:
        raise ValueError(f"Etapa desconocida en --force: {', '.join(sorted(unknown))}. Opciones: {', '.join(STAGE_NAMES)}")
    if until is not None and until not in STAGE_NAMES:
        raise ValueError(f"Etapa desconocida en --until: {until}. Opciones: {', '.join(STAGE_NAMES)}")
    last = "qa" if review and (until is None or STAGE_NAMES.index(until) > STAGE_NAMES.index("qa")) else until

    executed: list[str] = []
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    from . import budget

    spent_before = budget.video_spent(ctx.work_dir)      # budget.per_video_usd counts this attempt only
    budget.ATTEMPT_START[str(ctx.work_dir)] = spent_before   # budget.guard: the same cap inside judge and fallback
    from . import feedback, sin_youtube

    offline = sin_youtube.active()                       # modo sin YouTube: YouTube's pause lasts (sin_youtube.py)
    learned = feedback.load_learned(ctx.root)            # channels your «Errores» labels taught it to avoid
    if learned:
        print(f"Canales de YouTube bloqueados por tus correcciones: {', '.join(learned)}")
    checked = [False]                     # the per-video check before the first paid stage, once
    executed_lock = threading.Lock()

    def execute(number: int, stage: Stage, track: bool = True) -> None:
        label = f"[{number}/{len(STAGES)}] {stage.name}"
        forced = "all" in force or stage.name in force
        if not forced and is_up_to_date(ctx, stage):
            print(f"{label}: al día, se salta.")
            return
        if stage.run is None:
            raise StageNotImplemented(f"La etapa '{stage.name}' todavía no está implementada.")
        budget.check_video(ctx.root, ctx.config, ctx.work_dir, ctx.materials_dir, spent_before)
        from . import stickman

        if stage.name in PROXY_STAGES and not offline:
            if not checked[0] and not (stage.name in stickman.SKIP and stickman.drawn(ctx)):
                # what a later stage will need and is missing: found now, not after hours of paid downloads
                from .preflight import video_problems

                problems = video_problems(ctx)
                if problems:
                    raise RuntimeError("No empiezo a gastar proxy: " + "; ".join(problems))
                checked[0] = True
            budget.check_proxy(ctx.root, ctx.config, ctx.slug)   # its owner's GB a day: it waits for tomorrow here
        print(f"{label}: ejecutando… ({datetime.now():%H:%M})")
        # what the web studio shows as «haciendo ahora»; a stage running in the background keeps its own file
        current = ctx.work_dir / ("current.json" if track else f".current-{stage.name}.json")
        state = {"stage": stage.name, "number": number, "of": len(STAGES), "pid": os.getpid(),
                 "started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "waiting": True}
        current.write_text(json.dumps(state), encoding="utf-8")
        from .housekeeping import Sampler

        from . import stickman

        skipped = stage.name in stickman.SKIP and stickman.drawn(ctx)    # drawn in code: no footage
        queued = time.monotonic()
        started = None
        try:
            # a drawn video skips these stages without queueing for the network turn (atlas1pt waited behind
            # other videos' searches with «esperando turno de red» for a stage it never runs)
            with nullcontext() if skipped else turn(ctx.root, _turn_group(ctx, stage.name), ctx.slug):
                started = time.monotonic()
                waited = started - queued                   # the turn's wait, never counted as the stage's work
                state.pop("waiting", None)
                current.write_text(json.dumps({**state, "waitSeconds": round(waited, 1),
                                               "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                                   encoding="utf-8")
                with Sampler() as usage:                    # peak RAM / CPU of the machine during the stage
                    if skipped:
                        stickman.skip(ctx, stage.name)
                    else:
                        stage.run(ctx)
            if stage.validate is not None:
                stage.validate(ctx)
        except BaseException as error:
            _record_failure(ctx, stage, error, queued, started)
            # The stage stopped (an error, waiting for the API quota…): the file stays for the failure notice
            # (which stage), marked as ended, or the studio would show it «haciendo» while the queue (the same
            # process, still alive) goes on with other videos — mega11 showed «Buscar material desde hace 6 h».
            try:
                current.write_text(json.dumps({**json.loads(current.read_text("utf-8")),
                                               "ended": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                                   encoding="utf-8")
            except (OSError, ValueError):
                pass
            raise
        marker = _marker(ctx, stage)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "stage": stage.name,
                    "inputsHash": fingerprint(ctx, stage),
                    "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "seconds": round(time.monotonic() - started, 1),
                    "waitSeconds": round(waited, 1),
                    **_failed_attempts(ctx, stage),
                    **usage.fields(),
                    **({"withoutYouTube": True} if offline and stage.name in sin_youtube.STAGES else {}),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        current.unlink(missing_ok=True)
        _failures_path(ctx, stage).unlink(missing_ok=True)       # now inside the marker
        with executed_lock:
            executed.append(stage.name)
        spent = time.monotonic() - started
        print(f"{label}: hecho en {spent:.1f} s" + (f" ({spent / 60:.0f} min)" if spent >= 120 else ""))

    # speed.parallel_stages (on): factcheck, which feeds no other stage, runs beside align and planner, and is waited
    # for before the first paid stage (when it holds a video, nothing was spent). Same markers. Not people: its plan B
    # takes frames of the protagonist's HD clips already downloaded (the library ingest fills), so moving it before
    # ingest would change what it finds.
    parallel = bool(ctx.section("speed").get("parallel_stages", True))
    background: dict[str, tuple[threading.Thread, list[BaseException]]] = {}

    def launch(name: str) -> None:
        index = STAGE_NAMES.index(name) if name in STAGE_NAMES else -1
        if index < 0 or name in background or (last is not None and STAGE_NAMES.index(last) < index):
            return
        errors: list[BaseException] = []

        def target() -> None:
            try:
                execute(index + 1, STAGES[index], track=False)
            except BaseException as error:        # handed to the main thread where it is waited for
                errors.append(error)

        thread = threading.Thread(target=target, name=f"etapa-{name}", daemon=True)
        background[name] = (thread, errors)
        thread.start()

    def join(name: str) -> bool:
        """Wait for a stage started in the background; True if it was (it must not run again here)."""

        if name not in background:
            return False
        thread, errors = background.pop(name)
        thread.join()
        own = ctx.work_dir / f".current-{name}.json"
        if errors:
            if own.is_file():                     # the failure notice and the studio name the stage that stopped
                own.replace(ctx.work_dir / "current.json")
            raise errors[0]
        own.unlink(missing_ok=True)
        return True

    warming: list[threading.Thread] = []

    def warm_package() -> None:
        """5.3: package's outside requests (titles LLM, concept pictures) asked while the video renders."""

        if "package" not in STAGE_NAMES or (last is not None and STAGE_NAMES.index(last) < STAGE_NAMES.index("package")):
            return
        stage = STAGES[STAGE_NAMES.index("package")]
        if not ("all" in force or "package" in force) and is_up_to_date(ctx, stage):
            return

        def target() -> None:
            try:
                package.prepare(ctx)
            except Exception as error:            # package itself asks again and fails, or not, there
                print(f"   (títulos por adelantado no disponibles: {str(error)[:120]})")

        thread = threading.Thread(target=target, name="adelanto-package", daemon=True)
        warming.append(thread)
        thread.start()

    try:
        for number, stage in enumerate(STAGES, start=1):
            started_here = False
            if parallel and stage.name == "render":
                warm_package()
            if stage.name == "package":
                for thread in warming:
                    thread.join()
            if parallel and stage.name == "factcheck" and "align" in STAGE_NAMES and stage.name != last:
                launch("factcheck")               # waited for before the first paid stage, not here
                started_here = "factcheck" in background
            elif stage.name in PROXY_STAGES and "factcheck" in background:
                join("factcheck")                 # before the first paid stage
            if not started_here and not join(stage.name):
                execute(number, stage)
            if offline and stage.name == "coldopen":
                sin_youtube.gate(ctx)        # worse than the channel's usual without YouTube: it waits (WaitingForYouTube)
            if stage.name == last:
                if review and stage.name == "qa":
                    print("Revisión: pipeline detenido tras la QA (--review). Revisa out/<slug>/qa/ y relanza sin --review.")
                break
        for name in list(background):            # stopped before their join point (--until): theirs too
            join(name)
    finally:
        for name in list(background):            # never left running behind the video
            thread, _ = background.pop(name)
            thread.join()
        for thread in warming:
            thread.join()
    executed.sort(key=lambda name: STAGE_NAMES.index(name) if name in STAGE_NAMES else len(STAGE_NAMES))
    if stage is STAGES[-1] and not (review and last == "qa"):
        # every stage through, the last one included: the video is finished (housekeeping.is_done)
        (ctx.out_dir / render.IN_PROGRESS).unlink(missing_ok=True)
    return executed
