"""Stage orchestration: idempotent, resumable, no in-memory state between stages.

A stage is skipped when its outputs exist, validate, and were produced from the
same inputs (files + the stage's config section). The fingerprint lives in
work/<slug>/.stages/<stage>.json, so changing guion.txt or config.yaml
automatically invalidates the affected stage, and a re-run stage invalidates the
stages that read its output.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import align, analysis, coldopen, factcheck, fallback, ingest, judge, package, people, planner, qa, render, shorts, sourcing, timeline
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


def fingerprint(ctx: RunContext, stage: Stage) -> str:
    digest = hashlib.sha256()
    for path in stage.inputs(ctx):
        _hash_path(digest, path)
    for section in stage.config_sections:
        digest.update(json.dumps(ctx.section(section), sort_keys=True).encode())
    return digest.hexdigest()


def _marker(ctx: RunContext, stage: Stage) -> Path:
    return ctx.work_dir / ".stages" / f"{stage.name}.json"


def is_up_to_date(ctx: RunContext, stage: Stage) -> bool:
    marker = _marker(ctx, stage)
    if not marker.is_file() or not all(path.exists() for path in stage.outputs(ctx)):
        return False
    try:
        recorded = json.loads(marker.read_text(encoding="utf-8")).get("inputsHash")
    except (OSError, json.JSONDecodeError):
        return False
    if recorded != fingerprint(ctx, stage):
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
    for number, stage in enumerate(STAGES, start=1):
        label = f"[{number}/{len(STAGES)}] {stage.name}"
        forced = "all" in force or stage.name in force
        if not forced and is_up_to_date(ctx, stage):
            print(f"{label}: al día, se salta.")
        else:
            if stage.run is None:
                raise StageNotImplemented(f"La etapa '{stage.name}' todavía no está implementada.")
            print(f"{label}: ejecutando… ({datetime.now():%H:%M})")
            current = ctx.work_dir / "current.json"          # what the web studio shows as «haciendo ahora»
            current.write_text(json.dumps({"stage": stage.name, "number": number, "of": len(STAGES),
                                           "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                               encoding="utf-8")
            from .housekeeping import Sampler

            with turn(ctx.root, stage.name, ctx.slug):     # two videos at once in the queue: one on the network, one on the CPU
                started = time.monotonic()
                with Sampler() as usage:                    # peak RAM / CPU of the machine during the stage
                    stage.run(ctx)
            if stage.validate is not None:
                stage.validate(ctx)
            marker = _marker(ctx, stage)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps(
                    {
                        "stage": stage.name,
                        "inputsHash": fingerprint(ctx, stage),
                        "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "seconds": round(time.monotonic() - started, 1),
                        **usage.fields(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            current.unlink(missing_ok=True)
            executed.append(stage.name)
            spent = time.monotonic() - started
            print(f"{label}: hecho en {spent:.1f} s" + (f" ({spent / 60:.0f} min)" if spent >= 120 else ""))
        if stage.name == last:
            if review and stage.name == "qa":
                print("Revisión: pipeline detenido tras la QA (--review). Revisa out/<slug>/qa/ y relanza sin --review.")
            break
    return executed
