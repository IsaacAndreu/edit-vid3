"""`python main.py --probar-youtube`: why YouTube downloads are slow on this machine, in about a minute.

It prints yt-dlp's version, the challenge solver (yt-dlp-ejs) and the JavaScript runtime it needs, then
downloads the same 10-second piece of a public video exactly like the night queue does — first with your
cookies, then without — and times it. The verdict says which of the usual causes it is and what to run.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .context import RunContext

TEST_VIDEO = "aqz-KE-bpKQ"          # Big Buck Bunny (Blender Foundation, public, stable, up to 4K)
TEST_RANGE = (60.0, 70.0)
FORMAT = "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/b[height<=1080]"
GOOD, SLOW = 12.0, 30.0              # seconds for the 10-s piece: the cloud does it in ~4 s


def versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    def get(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return ""

    runtime = next((name for name in ("deno", "node", "bun") if shutil.which(name)), "")
    return {"yt-dlp": get("yt-dlp"), "ejs": get("yt-dlp-ejs"), "js": runtime}


def _try(ctx: RunContext, sets: list[Any], label: str) -> dict[str, Any]:
    from .sourcing.youtube import WARNING_COUNTS, YouTubeSource

    cfg = dict(ctx.section("sourcing").get("youtube", {}))
    WARNING_COUNTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        source = YouTubeSource(root=ctx.root, cache_dir=Path(tmp), config=cfg, cookie_sets=sets)
        began = time.monotonic()
        try:
            path = source.download_range(TEST_VIDEO, *TEST_RANGE, fmt=FORMAT, prefix="probe")
            size = path.stat().st_size
            error = ""
        except Exception as exc:     # the verdict explains it
            size, error = 0, f"{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            source.close()
        seconds = time.monotonic() - began
        phases = {action: round(total, 1) for action, (_, total) in source.stats.items()}
    result = {"label": label, "seconds": round(seconds, 1), "mb": round(size / 1e6, 1), "error": error,
              "warnings": dict(WARNING_COUNTS), "phases": phases}
    speed = f"{result['mb'] / seconds:.1f} MB/s" if size and seconds else "—"
    detail = f"{seconds:.1f} s para 10 s de vídeo ({result['mb']} MB, {speed})"
    print(f"   {label}: {'ERROR ' + error if error else detail}")
    if phases:
        print("      por fases: " + " · ".join(f"{k} {v} s" for k, v in phases.items()))
    return result


def connection_speed() -> float | None:
    """MB/s downloading 10 MB from a CDN that is not YouTube: is the line itself slow?"""

    import requests

    try:
        began = time.monotonic()
        response = requests.get("https://speed.cloudflare.com/__down?bytes=10000000", timeout=120)
        response.raise_for_status()
        return round(len(response.content) / 1e6 / (time.monotonic() - began), 1)
    except Exception:
        return None


def verdict(info: dict[str, str], runs: list[dict[str, Any]]) -> list[str]:
    """What to do, most likely cause first."""

    out: list[str] = []
    line = info.get("line")
    fastest_run = min((r for r in runs if not r["error"]), key=lambda r: r["seconds"], default=None)
    if fastest_run and fastest_run["seconds"] > SLOW:
        phases = fastest_run.get("phases") or {}
        waited = phases.get("espera por límite", 0)
        download = phases.get("download", 0)
        info_time = sum(v for k, v in phases.items() if k not in ("download", "espera por límite"))
        if waited > fastest_run["seconds"] / 2:
            out.append(f"Casi todo el tiempo ({waited:.0f} s) fue esperar porque YouTube limita a tu conexión (429). "
                       "Deja la cola en parallel_videos: 1 y sube sourcing.youtube.min_interval a 3.")
        elif info_time > download and info_time > SLOW:
            out.append(f"Lo lento es pedir los datos del vídeo ({info_time:.0f} s), no bajarlo: suele ser deno resolviendo "
                       "los retos muy despacio. Prueba: deno upgrade, excluye la carpeta de deno y la del proyecto del "
                       "antivirus (Windows Defender → Exclusiones) y vuelve a probar.")
        elif line is not None and line >= 2 and download > SLOW:
            out.append(f"Tu conexión va bien ({line} MB/s fuera de YouTube) pero YouTube te sirve el vídeo a paso de tortuga "
                       f"({download:.0f} s de descarga): YouTube frena a tu IP o a tus cuentas. Prueba sin cookies y, si "
                       "sigue igual, reinicia el router (IP nueva) o usa otra red una noche.")
        elif line is not None and line < 2:
            out.append(f"Tu conexión va lenta en general ({line} MB/s fuera de YouTube): no es cosa de YouTube. Prueba "
                       "por cable, sin VPN, o revisa que nada más esté descargando por la noche.")
    if not info["ejs"] or not info["js"]:
        out.append("FALTA el solucionador de retos de YouTube (yt-dlp-ejs) o un JavaScript (deno/node). Sin él, YouTube "
                   "sirve las descargas a paso de tortuga. Arréglalo con:\n"
                   "     pip install -U \"yt-dlp[default]\"\n"
                   "     winget install DenoLand.Deno      (Windows; en Mac: brew install deno)\n"
                   "   y cierra y abre la terminal.")
    warned = " ".join(" ".join(r["warnings"]) for r in runs).lower()
    if "retos" in warned and not out:
        out.append("yt-dlp no consigue resolver los retos aunque tiene deno/node: actualiza las dos cosas "
                   "(pip install -U \"yt-dlp[default]\" y deno upgrade) y vuelve a probar.")
    ok = [r for r in runs if not r["error"]]
    blocked = [r for r in runs if "sign in" in r["error"].lower() or "robot" in r["error"].lower() or "bot\"" in r["error"].lower()]
    if any(r["label"] == "con cookies" for r in blocked) or (blocked and len(runs) == 1):
        out.append("YouTube pide iniciar sesión («no eres un robot»): renueva las cookies (exporta de nuevo "
                   "youtube-cookies.txt desde el navegador) o usa browser_accounts en config.yaml.")
    elif blocked:
        out.append("Sin cookies YouTube te pide iniciar sesión en esta red, pero con ellas funciona: no las quites.")
    if "429" in warned or any("429" in r["error"] for r in runs):
        out.append("YouTube está limitando a tu conexión (429). Baja sourcing.youtube.concurrency a 1-2, sube "
                   "min_interval a 2 y deja la cola en parallel_videos: 1 unas noches.")
    if len(ok) == 2 and ok[0]["label"] == "con cookies":
        with_cookies, without = ok
        if with_cookies["seconds"] > SLOW and without["seconds"] < GOOD:
            out.append("Con tus cookies va lento y sin ellas rápido: YouTube frena a ESA cuenta. Exporta cookies de "
                       "otra cuenta (o quita la actual) — las búsquedas y descargas públicas no las necesitan.")
    fastest = min((r["seconds"] for r in ok), default=None)
    if fastest is not None and fastest > SLOW and not out and line is None:
        out.append("Todo en orden en yt-dlp pero la descarga es lenta con y sin cookies: es la conexión o YouTube "
                   "frena a tu IP. Prueba con el cable/otra red, sin VPN, o la cola por la mañana.")
    if fastest is not None and fastest <= GOOD and not out:
        out.append("YouTube descarga bien en esta máquina ahora mismo. Si una noche va lenta, mira en "
                   "out/<vídeo>/diagnostico.md la línea «Tiempos YouTube» y los AVISO yt-dlp de esa noche.")
    if fastest is not None and GOOD < fastest <= SLOW and not out:
        out.append("Algo lento pero usable. Si la noche entera va así, prueba sin cookies y con parallel_videos: 1.")
    if not ok and not out:
        out.append("No se pudo descargar nada: mira el error de arriba y pásamelo.")
    return out


def run(ctx: RunContext) -> list[str]:
    from .sourcing import cookie_sets

    info = versions()
    print(f"yt-dlp {info['yt-dlp'] or 'NO INSTALADO'} · retos (yt-dlp-ejs) {info['ejs'] or 'FALTA'} · "
          f"JavaScript: {info['js'] or 'NINGUNO'}")
    sets = cookie_sets(ctx, ctx.section("sourcing").get("youtube", {}))
    print(f"Descargando 10 s de un vídeo de prueba como en la cola de noche ({len(sets)} cuenta(s) de cookies)…")
    runs = []
    if sets:
        runs.append(_try(ctx, sets, "con cookies"))
    runs.append(_try(ctx, [], "sin cookies"))
    info["line"] = connection_speed()
    print(f"   Conexión fuera de YouTube: {info['line'] if info['line'] is not None else '?'} MB/s")
    lines = verdict(info, runs)
    print("\nQué hacer:")
    for n, line in enumerate(lines, 1):
        print(f" {n}. {line}")
    return lines
