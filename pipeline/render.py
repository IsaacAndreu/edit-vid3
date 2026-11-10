"""Remotion render invocation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import Settings
from .timing import METRICS


COMPOSITION_ID = "YoutubeVideo"
ENTRY_POINT = "src/index.ts"
BROWSER_ENV = "REMOTION_BROWSER_EXECUTABLE"


class RenderError(RuntimeError):
    """Remotion could not be started or exited with an error."""


def npx_executable() -> str:
    return "npx.cmd" if os.name == "nt" else "npx"


def render_command(
    props_path: Path,
    output_path: Path,
    *,
    concurrency: str | None = None,
) -> list[str]:
    command = [
        npx_executable(),
        "remotion",
        "render",
        ENTRY_POINT,
        COMPOSITION_ID,
        str(output_path),
        "--props",
        str(props_path),
    ]
    if concurrency:
        command += ["--concurrency", str(concurrency)]
    browser = os.getenv(BROWSER_ENV, "").strip()
    if browser:
        command += ["--browser-executable", browser]
    return command


def render_remotion(
    props_path: Path,
    output_path: Path,
    settings: Settings,
    *,
    concurrency: str | None = None,
) -> None:
    command = render_command(props_path, output_path, concurrency=concurrency or settings.render_concurrency)
    retry_hint = f"python main.py render {output_path}"
    try:
        with METRICS.timed("render.remotion"):
            subprocess.run(command, cwd=settings.project_root, check=True)
    except FileNotFoundError as error:
        raise RenderError(
            "No se encontró npx. Instala Node.js y ejecuta `npm install`. "
            f"El material ya está resuelto; después relanza solo el render con: {retry_hint}"
        ) from error
    except subprocess.CalledProcessError as error:
        raise RenderError(
            f"Remotion terminó con código {error.returncode} (el detalle está justo encima). "
            f"El material ya está resuelto en {props_path}; tras corregirlo relanza solo el render con: "
            f"{retry_hint}"
        ) from error


def studio_command(props_path: Path | None = None) -> list[str]:
    command = [npx_executable(), "remotion", "studio", ENTRY_POINT]
    if props_path is not None:
        command += ["--props", str(props_path)]
    return command
