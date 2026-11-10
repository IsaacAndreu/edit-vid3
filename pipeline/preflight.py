"""Environment checks that run before any paid or slow work starts.

``python main.py doctor`` prints the full table. A normal run executes the same
checks (only the ones its flags need) and stops in under a second when
something that would break the run later is missing.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .config import ConfigError, Settings, load_settings
from .templates import PROJECT_ROOT, TemplateManifestError, load_manifest
from .transcribe import WHISPER_UPLOAD_LIMIT_BYTES


OK = "ok"
WARNING = "warning"
ERROR = "error"

YTDLP_STALE_DAYS = 90
MIN_FREE_DISK_BYTES = 2 * 1024**3
ASSETS_WARNING_BYTES = 20 * 1024**3


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


class PreflightError(RuntimeError):
    """Raised when a check that would break the run fails."""


def _tool_check(name: str, purpose: str, *, required: bool, fix: str) -> Check:
    path = shutil.which(name)
    if path:
        return Check(name, OK, path)
    return Check(name, ERROR if required else WARNING, f"no está en PATH ({purpose})", fix)


def _module_check(module: str, package: str, *, required: bool) -> Check:
    try:
        imported = importlib.import_module(module)
    except Exception as error:  # ImportError, or a broken install
        return Check(
            f"python:{package}",
            ERROR if required else WARNING,
            f"no se puede importar ({type(error).__name__})",
            "python -m pip install -r requirements.txt",
        )
    version = getattr(getattr(imported, "version", None), "__version__", None) or getattr(
        imported, "__version__", ""
    )
    return Check(f"python:{package}", OK, str(version or "instalado"))


def _ytdlp_freshness() -> Check | None:
    try:
        from yt_dlp.version import __version__ as version
    except Exception:
        return None
    try:
        year, month, day = (int(part) for part in version.split(".")[:3])
        age_days = (date.today() - date(year, month, day)).days
    except (ValueError, TypeError):
        return None
    if age_days > YTDLP_STALE_DAYS:
        return Check(
            "yt-dlp reciente",
            WARNING,
            f"versión {version}, de hace {age_days} días; YouTube cambia a menudo",
            'python -m pip install -U "yt-dlp[default]"',
        )
    return Check("yt-dlp reciente", OK, f"versión {version}")


def _node_dependencies_check(project_root: Path) -> Check:
    """Every package the render imports must be installed, not only the Remotion CLI."""

    required = ["@remotion/cli"]
    try:
        manifest = json.loads((project_root / "package.json").read_text(encoding="utf-8"))
        required += sorted(manifest.get("dependencies") or {})
    except (OSError, ValueError):
        pass
    missing = [name for name in required if not (project_root / "node_modules" / name).is_dir()]
    if missing:
        return Check(
            "dependencias de Remotion",
            ERROR,
            "faltan en node_modules: " + ", ".join(missing),
            "npm install",
        )
    return Check("dependencias de Remotion", OK, f"{len(required)} paquetes instalados")


def _directory_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def _writable_dir_check(directory: Path) -> Check:
    probe = directory
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not os.access(probe, os.W_OK):
        return Check("carpeta de salida", ERROR, f"sin permiso de escritura en {probe}", "Elige otro --output.")
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        return Check("carpeta de salida", OK, str(directory))
    if free < MIN_FREE_DISK_BYTES:
        return Check(
            "carpeta de salida",
            WARNING,
            f"solo quedan {free / 1024**3:.1f} GB libres en {probe}",
            "Libera espacio: python main.py clean",
        )
    return Check("carpeta de salida", OK, f"{directory} ({free / 1024**3:.0f} GB libres)")


def _api_checks(settings: Settings) -> list[Check]:
    """Free, read-only requests that prove each key is accepted."""

    import requests

    probes: list[tuple[str, str, dict[str, str], dict[str, Any]]] = [
        ("API DeepSeek", f"{settings.deepseek_base_url}/models", {"Authorization": f"Bearer {settings.llm_api_key}"}, {}),
        ("API OpenAI", "https://api.openai.com/v1/models", {"Authorization": f"Bearer {settings.openai_api_key}"}, {}),
        (
            "API Pexels",
            "https://api.pexels.com/v1/search",
            {"Authorization": settings.pexels_api_key},
            {"query": "test", "per_page": 1},
        ),
    ]
    checks: list[Check] = []
    for name, url, headers, params in probes:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.RequestException as error:
            checks.append(Check(name, ERROR, f"sin conexión ({type(error).__name__})", "Revisa la red o el proxy."))
            continue
        if response.status_code in {401, 403}:
            checks.append(Check(name, ERROR, f"clave rechazada (HTTP {response.status_code})", "Revisa la clave en .env."))
        elif response.status_code >= 400:
            checks.append(Check(name, WARNING, f"respondió HTTP {response.status_code}"))
        else:
            checks.append(Check(name, OK, "clave aceptada"))
    return checks


def run_checks(
    *,
    need_third_party: bool = True,
    need_render: bool = True,
    need_audio_master: bool = True,
    audio_path: Path | None = None,
    script_path: Path | None = None,
    output_path: Path | None = None,
    check_apis: bool = False,
    settings_loader: Callable[[], Settings] = load_settings,
    project_root: Path = PROJECT_ROOT,
) -> list[Check]:
    checks: list[Check] = []

    settings: Settings | None = None
    try:
        settings = settings_loader()
        checks.append(Check(".env", OK, "claves presentes"))
    except ConfigError as error:
        checks.append(Check(".env", ERROR, str(error), "cp .env.example .env y rellena las claves."))

    try:
        manifest = load_manifest()
        checks.append(Check("manifiesto de plantillas", OK, f"{len(manifest.templates)} plantillas"))
    except TemplateManifestError as error:
        checks.append(Check("manifiesto de plantillas", ERROR, str(error)))

    checks.append(_module_check("openai", "openai", required=True))
    checks.append(_module_check("requests", "requests", required=True))
    checks.append(_module_check("dotenv", "python-dotenv", required=True))

    ffmpeg_needed = need_third_party or (need_render and need_audio_master)
    checks.append(
        _tool_check(
            "ffprobe",
            "duración del audio, clips y postflight",
            required=need_render or need_third_party,
            fix="Instala ffmpeg (incluye ffprobe).",
        )
    )
    checks.append(
        _tool_check(
            "ffmpeg",
            "clips de YouTube, contact sheets y master de audio",
            required=ffmpeg_needed,
            fix="Instala ffmpeg, o usa --skip-third-party y --skip-audio-master.",
        )
    )

    if need_third_party:
        checks.append(_module_check("yt_dlp", "yt-dlp", required=True))
        freshness = _ytdlp_freshness()
        if freshness:
            checks.append(freshness)
        checks.append(
            _tool_check(
                "deno",
                "yt-dlp lo usa para resolver los desafíos de YouTube",
                required=True,
                fix="Instala Deno (https://deno.com) o usa --skip-third-party.",
            )
        )

    if need_render:
        checks.append(_tool_check("node", "render de Remotion", required=True, fix="Instala Node.js 18 o superior."))
        checks.append(_tool_check("npx", "render de Remotion", required=True, fix="Instala Node.js (incluye npx)."))
        checks.append(_node_dependencies_check(project_root))

    if script_path is not None:
        if script_path.is_file():
            checks.append(Check("guion", OK, str(script_path)))
        else:
            checks.append(Check("guion", ERROR, f"no existe {script_path}"))
    if audio_path is not None:
        if not audio_path.is_file():
            checks.append(Check("voz", ERROR, f"no existe {audio_path}"))
        else:
            size = audio_path.stat().st_size
            detail = f"{audio_path} ({size / 1_048_576:.1f} MB)"
            if size > WHISPER_UPLOAD_LIMIT_BYTES and not shutil.which("ffmpeg"):
                checks.append(
                    Check("voz", ERROR, detail + "; supera los 25 MB de Whisper", "Instala ffmpeg o conviértela a MP3.")
                )
            elif size > WHISPER_UPLOAD_LIMIT_BYTES:
                checks.append(Check("voz", OK, detail + "; se subirá una copia comprimida a Whisper"))
            else:
                checks.append(Check("voz", OK, detail))
    if output_path is not None:
        checks.append(_writable_dir_check(output_path.parent))

    assets_root = project_root / "public" / "pipeline-assets"
    if assets_root.is_dir():
        size = _directory_size(assets_root)
        if size > ASSETS_WARNING_BYTES:
            checks.append(
                Check(
                    "assets acumulados",
                    WARNING,
                    f"public/pipeline-assets ocupa {size / 1024**3:.1f} GB",
                    "python main.py clean",
                )
            )

    if check_apis and settings is not None:
        checks.extend(_api_checks(settings))
    return checks


def format_checks(checks: list[Check]) -> str:
    marks = {OK: "✓", WARNING: "!", ERROR: "✗"}
    width = max((len(check.name) for check in checks), default=0)
    lines = []
    for check in checks:
        line = f"  {marks.get(check.status, '?')} {check.name.ljust(width)}  {check.detail}"
        if check.status != OK and check.fix:
            line += f"\n    {' ' * width}  → {check.fix}"
        lines.append(line)
    return "\n".join(lines)


def enforce(checks: list[Check]) -> None:
    errors = [check for check in checks if check.status == ERROR]
    if errors:
        raise PreflightError(
            "El entorno no está listo; el run fallaría más adelante:\n"
            + format_checks(errors)
            + "\nEjecuta `python main.py doctor` para ver todas las comprobaciones."
        )
