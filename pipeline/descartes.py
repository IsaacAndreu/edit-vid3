"""«Material descartado»: why candidates were left out, and how many shots ended without footage because of it.

The limits that throw material away are of three kinds: what YouTube refuses (bot, region, age, private, removed),
caps that save proxy GB (whole_max_*_residential, max_height, max_details_per_shot, min_height, min/max_duration…)
and editorial filters (content.title_blocklist, judge.avoid_other_videos, the text/face/presenter checks of the
analysis and the fallback). Each of them can be changed per channel (canales/<canal>.yaml or
materiales/<canal>/config.yaml) and per video (materiales/<vídeo>/config.yaml); this table says which one is worth
changing. For every footage shot it reads, from what the run left on disk:

- the sourcing notes of its candidates (candidates/<plano>.json): refused, too short, no HLS…;
- the options the analysis discarded (scores/<plano>.json): text on screen, presenter, not relevant enough…;
- what this machine refuses (cache/videos/.rechazados.json) for its candidate videos;
and, for the shots whose final picture is not a video (manifest: a photo, a card, a generated image), the main reason
among their own candidates' discards.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PATTERNS = (
    ("YouTube: «no eres un bot»", ("no eres un bot",)),
    ("YouTube: no disponible en el país", ("país del proxy", "bloqueado en", "no disponible en")),
    ("YouTube: no lo sirve a un proxy", ("ip de un proxy", "vpn")),
    ("YouTube: necesita cuenta / edad", ("necesita una cuenta", "restringido por edad")),
    ("YouTube: borrado o privado", ("no está disponible", "no público")),
    ("proxy: sin HLS y supera el tope (whole_max_*_residential)", ("sin hls", "supera el tope")),
    ("plano difícil: tope de vídeos mirados (max_details_per_shot)", ("se deja de buscar",)),
    ("título bloqueado (content.title_blocklist)", ("title_blocklist", "título bloqueado")),
    ("ya usado en otro vídeo (judge.avoid_other_videos)", ("otro vídeo", "used elsewhere")),
)
REFUSALS = {"bot": "YouTube: «no eres un bot»", "geo": "YouTube: no disponible en el país",
            "vpn": "YouTube: no lo sirve a un proxy", "sin-hls": "proxy: sin HLS y supera el tope (whole_max_*_residential)",
            "no-disponible": "YouTube: borrado o privado"}


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def note_reason(note: str) -> str | None:
    low = note.casefold()
    for name, markers in PATTERNS:
        if any(m in low for m in markers):
            return name
    return None


def analysis_reason(discarded: str) -> str:
    return "análisis: " + re.split(r" \(|:", discarded, 1)[0].strip()


def collect(work: Path, out: Path, cache: Path) -> dict[str, dict[str, int]]:
    refusals = _read(cache / "videos" / ".rechazados.json") or {}
    manifest = {r.get("shotId"): r for r in ((_read(out / "manifest.json") or {}).get("shots") or [])}
    table: dict[str, dict[str, int]] = {}

    def add(reason: str, field: str, n: int = 1) -> None:
        entry = table.setdefault(reason, {"candidatos": 0, "planos": 0})
        entry[field] += n

    for path in sorted((work / "candidates").glob("*.json")) if (work / "candidates").is_dir() else []:
        if path.name.startswith("_"):
            continue
        data = _read(path) or {}
        shot = str(data.get("shotId") or path.stem)
        reasons: dict[str, int] = {}
        for note in data.get("notes") or []:
            reason = note_reason(str(note))
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        for c in data.get("candidates") or []:
            entry = refusals.get(str(c.get("id") or "").removeprefix("yt:"))
            if entry is not None:
                why = entry.get("why", "bot") if isinstance(entry, dict) else "bot"
                reason = REFUSALS.get(str(why), f"YouTube: {why}")
                reasons[reason] = reasons.get(reason, 0) + 1
        scores = _read(work / "scores" / f"{shot}.json") or {}
        for option in scores.get("options") or []:
            if option.get("discarded"):
                reason = analysis_reason(str(option["discarded"]))
                reasons[reason] = reasons.get(reason, 0) + 1
        for reason, n in reasons.items():
            add(reason, "candidatos", n)
        row = manifest.get(shot)
        without_video = row is not None and row.get("kind") != "video"
        if without_video and reasons:
            add(max(reasons, key=lambda r: reasons[r]), "planos")
    return table


def lines(table: dict[str, dict[str, int]]) -> list[str]:
    if not table:
        return []
    out = ["## Material descartado", "",
           "Cada motivo se puede cambiar por canal o por vídeo en su config.yaml (ver pipeline/descartes.py). «Planos sin "
           "vídeo»: planos que acabaron en foto, rótulo o imagen generada, con ese motivo como el principal de sus "
           "candidatos.", "", "| Motivo | Candidatos | Planos sin vídeo |", "|---|---|---|"]
    for reason, entry in sorted(table.items(), key=lambda kv: (-kv[1]["planos"], -kv[1]["candidatos"])):
        out.append(f"| {reason} | {entry['candidatos']} | {entry['planos']} |")
    return out
