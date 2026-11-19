"""What would make the queue's videos fail half way, checked before they start (fase 2.5).

`main.preflight` already looked at the required keys, the disk, three binaries and a GET to youtube.com. This adds,
reusing `--doctor`'s checks (pipeline/chequeo.py, which the queue never called):

- blockers (the queue does not start; the watcher looks again in 30 min): the code does not import (pipeline/puerta),
  config.yaml does not load, a tool or Python package the stages need is missing, Remotion is not installed;
- warnings (said once per round, the queue goes on): a channel profile that does not load (only its videos fail),
  no voice key, no browser for Remotion yet (it would be downloaded in the middle of a render), every proxy down.

`prepare_assets(root)` (fase 4.10): what a video would otherwise download in the middle of its stages — Node packages
that package.json lists and node_modules lacks, Remotion's browser, the face models — fetched here, before the queue
starts, each with a time limit; what cannot be fetched is a warning. Behind a proxy those downloads were hangs at night.

`video_problems(ctx)`: the cheap check of one video right before its first stage that pays the proxy (sourcing):
what a later stage needs and is missing would otherwise be found after hours of searching and downloading.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def queue_problems(root: Path, imports: bool = True) -> tuple[list[str], list[str]]:
    from . import chequeo
    from .config import ConfigError
    from .context import RunContext, channel_profile

    blockers: list[str] = []
    warnings: list[str] = []
    if imports:
        from .puerta import import_problems

        errors, _ = import_problems(root)
        blockers += [f"el código no importa: {e}" for e in errors[:3]]
    try:
        RunContext.create("_preflight", root=root)
    except (ConfigError, ValueError) as error:
        blockers.append(f"config.yaml no se puede leer: {str(error)[:200]}")
    for check in (chequeo.tools,):
        try:
            for row in check(root):
                if row["level"] == chequeo.FAIL:
                    blockers.append(row["text"])
        except Exception as error:
            warnings.append(f"no se pudo revisar {check.__name__}: {str(error)[:120]}")
    for profile in sorted((root / "canales").glob("*.yaml")) if (root / "canales").is_dir() else []:
        try:
            channel_profile(root, profile.stem)
        except Exception as error:
            warnings.append(f"el perfil canales/{profile.name} no se puede leer ({str(error)[:120]}): "
                            "sus vídeos fallarán")
    try:
        for row in chequeo.keys(root):
            if row["level"] == chequeo.WARN and ("AI84" in row["text"] and "GENAIPRO" in row["text"]):
                warnings.append("sin clave de voz (AI84_API_KEY ni GENAIPRO_API_KEY): solo saldrán los vídeos con voz.mp3")
        for row in chequeo.youtube(root):
            if row["level"] == chequeo.FAIL:
                warnings.append(row["text"] + ": los vídeos con metraje esperarán")
    except Exception as error:
        warnings.append(f"no se pudo revisar claves/YouTube: {str(error)[:120]}")
    if not remotion_browser(root):
        warnings.append("Remotion aún no tiene navegador (node_modules/.remotion ni render.browser): lo descargará "
                        "en mitad del primer render; mejor ahora: npx remotion browser ensure")
    return blockers, warnings


def remotion_browser(root: Path) -> bool:
    from .context import RunContext

    try:
        configured = RunContext.create("_preflight", root=root).section("render").get("browser")
    except Exception:
        configured = None
    if configured and Path(str(configured)).exists():
        return True
    return (root / "node_modules" / ".remotion").is_dir() or Path("/opt/pw-browsers").is_dir()


def video_problems(ctx: Any) -> list[str]:
    """What this video will need after the proxy stages and is missing now."""

    problems = []
    if not ctx.env("OPENAI_API_KEY", required=False):
        problems.append("falta OPENAI_API_KEY (el juez de los clips): se buscaría material que nadie podría elegir")
    if not ctx.env("LLM_API_KEY", required=False):
        problems.append("falta LLM_API_KEY")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            problems.append(f"no encuentro {tool}")
    if not (ctx.root / "node_modules" / "remotion").is_dir():
        problems.append("no está node_modules/remotion (npm ci): el render fallaría tras horas de descargas")
    return problems


ASSET_TIMEOUT = 600


def prepare_assets(root: Path, run: Any = None) -> list[str]:
    """Download now what the stages would download on first use. Returns warnings (nothing blocks the queue here:
    `queue_problems` says what is still missing)."""

    import subprocess

    run = run or subprocess.run
    warnings: list[str] = []
    from .render import ensure_node_modules, missing_node_packages

    if missing_node_packages(root):
        try:
            ensure_node_modules(root)
        except Exception as error:
            warnings.append(f"no se pudieron instalar los paquetes de Node: {str(error)[:200]}")
    if (root / "node_modules" / "remotion").is_dir() and not remotion_browser(root):
        npx = shutil.which("npx") or "npx"
        print("Descargando el navegador de Remotion antes de la cola (npx remotion browser ensure)…")
        try:
            done = run([npx, "remotion", "browser", "ensure"], cwd=str(root), capture_output=True, text=True,
                       timeout=ASSET_TIMEOUT)
            if done.returncode != 0:
                warnings.append(f"Remotion no pudo descargar su navegador: {(done.stderr or done.stdout or '')[-200:]}")
        except (OSError, subprocess.TimeoutExpired) as error:
            warnings.append(f"Remotion no pudo descargar su navegador ({type(error).__name__})")
    try:
        from .context import RunContext
        from .identity import FACE_MODELS, model_path

        ctx = RunContext.create("_preflight", root=root)
        for name in FACE_MODELS:
            if model_path(ctx, name) is None:
                warnings.append(f"no se pudo descargar el modelo de caras {name}: se intentará en la etapa que lo use")
    except Exception as error:
        warnings.append(f"modelos de caras sin comprobar: {type(error).__name__}: {str(error)[:120]}")
    return warnings
