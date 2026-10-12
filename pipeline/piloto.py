"""The scene-search pilot: ONE new documentary with the scene search, against an existing one as the reference.

    python main.py --piloto-escenas <vídeo> [--referencia <vídeo hecho>]   (or the video page → «🧪 Piloto»)
    python main.py --informe-piloto <vídeo>
    python main.py --quitar-piloto <vídeo>

Turning it on writes, in that video's materiales/<vídeo>/config.yaml only, sourcing.youtube.scene_search: true,
judge.variety_margin: 0.02 and sourcing.youtube.api_overflow: esperar (when the API's daily searches would not cover
the scene searches, the video waits for tomorrow's quota instead of searching the rest by yt-dlp). Everything else
keeps the per-shot search; turning it off removes those keys.

The report compares the real runs, per 100 shots where sizes differ: requests that went to YouTube (searches,
extractions, downloads, «are you a bot» answers), different sources on screen and repeats (also back-to-back),
shots without usable footage (fallback, weak shots), stage times and the human review of the clips (Revisar clips:
correcta / incorrecta / dudosa). The simulator's CLIP is no proof: the review is what decides.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from .context import RunContext

PILOT = {"sourcing": {"youtube": {"scene_search": True, "api_overflow": "esperar"}}, "judge": {"variety_margin": 0.02}}
REGISTRY = "out/_pilotos.json"


def _config_path(root: Path, slug: str) -> Path:
    return RunContext.create(slug, root=root).materials_dir / "config.yaml"


def _registry(root: Path) -> dict[str, Any]:
    try:
        return json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_registry(root: Path, data: dict[str, Any]) -> None:
    (root / REGISTRY).parent.mkdir(parents=True, exist_ok=True)
    (root / REGISTRY).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def _strip(base: dict[str, Any], keys: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in keys.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _strip(out[key], value)
            if not out[key]:
                del out[key]
        else:
            out.pop(key, None)
    return out


def finished(root: Path) -> list[str]:
    """Videos with a selection and a diagnosis: possible references."""

    return sorted(p.parent.name for p in (root / "work").glob("*/diag.json")
                  if (p.parent / "selection.json").is_file() and not p.parent.name.startswith("_"))


def enable(root: Path, slug: str, reference: str | None = None) -> dict[str, Any]:
    others = [v for v in _registry(root) if v != slug]
    if others:            # one new documentary only: a second pilot would double the traffic being measured
        raise ValueError(f"Ya hay un piloto: {others[0]}. Quítalo antes («--quitar-piloto {others[0]}»).")
    if reference and reference not in finished(root):
        raise ValueError(f"{reference} no es un vídeo terminado (hace falta su diagnóstico y su selección)")
    if not reference:
        options = [v for v in finished(root) if v != slug and v not in _registry(root)]
        same = [v for v in options
                if RunContext.create(v, root=root).config.get("canal") == RunContext.create(slug, root=root).config.get("canal")]
        reference = (same or options or [None])[-1]
    path = _config_path(root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    path.write_text(yaml.safe_dump(_merge(current or {}, PILOT), allow_unicode=True, sort_keys=False), encoding="utf-8")
    registry = _registry(root)
    registry[slug] = {"reference": reference, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _save_registry(root, registry)
    return {"ok": True, "video": slug, "reference": reference}


def disable(root: Path, slug: str) -> dict[str, Any]:
    path = _config_path(root, slug)
    if path.is_file():
        current = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        left = _strip(current, PILOT)
        path.write_text(yaml.safe_dump(left, allow_unicode=True, sort_keys=False) if left else "", encoding="utf-8")
    registry = _registry(root)
    registry.pop(slug, None)
    _save_registry(root, registry)
    return {"ok": True, "video": slug}


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def measure(root: Path, slug: str) -> dict[str, Any]:
    """What really happened in a finished run of `slug` (its work folder)."""

    from . import feedback

    work = root / "work" / slug
    diag = _read(work / "diag.json") or {}
    selections = (_read(work / "selection.json") or {}).get("selections", [])
    summary = _read(work / "candidates" / "_summary.json") or {}
    requests: dict[str, int] = {}
    bot = 0
    path = work / "youtube_downloads.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            action = str(row.get("action") or "?")
            kind = "descargas" if action.startswith("download") else {"metadata": "extracciones",
                                                                      "search": "búsquedas yt-dlp"}.get(action, action)
            requests[kind] = requests.get(kind, 0) + 1
            bot += row.get("error") == "bot"
    youtube = [s for s in selections if s.get("status") == "selected" and str(s.get("candidateId", "")).startswith("yt:")]
    sources = [s["candidateId"] for s in youtube]
    back_to_back = sum(1 for a, b in zip(selections, selections[1:])
                       if a.get("candidateId") and a.get("candidateId") == b.get("candidateId"))
    labels = {k.split("/", 1)[1]: v["verdict"] for k, v in feedback.labels(root).items() if k.startswith(slug + "/")}
    shots = len(selections) or int(diag.get("juez", {}).get("shots") or 0)
    stages = diag.get("etapas", {})
    return {
        "video": slug,
        "shots": shots,
        "sceneSearch": bool(summary.get("sceneSearch")),
        "requests": requests,
        "botAnswers": bot,
        "youtubeShots": len(youtube),
        "differentSources": len(set(sources)),
        "repeats": round(1 - len(set(sources)) / len(sources), 3) if sources else None,
        "backToBack": back_to_back,
        "fallback": int(diag.get("juez", {}).get("fallback") or sum(s.get("status") == "fallback" for s in selections)),
        "weakShots": int(diag.get("planos_flojos") or 0),
        "unresolved": int(diag.get("relleno", {}).get("sin_resolver") or 0),
        "sourcingMinutes": round(float(stages.get("sourcing", {}).get("segundos") or 0) / 60, 1),
        "analysisMinutes": round(float(stages.get("analysis", {}).get("segundos") or 0) / 60, 1),
        "totalMinutes": round(sum(float(s.get("segundos") or 0) for s in stages.values()) / 60, 1),
        "review": {v: list(labels.values()).count(v) for v in ("correcta", "incorrecta", "dudosa")},
        "reviewed": len(labels),
    }


def _per100(value: Any, shots: int) -> Any:
    return round(100 * value / shots, 1) if isinstance(value, (int, float)) and shots else None


def report(root: Path, slug: str, reference: str | None = None) -> dict[str, Any]:
    reference = reference or _registry(root).get(slug, {}).get("reference")
    if not reference:
        raise SystemExit("Falta el vídeo de referencia: --referencia <vídeo hecho>")
    pilot, ref = measure(root, slug), measure(root, reference)
    rows = []

    def row(label: str, key: str, per100: bool = False, lower_is_better: bool = True) -> None:
        a, b = ref.get(key), pilot.get(key)
        if per100:
            a, b = _per100(a, ref["shots"]), _per100(b, pilot["shots"])
        rows.append({"label": label + (" (por 100 planos)" if per100 else ""), "reference": a, "pilot": b,
                     "better": None if a is None or b is None or a == b else (b < a) == lower_is_better})

    for kind in sorted(set(ref["requests"]) | set(pilot["requests"])):
        ref[f"req:{kind}"], pilot[f"req:{kind}"] = ref["requests"].get(kind, 0), pilot["requests"].get(kind, 0)
        row(f"Peticiones: {kind}", f"req:{kind}", per100=True)
    row("Respuestas «no eres un bot»", "botAnswers")
    row("Fuentes distintas en pantalla", "differentSources", per100=True, lower_is_better=False)
    row("Fuentes repetidas", "repeats")
    row("Misma fuente en planos seguidos", "backToBack", per100=True)
    row("Planos sin metraje aprovechable (relleno)", "fallback", per100=True)
    row("Planos flojos", "weakShots", per100=True)
    row("Minutos de búsqueda", "sourcingMinutes")
    row("Minutos totales", "totalMinutes")
    for verdict in ("correcta", "incorrecta", "dudosa"):
        ref[f"rev:{verdict}"] = ref["review"][verdict] / ref["reviewed"] if ref["reviewed"] else None
        pilot[f"rev:{verdict}"] = pilot["review"][verdict] / pilot["reviewed"] if pilot["reviewed"] else None
        row(f"Revisión humana: {verdict} (proporción)", f"rev:{verdict}", lower_is_better=verdict != "correcta")
    result = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pilot": pilot, "reference": ref, "rows": rows,
              "pending": [] if pilot["reviewed"] >= 30 else
              [f"Revisa al menos 30 clips del piloto en «Revisar clips» (ahora {pilot['reviewed']}): decide la calidad, no el simulador."]}
    if not pilot["sceneSearch"]:
        result["pending"].append("Este vídeo no se buscó por escenas (¿se activó el piloto antes de la búsqueda?).")
    target = root / "out" / slug / "piloto.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (target.with_suffix(".md")).write_text(markdown(result), encoding="utf-8")
    return result


def markdown(result: dict[str, Any]) -> str:
    def show(x: Any) -> str:
        return "—" if x is None else f"{x:.0%}" if isinstance(x, float) and 0 <= x <= 1 and not float(x).is_integer() else str(x)

    lines = [f"# Piloto por escenas: {result['pilot']['video']} frente a {result['reference']['video']}", "",
             f"{result['pilot']['shots']} planos frente a {result['reference']['shots']}.", "",
             "| | Referencia | Piloto | |", "|---|---|---|---|"]
    for row in result["rows"]:
        mark = "" if row["better"] is None else "✅" if row["better"] else "⚠️"
        lines.append(f"| {row['label']} | {show(row['reference'])} | {show(row['pilot'])} | {mark} |")
    if result["pending"]:
        lines += ["", *[f"- {p}" for p in result["pending"]]]
    return "\n".join(lines) + "\n"
