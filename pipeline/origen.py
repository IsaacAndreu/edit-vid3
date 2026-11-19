"""Where each shot's picture came from — to measure whether the clip is about what the narration says.

For every shot of a finished video (out/<slug>/manifest.json, with selection.json and fallback.json for the details):

- primera elección del juez · otra opción juzgada (the judge's 2nd/3rd, because the 1st repeated or could not come)
- por puntuación (sin juez) · elegido a mano
- relleno juzgado · relleno sin juzgar · foto · generado
- apertura · tarjeta de persona · rótulo (no picture) · heredado (continues another shot's clip) · otro

plus who decided among the judge's options (juez, continuación, maestro, variedad, puntuación, error del juez) and how
many shots the judge saw only as storyboard thumbnails (no 360p window). diagnostico.md shows it per video and
`python main.py --informe-analisis` per channel. Without it nothing says whether a change to search, analysis or
judge makes the clips better.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ORDER = ["primera elección del juez", "otra opción juzgada", "elección del juez (sin puesto)", "por puntuación (sin juez)",
         "elegido a mano", "relleno juzgado", "relleno sin juzgar", "foto", "generado", "apertura", "tarjeta de persona",
         "rótulo", "heredado", "otro"]
PHOTOS = {"web-photo", "library-photo", "pexels-photo", "protagonist-photo"}
JUDGED_BEFORE = {"next-option", "protagonist", "event-footage", "re-search"}     # fallback items written without `judged`


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def classify(row: dict[str, Any], selection: dict[str, Any] | None, item: dict[str, Any] | None) -> str:
    decided = str(row.get("decidedBy") or "")
    if not row.get("media"):
        return "rótulo"
    if decided == "coldopen":
        return "apertura"
    if decided == "people":
        return "tarjeta de persona"
    if decided.startswith("heredado:"):
        return "heredado"
    if decided == "editor":
        return "elegido a mano"
    if decided in ("judge", "score"):
        rank = (selection or {}).get("judgeRank")
        if rank == 1:
            return "primera elección del juez"
        if rank:
            return "otra opción juzgada"
        return "elección del juez (sin puesto)" if decided == "judge" else "por puntuación (sin juez)"
    if decided.startswith("fallback:"):
        method = decided.split(":", 1)[1]
        if method in PHOTOS:
            return "foto"
        if method == "generated":
            return "generado"
        judged = (item or {}).get("judged")
        if judged is None:
            judged = method in JUDGED_BEFORE
        return "relleno juzgado" if judged else "relleno sin juzgar"
    return "otro"


def video(work: Path, out: Path) -> dict[str, Any] | None:
    manifest = _read(out / "manifest.json")
    if not manifest:
        return None
    selections = {s["shotId"]: s for s in ((_read(work / "selection.json") or {}).get("selections") or [])}
    items = {i["shotId"]: i for i in ((_read(work / "fallback.json") or {}).get("items") or [])}
    counts: dict[str, int] = {}
    for row in manifest.get("shots") or []:
        kind = classify(row, selections.get(row.get("shotId")), items.get(row.get("shotId")))
        counts[kind] = counts.get(kind, 0) + 1
    picked: dict[str, int] = {}
    for s in selections.values():
        if s.get("status") == "selected" and s.get("pickedBy"):
            picked[s["pickedBy"]] = picked.get(s["pickedBy"], 0) + 1
    thumbs = sum(1 for s in selections.values() if s.get("thumbnailsOnly"))
    return {"slug": work.name, "shots": sum(counts.values()), "origin": counts, "pickedBy": picked,
            "thumbnailsOnly": thumbs, "judged": sum(1 for s in selections.values() if s.get("judge") is not None)}


def lines(data: dict[str, Any]) -> list[str]:
    total = data["shots"] or 1
    out = ["## De dónde salió cada plano", "", "| Procedencia | Planos | % |", "|---|---|---|"]
    for kind in ORDER:
        n = data["origin"].get(kind, 0)
        if n:
            out.append(f"| {kind} | {n} | {100 * n / total:.0f} % |")
    if data["pickedBy"]:
        out += ["", "Quién decidió entre las opciones del juez: "
                + ", ".join(f"{k} {v}" for k, v in sorted(data["pickedBy"].items(), key=lambda kv: -kv[1]))]
    out.append(f"Planos que el juez vio solo con miniaturas (sin ventana a 360p): {data['thumbnailsOnly']} "
               f"de {data['judged']} juzgados")
    return out


def by_channel(videos: list[dict[str, Any]]) -> list[str]:
    """The same table summed per channel (for --informe-analisis)."""

    channels: dict[str, dict[str, int]] = {}
    for v in videos:
        if not v.get("origin"):
            continue
        entry = channels.setdefault(v.get("channel", "?"), {})
        for kind, n in v["origin"].items():
            entry[kind] = entry.get(kind, 0) + n
        entry["_thumbs"] = entry.get("_thumbs", 0) + int(v.get("thumbnailsOnly") or 0)
    if not channels:
        return []
    kinds = [k for k in ORDER if any(c.get(k) for c in channels.values())]
    out = ["## De dónde salió cada plano, por canal", "",
           "| Canal | " + " | ".join(kinds) + " | Juzgados solo con miniaturas |",
           "|---|" + "---|" * (len(kinds) + 1)]
    for name, entry in sorted(channels.items()):
        total = sum(v for k, v in entry.items() if not k.startswith("_")) or 1
        out.append(f"| {name} | " + " | ".join(f"{100 * entry.get(k, 0) / total:.0f} %" for k in kinds)
                   + f" | {entry['_thumbs']} |")
    return out
