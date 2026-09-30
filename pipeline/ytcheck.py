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
GOOD, SLOW = 20.0, 45.0              # s for the 10-s piece (HLS + exact cut): the cloud does it in ~10 s


def versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    def get(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return ""

    runtime = next((name for name in ("deno", "node", "bun") if shutil.which(name)), "")
    return {"yt-dlp": get("yt-dlp"), "ejs": get("yt-dlp-ejs"), "js": runtime}


PROBE_LIMIT = 90                     # seconds per attempt: slower than this is "too slow" anyway


def _probe(ctx: RunContext, cookies: bool, ipv4: bool) -> dict[str, Any]:
    """One download, in this process (called from a child process so it can be cut off)."""

    from .sourcing import cookie_sets
    from .sourcing.youtube import WARNING_COUNTS, YouTubeSource

    cfg = {**ctx.section("sourcing").get("youtube", {}), "force_ipv4": ipv4}
    sets = cookie_sets(ctx, cfg) if cookies else []
    WARNING_COUNTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        source = YouTubeSource(root=ctx.root, cache_dir=Path(tmp), config=cfg, cookie_sets=sets)
        began = time.monotonic()
        try:
            size, error = source.download_range(TEST_VIDEO, *TEST_RANGE, fmt=FORMAT, prefix="probe").stat().st_size, ""
        except Exception as exc:     # the verdict explains it
            size, error = 0, f"{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            source.close()
        seconds = time.monotonic() - began
        phases = {action: round(total, 1) for action, (_, total) in source.stats.items()}
    return {"seconds": round(seconds, 1), "mb": round(size / 1e6, 1), "error": error,
            "warnings": dict(WARNING_COUNTS), "phases": phases}


def _try(ctx: RunContext, label: str, cookies: bool, ipv4: bool) -> dict[str, Any]:
    """Run one probe in a child process, cut off after PROBE_LIMIT seconds."""

    import json
    import subprocess
    import sys

    began = time.monotonic()
    try:
        done = subprocess.run([sys.executable, "-m", "pipeline.ytcheck", "probe", str(int(cookies)), str(int(ipv4))],
                              capture_output=True, text=True, timeout=PROBE_LIMIT, cwd=ctx.root)
        lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
        result = json.loads(lines[-1]) if lines else {"seconds": round(time.monotonic() - began, 1), "mb": 0,
                                                       "error": (done.stderr or "sin respuesta")[-200:], "warnings": {}, "phases": {}}
    except subprocess.TimeoutExpired:
        result = {"seconds": float(PROBE_LIMIT), "mb": 0, "error": "", "warnings": {}, "phases": {}, "timeout": True}
    result.update(label=label, cookies=cookies, ipv4=ipv4)
    if result.get("timeout"):
        print(f"   {label}: más de {PROBE_LIMIT} s para 10 s de vídeo (cortado)")
    elif result["error"]:
        print(f"   {label}: ERROR {result['error']}")
    else:
        speed = result["mb"] / result["seconds"] if result["seconds"] else 0
        print(f"   {label}: {result['seconds']:.1f} s para 10 s de vídeo ({result['mb']} MB, {speed:.1f} MB/s)")
    if result.get("phases"):
        print("      por fases: " + " · ".join(f"{k} {v} s" for k, v in result["phases"].items()))
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
    v4 = next((r for r in runs if r.get("ipv4") and r.get("cookies", True) == runs[0].get("cookies", True)), None)
    v6 = next((r for r in runs if r.get("ipv4") is False), None)
    if v4 and v6 and not v4["error"] and not v6["error"]:
        if v4["seconds"] <= GOOD and v6["seconds"] > SLOW:
            out.append(f"¡Era IPv6! Con IPv4 tarda {v4['seconds']:.0f} s y por la red por defecto {v6['seconds']:.0f} s. "
                       "Ya viene arreglado: config.yaml trae sourcing.youtube.force_ipv4: true (no lo quites).")
        elif v6["seconds"] <= GOOD and v4["seconds"] > SLOW:
            out.append("Aquí IPv6 va mejor que IPv4: pon sourcing: {youtube: {force_ipv4: false}} en config.yaml.")
    slow_all = runs and all(r.get("timeout") or (not r["error"] and r["seconds"] > SLOW) for r in runs)
    if slow_all and line is not None and line >= 2 and not any(r.get("phases") for r in runs):
        out.append(f"Tu conexión va bien ({line} MB/s fuera de YouTube) pero YouTube va a paso de tortuga en todos los "
                   "intentos (IPv4, IPv6, con y sin cookies): YouTube frena a tu IP. Lo más rápido: apaga el router 5 "
                   "minutos (IP nueva) y repite la prueba; o prueba compartiendo datos del móvil — si ahí va rápido, "
                   "es tu IP de casa.")
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
                       f"({download:.0f} s de descarga): YouTube frena a tu IP. Apaga el router 5 minutos (IP nueva) y "
                       "repite la prueba, o prueba con los datos del móvil: si ahí va rápido, es tu IP de casa.")
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
    if any(r.get("cookies", r["label"].startswith("con cookies")) for r in blocked) or (blocked and len(runs) == 1):
        out.append("YouTube pide iniciar sesión («no eres un robot»): renueva las cookies (exporta de nuevo "
                   "youtube-cookies.txt desde el navegador) o usa browser_accounts en config.yaml.")
    elif blocked:
        out.append("Sin cookies YouTube te pide iniciar sesión en esta red, pero con ellas funciona: no las quites.")
    if "429" in warned or any("429" in r["error"] for r in runs):
        out.append("YouTube está limitando a tu conexión (429). Baja sourcing.youtube.concurrency a 1-2, sube "
                   "min_interval a 2 y deja la cola en parallel_videos: 1 unas noches.")
    with_cookies = next((r for r in ok if r.get("cookies") and r.get("ipv4", True)), None)
    without = next((r for r in ok if r.get("cookies") is False), None)
    if with_cookies and without:
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
    info["line"] = connection_speed()
    print(f"Conexión fuera de YouTube: {info['line'] if info['line'] is not None else '?'} MB/s")
    cookies = bool(cookie_sets(ctx, ctx.section("sourcing").get("youtube", {})))
    who = "con cookies" if cookies else "sin cookies"
    print(f"Descargando 10 s de un vídeo de prueba como en la cola de noche (cada intento se corta a los {PROBE_LIMIT} s)…")
    runs = [_try(ctx, f"{who}, IPv4", cookies, True), _try(ctx, f"{who}, red por defecto (IPv6)", cookies, False)]
    if cookies and all(r.get("timeout") or r["seconds"] > SLOW for r in runs):
        runs.append(_try(ctx, "sin cookies, IPv4", False, True))
    lines = verdict(info, runs)
    print("\nQué hacer:")
    for n, line in enumerate(lines, 1):
        print(f" {n}. {line}")
    return lines


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) == 4 and sys.argv[1] == "probe":
        print(json.dumps(_probe(RunContext.create("_ytcheck"), sys.argv[2] == "1", sys.argv[3] == "1")))
