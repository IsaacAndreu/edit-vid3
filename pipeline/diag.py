"""Diagnosis of each video: what happened, how long each part took, what failed and why, and what to
change so it goes better next time.

- out/<slug>/log.txt: everything printed while the video was made, each line with its time
  (appended run after run, so a night's history stays).
- out/<slug>/diagnostico.md (+ work/<slug>/diag.json): written when the run ends, fine or not:
  the machine (yt-dlp and its challenge solver, JavaScript runtime, ffmpeg, disk, memory), time per
  stage, YouTube timings and warnings, download failures grouped by cause, where fill-in footage came
  from, costs, and a "Qué mejorar" list of concrete fixes derived from all of that.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, TextIO

from .context import RunContext

LOG = "log.txt"
REPORT = "diagnostico.md"


# --- full log ---------------------------------------------------------------------------------------------

class _Tee:
    """Writes to the console as before and to the log file with the time at the start of each line."""

    def __init__(self, console: TextIO, log: TextIO, lock: threading.Lock) -> None:
        self.console, self.log, self.lock = console, log, lock
        self.at_line_start = True

    def write(self, text: str) -> int:
        with self.lock:
            try:
                self.console.write(text)
            except (UnicodeEncodeError, ValueError):
                self.console.write(text.encode("ascii", "replace").decode())
            for part in text.splitlines(keepends=True):
                if self.at_line_start and part.strip():
                    self.log.write(f"{datetime.now():%H:%M:%S} ")
                self.log.write(part)
                self.at_line_start = part.endswith("\n")
            self.log.flush()
        return len(text)

    def flush(self) -> None:
        self.console.flush()
        self.log.flush()

    def isatty(self) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.console, name)


@contextlib.contextmanager
def logging(ctx: RunContext) -> Iterator[None]:
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.out_dir / LOG
    lock = threading.Lock()
    with path.open("a", encoding="utf-8") as log:
        log.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} · {' '.join(sys.argv[1:])} =====\n")
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = _Tee(old_out, log, lock), _Tee(old_err, log, lock)
        try:
            yield
        finally:
            sys.stdout, sys.stderr = old_out, old_err


# --- what happened ---------------------------------------------------------------------------------------------

def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _version(package: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(package)
    except PackageNotFoundError:
        return "FALTA"


def _tool(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return (out.stdout or out.stderr).strip().splitlines()[0][:80]
    except (OSError, subprocess.SubprocessError, IndexError):
        return "no encontrado"


def environment(ctx: RunContext) -> dict[str, Any]:
    memory = None
    try:
        import psutil  # optional

        memory = round(psutil.virtual_memory().total / 1e9, 1)
    except Exception:
        pass
    runtime = next((name for name in ("deno", "node", "bun") if shutil.which(name)), None)
    return {
        "sistema": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
        "cpu": os.cpu_count(), "ram_gb": memory, "disco_libre_gb": round(shutil.disk_usage(ctx.root).free / 1e9, 1),
        "yt-dlp": _version("yt-dlp"), "yt-dlp-ejs": _version("yt-dlp-ejs"), "javascript": runtime or "NINGUNO",
        "ffmpeg": _tool(["ffmpeg", "-version"]), "rembg": _version("rembg"),
    }


FAILURE_CAUSES = (
    ("tramo vacío", "YouTube devolvió un tramo vacío"),
    ("no cabe en 1920x1080", "clip con tamaño raro"),
    ("403", "YouTube rechazó la descarga (403)"),
    ("429", "YouTube limitó las peticiones (429)"),
    ("not a bot", "cuenta bloqueada (no soy un robot)"),
    ("sign in", "cuenta bloqueada (no soy un robot)"),
    ("private", "vídeo privado o borrado"),
    ("unavailable", "vídeo privado o borrado"),
    ("404", "imagen o página que ya no existe (404)"),
    ("timed out", "la conexión tardó demasiado"),
    ("timeout", "la conexión tardó demasiado"),
    ("list index", "tramo sin imagen (versión antigua)"),
    ("se esperaba 1920x1080", "clip 4:3/vertical rechazado (versión antigua)"),
)


def _cause(message: str) -> str:
    lowered = message.casefold()
    return next((cause for marker, cause in FAILURE_CAUSES if marker in lowered), "otro: " + message.strip()[:70])


def _log_facts(ctx: RunContext) -> dict[str, Any]:
    """What only the log knows: YouTube timings per stage, yt-dlp warnings, blocked accounts, render speed."""

    path = ctx.out_dir / LOG
    if not path.is_file():
        return {}
    text = path.read_text("utf-8", errors="replace")
    run = text.rsplit("\n===== ", 1)[-1]                 # this run only
    facts: dict[str, Any] = {"youtube": {}, "avisos_ytdlp": [], "cuentas_bloqueadas": 0}
    stage = None
    for line in run.splitlines():
        found = re.search(r"\] (\w+): ejecutando", line)
        if found:
            stage = found.group(1)
        found = re.search(r"Tiempos YouTube: (.*)", line)
        if found and stage:
            facts["youtube"][stage] = {m.group(1): (int(m.group(2)), float(m.group(3)))
                                       for m in re.finditer(r"([\w ]+?) (\d+)× ([\d.]+) s", found.group(1))}
        found = re.search(r"AVISO yt-dlp: (.*)", line)
        if found and found.group(1) not in facts["avisos_ytdlp"]:
            facts["avisos_ytdlp"].append(found.group(1))
        if "YouTube bloqueó" in line:
            facts["cuentas_bloqueadas"] += 1
        found = re.search(r"Remotion: (\d+) fotogramas en (\d+) s \(([\d.]+) fps\)", line)
        if found:
            facts["render_fps"] = float(found.group(3))
    return facts


def collect(ctx: RunContext) -> dict[str, Any]:
    work = ctx.work_dir
    data: dict[str, Any] = {"video": ctx.slug, "fecha": datetime.now().isoformat(timespec="seconds"),
                            "entorno": environment(ctx), "etapas": {}}
    from .runner import STAGE_NAMES

    stages_dir = work / ".stages"
    order = {name: i for i, name in enumerate(STAGE_NAMES)}
    markers = sorted(stages_dir.glob("*.json"), key=lambda m: order.get(m.stem, 99)) if stages_dir.is_dir() else []
    for marker in markers:
        info = _read(marker) or {}
        data["etapas"][marker.stem] = {"segundos": info.get("seconds"), "hecha": info.get("completedAt")}
    selection = _read(work / "selection.json")
    if selection:
        data["juez"] = selection.get("stats", {})
    ingest = _read(work / "media" / "_ingest.json")
    if ingest:
        failed = ingest.get("failed") or {}
        causes: dict[str, list[str]] = {}
        for shot, message in failed.items():
            causes.setdefault(_cause(str(message)), []).append(shot)
        data["descarga"] = {"clips": sum(1 for m in ingest.get("media", []) if m.get("kind") == "video"),
                            "imagenes": sum(1 for m in ingest.get("media", []) if m.get("kind") == "image"),
                            "fallidas": len(failed), "causas": causes}
    fallback = _read(work / "fallback.json")
    if fallback:
        methods: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for item in fallback.get("items", []):
            methods[item.get("method", "?")] = methods.get(item.get("method", "?"), 0) + 1
            reason = re.sub(r" de s\d+|: .*", "", str(item.get("reason", "")))
            reasons[reason] = reasons.get(reason, 0) + 1
        data["relleno"] = {"metodos": methods, "motivos": reasons, "sin_resolver": len(fallback.get("unresolved", {}) or {})}
    summary = _read(work / "scores" / "_summary.json")
    if summary:
        data["analisis"] = {"planos": summary.get("shots"), "con_video_verificado": summary.get("shotsWithCheckedVideo"),
                            "descartes": summary.get("discardReasons", {})}
    qa = _read(ctx.out_dir / "qa" / "qa.json")
    if qa:
        data["pantalla"] = qa.get("shareBySeconds", {})
        data["planos_flojos"] = len(qa.get("lowScore", []))
    costs = _read(work / "costs.json")
    if costs:
        by_stage: dict[str, float] = {}
        for entry in costs.get("entries", []):
            by_stage[entry.get("stage", "?")] = by_stage.get(entry.get("stage", "?"), 0.0) + float(entry.get("usd") or 0)
        data["coste_usd"] = {k: round(v, 3) for k, v in by_stage.items()}
    factcheck = _read(work / "factcheck.json")
    if factcheck:
        verdicts: dict[str, int] = {}
        for claim in factcheck.get("claims", []):
            verdicts[claim.get("verdict", "?")] = verdicts.get(claim.get("verdict", "?"), 0) + 1
        data["verificacion"] = verdicts
    data.update(_log_facts(ctx))
    from . import ytstats

    rows = ytstats.read(work / "youtube_downloads.jsonl")
    if rows:
        data["youtube_metricas"] = ytstats.summary(rows)
    return data


# --- what to change ---------------------------------------------------------------------------------------------

def hints(data: dict[str, Any], ctx: RunContext) -> list[str]:
    out: list[str] = []
    env = data.get("entorno", {})
    if env.get("yt-dlp-ejs") == "FALTA" or env.get("javascript") == "NINGUNO":
        out.append("Falta el resolvedor de retos de YouTube (yt-dlp-ejs) o deno/node: las descargas irán lentísimas. "
                   "`pip install -U \"yt-dlp[default]\" deno`.")
    ingest_yt = (data.get("youtube") or {}).get("ingest", {})
    download = ingest_yt.get("download")
    if download and download[1] > 25:
        out.append(f"Descargas en HD muy lentas ({download[1]:.0f} s por tramo; lo normal es < 10 s). Si hay avisos de "
                   "retos abajo, `pip install -U \"yt-dlp[default]\" deno`; si no, YouTube está frenando tu IP: prueba "
                   "`sourcing.youtube.player_client: [tv, web_safari]` o descargar de día y renderizar de noche.")
    waits = ingest_yt.get("espera por límite") or (data.get("youtube") or {}).get("sourcing", {}).get("espera por límite")
    if waits and waits[0] * waits[1] > 300:
        out.append(f"Se esperaron {waits[0] * waits[1] / 60:.0f} min por límites de YouTube (429). Baja "
                   "`sourcing.youtube.concurrency` a 2 o añade otra cuenta de cookies.")
    if data.get("cuentas_bloqueadas"):
        out.append(f"YouTube bloqueó {data['cuentas_bloqueadas']} cuenta(s): exporta cookies nuevas de esas cuentas "
                   "(o usa las de Firefox, que no caducan: `browser_accounts`).")
    for warning in data.get("avisos_ytdlp", []):
        out.append(f"yt-dlp avisó: {warning}")
    causes = (data.get("descarga") or {}).get("causas", {})
    for cause, shots in sorted(causes.items(), key=lambda c: -len(c[1])):
        if "versión antigua" in cause:
            out.append(f"{len(shots)} descarga(s) fallaron por un error ya corregido ({cause}): `git pull`.")
        elif len(shots) >= 3:
            out.append(f"{len(shots)} descargas fallaron por «{cause}» ({', '.join(shots[:6])}…).")
    shares = data.get("pantalla", {})
    stock = sum(v for k, v in shares.items() if "pexels" in k.lower() or "generad" in k.lower())
    limit = float(ctx.section("report").get("max_stock", 0.10))
    if stock > limit:
        methods = (data.get("relleno") or {}).get("metodos", {})
        out.append(f"Metraje genérico al {stock:.0%} (límite {limit:.0%}). Del relleno: "
                   + ", ".join(f"{k} {v}" for k, v in methods.items())
                   + ". Cámbialo en el editor (`python main.py --editor " + ctx.slug + "`, botón «⚠ flojos») "
                   "o sube `sourcing.youtube.videos_per_shot` para tener más opciones.")
    judge = data.get("juez") or {}
    shots = judge.get("shots") or 0
    if shots and judge.get("fallback", 0) / shots > 0.2:
        out.append(f"El juez rechazó todo en {judge['fallback']} de {shots} planos: las búsquedas encuentran poco del "
                   "tema. Revisa los tramos del guion más abstractos o escribe más nombres propios (lugares, fechas).")
    discards = (data.get("analisis") or {}).get("descartes", {})
    total = sum(discards.values()) or 1
    if discards.get("poco relevante", 0) / total > 0.5:
        out.append("Más de la mitad de lo descartado es «poco relevante»: las búsquedas son demasiado genéricas.")
    wrong = (data.get("verificacion") or {}).get("wrong", 0)
    if wrong:
        out.append(f"La verificación marcó {wrong} dato(s) como incorrectos: corrígelos en el guion antes de subir "
                   f"(out/{ctx.slug}/verificacion.md).")
    metrics = data.get("youtube_metricas") or {}
    if metrics.get("requests"):
        blocked = metrics["errors"].get("bot", 0) + metrics["errors"].get("403", 0)
        if blocked / metrics["requests"] > 0.05:
            out.append(f"YouTube rechazó {blocked} de {metrics['requests']} peticiones (403 o «no eres un bot»): "
                       + ("revisa el PO Token Provider (docs/VPS.md)." if not metrics.get("pot") else
                          "esta IP o esta configuración no aguantan este volumen."))
    fps = data.get("render_fps")
    if fps is not None and fps < 5:
        out.append(f"Render lento ({fps:.1f} fps en Remotion): cierra otros programas o baja `render.concurrency`.")
    if env.get("disco_libre_gb") is not None and env["disco_libre_gb"] < 30:
        out.append(f"Queda poco disco ({env['disco_libre_gb']} GB): borra `work/<vídeo>` de vídeos ya subidos.")
    slowest = max(((k, v.get("segundos") or 0) for k, v in data.get("etapas", {}).items()), key=lambda kv: kv[1], default=None)
    if slowest and slowest[1] > 3600:
        out.append(f"La etapa más lenta fue {slowest[0]} ({slowest[1] / 3600:.1f} h).")
    return out


def _fmt(seconds: float | None) -> str:
    if not seconds:
        return "—"
    return f"{seconds / 60:.1f} min" if seconds >= 60 else f"{seconds:.0f} s"


def markdown(data: dict[str, Any], tips: list[str], error: str | None) -> str:
    lines = [f"# Diagnóstico · {data['video']}", "", f"_{data['fecha']}_", ""]
    if error:
        lines += ["## ❌ Error", "", "```", error.strip()[-3000:], "```", ""]
    lines += ["## Qué mejorar", ""] + ([f"- {t}" for t in tips] or ["- Nada destacable: todo dentro de lo normal ✅"]) + [""]
    lines += ["## Tiempo por etapa", "", "| Etapa | Tiempo |", "|---|---|"]
    lines += [f"| {k} | {_fmt(v.get('segundos'))} |" for k, v in data.get("etapas", {}).items()]
    if data.get("youtube"):
        lines += ["", "## YouTube", ""]
        for stage, stats in data["youtube"].items():
            lines.append(f"- {stage}: " + " · ".join(f"{k} {n}× {s:.1f} s" for k, (n, s) in stats.items()))
        if data.get("cuentas_bloqueadas"):
            lines.append(f"- Cuentas bloqueadas: {data['cuentas_bloqueadas']}")
    if data.get("youtube_metricas"):
        from . import ytstats

        lines += ["", "## YouTube: cómo respondió", "", *ytstats.lines(data["youtube_metricas"])]
    if data.get("descarga"):
        d = data["descarga"]
        lines += ["", "## Descarga en HD", "", f"{d['clips']} clips · {d['imagenes']} imágenes · {d['fallidas']} fallidas", ""]
        lines += [f"- {cause}: {len(shots)} ({', '.join(shots[:8])})" for cause, shots in d["causas"].items()]
    if data.get("relleno"):
        r = data["relleno"]
        lines += ["", "## Relleno (planos sin opción buena)", "",
                  "De dónde salió: " + ", ".join(f"{k} {v}" for k, v in r["metodos"].items()),
                  "Por qué: " + ", ".join(f"{k} {v}" for k, v in r["motivos"].items())]
    if data.get("pantalla"):
        lines += ["", "## En pantalla", ""] + [f"- {k}: {v:.0%}" for k, v in data["pantalla"].items()]
    if data.get("analisis"):
        a = data["analisis"]
        lines += ["", "## Análisis", "", f"{a.get('con_video_verificado')}/{a.get('planos')} planos con vídeo verificado",
                  "Descartes: " + ", ".join(f"{k} {v}" for k, v in (a.get("descartes") or {}).items())]
    if data.get("coste_usd"):
        lines += ["", "## Coste", "", " · ".join(f"{k} {v:.3f} $" for k, v in data["coste_usd"].items())
                  + f" · total {sum(data['coste_usd'].values()):.2f} $"]
    lines += ["", "## Entorno", ""] + [f"- {k}: {v}" for k, v in data.get("entorno", {}).items()]
    return "\n".join(lines) + "\n"


def write(ctx: RunContext, error: BaseException | None = None) -> list[str]:
    """Write the diagnosis; returns the hints (also printed)."""

    try:
        data = collect(ctx)
        tips = hints(data, ctx)
        detail = "".join(traceback.format_exception(error)) if error is not None else None
        if error is not None:
            data["error"] = f"{type(error).__name__}: {error}"
        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        (ctx.out_dir / REPORT).write_text(markdown(data, tips, detail), encoding="utf-8")
        ctx.work_dir.mkdir(parents=True, exist_ok=True)
        (ctx.work_dir / "diag.json").write_text(json.dumps({**data, "consejos": tips}, ensure_ascii=False, indent=1,
                                                           default=str), encoding="utf-8")
        if tips:
            print(f"Diagnóstico ({len(tips)} cosa(s) a mejorar) → out/{ctx.slug}/{REPORT}")
            for tip in tips[:5]:
                print(f"   • {tip}")
        return tips
    except Exception as failure:  # the diagnosis must never break a run
        print(f"(No se pudo escribir el diagnóstico: {type(failure).__name__}: {failure})")
        return []
