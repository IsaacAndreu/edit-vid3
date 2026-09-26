"""Stage 9 — quality gate before rendering: out/<slug>/qa/, manifest.json, creditos.txt.

Checks the final plan (timeline + the media files on disk) and writes:
- qa/contact-sheet.jpg — one tile per shot, in order, flagged tiles framed in red/amber;
- qa/report.md — low-score shots, third-party clips over 5 s (must be 0), repeated
  fragments, shots without credit, share per source, API spend;
- qa/qa.json — the same, machine-readable;
- manifest.json — provenance of every shot (URL, channel, timestamps, scores, decision);
- creditos.txt — third-party sources, ready to paste into the YouTube description.

Blockers (third-party clip > 5 s, third-party media without credit, missing file or a
timeline that does not match the narration) stop the pipeline: the render never starts.
"""

from __future__ import annotations

import json
import math
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .analysis import detectors as det
from .context import RunContext
from .costs import COSTS_FILE
from .schemas import MAX_THIRD_PARTY_SECONDS, FallbackFile, SelectionFile, ShotsFile, Timeline


STAGE = "qa"
THIRD_PARTY = {"youtube"}
FREE_IMAGES = {"wikimedia", "openverse", "pixabay"}


class QABlocked(RuntimeError):
    """The plan breaks a non-negotiable rule; the render must not start."""


def category(source: str) -> str:
    if source in THIRD_PARTY:
        return "terceros (YouTube)"
    if source in FREE_IMAGES:
        return "imágenes libres"
    if source == "pexels":
        return "Pexels"
    if source == "generated":
        return "generado"
    return source


def clip_seconds(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip() or 0)


def middle_frame(path: Path, kind: str) -> np.ndarray | None:
    if kind == "image":
        return cv2.imread(str(path))
    capture = cv2.VideoCapture(str(path))
    count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 1
    capture.set(cv2.CAP_PROP_POS_FRAMES, count // 2)
    ok, frame = capture.read()
    capture.release()
    return frame if ok else None


def mmss(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "timeline.json", ctx.work_dir / "selection.json", ctx.work_dir / "fallback.json",
            ctx.work_dir / "media" / "_ingest.json"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("qa")
    qa_dir = ctx.out_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    timeline = Timeline.model_validate(ctx.read_json("timeline.json"))
    shots_plan = {s.id: s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots}
    selections = {s.shotId: s for s in SelectionFile.model_validate(ctx.read_json("selection.json")).selections}
    fallback = {i.shotId: i for i in FallbackFile.model_validate(ctx.read_json("fallback.json")).items}
    ingest = {m["shotId"]: m for m in ctx.read_json("media/_ingest.json")["media"]}
    fps = timeline.fps

    blockers: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []   # manifest entries

    # --- per-shot facts ------------------------------------------------------------------
    for shot in timeline.shots:
        start_s, end_s = shot.from_ / fps, (shot.from_ + shot.durationInFrames) / fps
        entry: dict[str, Any] = {
            "shotId": shot.id, "type": shot.type, "start": round(start_s, 3), "end": round(end_s, 3),
            "text": shot.text, "chapterTitle": shot.chapterTitle,
        }
        if shot.media is None:
            rows.append(entry)
            continue
        path = ctx.work_dir / shot.media.src
        entry.update({"media": shot.media.src, "kind": shot.media.kind, "source": shot.media.source,
                      "credit": shot.media.credit, "category": category(shot.media.source)})
        if not path.is_file():
            blockers.append(f"{shot.id}: falta el fichero {shot.media.src}")
            rows.append(entry)
            continue
        if shot.media.kind == "video":
            seconds = clip_seconds(path)
            entry["clipSeconds"] = round(seconds, 3)
            if shot.media.source in THIRD_PARTY and max(seconds, shot.durationInFrames / fps) > MAX_THIRD_PARTY_SECONDS + 1 / fps:
                blockers.append(f"{shot.id}: clip de terceros de {max(seconds, shot.durationInFrames / fps):.2f} s (máximo 5 s)")
        if shot.media.source != "generated" and not (shot.media.credit or "").startswith("Fuente: "):
            blockers.append(f"{shot.id}: material de terceros sin crédito")
        # provenance
        if shot.id in ingest:
            selection = selections[shot.id]
            entry.update({
                "decidedBy": selection.decidedBy, "candidateId": selection.candidateId, "url": selection.url,
                "title": selection.title, "channel": selection.channel, "license": selection.license,
                "sourceStart": ingest[shot.id].get("start"), "sourceEnd": ingest[shot.id].get("end"),
                "score": selection.score, "attribution": selection.attribution,
            })
            if selection.judge:
                entry["judge"] = selection.judge.model_dump(exclude_none=True)
        elif shot.id in fallback:
            item = fallback[shot.id]
            entry.update({
                "decidedBy": f"fallback:{item.method}", "candidateId": item.candidateId, "url": item.url,
                "sourceStart": item.start, "sourceEnd": item.end, "fallbackReason": item.reason,
                "attribution": item.attribution, "score": item.clip,
            })
        frame = middle_frame(path, shot.media.kind)
        entry["_frame"] = frame
        entry["phash"] = det.phash(frame) if frame is not None else None
        rows.append(entry)

    if timeline.durationInFrames != round(ShotsFile.model_validate(ctx.read_json("shots.json")).durationSeconds * fps):
        blockers.append("La duración del timeline no coincide con la de la narración")

    # --- low scores -------------------------------------------------------------------------
    min_score = float(cfg.get("low_score", ctx.section("judge").get("min_score", 0.30)))
    low: list[str] = []
    for entry in rows:
        judge = entry.get("judge") or {}
        reasons = []
        if entry.get("score") is not None and entry["score"] < min_score and not judge:
            reasons.append(f"nota {entry['score']:.2f}")
        if judge and judge.get("confidence", 1) < float(cfg.get("low_confidence", 0.6)):
            reasons.append(f"juez poco seguro ({judge['confidence']:.2f})")
        if entry.get("source") == "generated":
            reasons.append("imagen generada")
        if reasons:
            entry["flag"] = "low"
            low.append(f"{entry['shotId']} ({mmss(entry['start'])}) — {', '.join(reasons)} — «{entry['text'][:60]}»")

    # --- repeats: same source with overlapping timestamps, or near-identical pictures --------
    repeats: list[str] = []
    media_rows = [e for e in rows if e.get("media")]
    for i, a in enumerate(media_rows):
        for b in media_rows[i + 1:]:
            same_source = a.get("candidateId") and a.get("candidateId") == b.get("candidateId")
            if same_source and a.get("sourceStart") is not None and b.get("sourceStart") is not None:
                overlap = a["sourceStart"] < b["sourceEnd"] and b["sourceStart"] < a["sourceEnd"]
            else:
                overlap = bool(same_source)
            close = a.get("phash") and b.get("phash") and det.hamming(a["phash"], b["phash"]) <= int(cfg.get("max_phash_distance", 6))
            if overlap or close:
                why = "mismo tramo de la misma fuente" if overlap else "imagen casi idéntica"
                repeats.append(f"{a['shotId']} ↔ {b['shotId']}: {why}")
                a.setdefault("flag", "repeat")
                b.setdefault("flag", "repeat")
    if repeats:
        warnings.append(f"{len(repeats)} posibles repeticiones")

    # --- shares, cost ---------------------------------------------------------------------------
    by_count = Counter(e["category"] for e in media_rows)
    by_time: Counter = Counter()
    for e in media_rows:
        by_time[e["category"]] += e["end"] - e["start"]
    footage_time = sum(by_time.values()) or 1
    costs = json.loads((ctx.work_dir / COSTS_FILE).read_text("utf-8")) if (ctx.work_dir / COSTS_FILE).is_file() else {"entries": []}
    spend: Counter = Counter()
    for item in costs.get("entries", []):
        spend[f"{item['stage']} · {item['operation']}"] += float(item.get("usd", 0))
    total_usd = sum(spend.values())

    # --- outputs ----------------------------------------------------------------------------
    sheet = contact_sheet(rows, timeline.shots, columns=int(cfg.get("columns", 14)))
    cv2.imwrite(str(qa_dir / "contact-sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
    manifest = [{k: v for k, v in e.items() if not k.startswith("_") and v is not None} for e in rows]
    (ctx.out_dir / "manifest.json").write_text(
        json.dumps({"slug": ctx.slug, "title": timeline.title, "fps": fps, "shots": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ctx.out_dir / "creditos.txt").write_text(credits_text(rows), encoding="utf-8")
    status = "BLOQUEADO" if blockers else "OK"
    report = render_report(ctx.slug, timeline, status, blockers, warnings, low, repeats, by_count, by_time, footage_time,
                           spend, total_usd, rows)
    (qa_dir / "report.md").write_text(report, encoding="utf-8")
    (qa_dir / "qa.json").write_text(json.dumps({
        "status": status, "blockers": blockers, "warnings": warnings, "lowScore": low, "repeats": repeats,
        "overFiveSeconds": sum("máximo 5 s" in b for b in blockers),
        "withoutCredit": sum("sin crédito" in b for b in blockers),
        "shareByShots": dict(by_count), "shareBySeconds": {k: round(v / footage_time, 4) for k, v in by_time.items()},
        "costUsd": round(total_usd, 4),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"   QA {status}: {len(blockers)} bloqueos · {len(low)} planos flojos · {len(repeats)} repeticiones")
    print("   Reparto (tiempo en pantalla): " + ", ".join(f"{k} {v / footage_time:.0%}" for k, v in by_time.most_common()))
    print(f"   Coste acumulado: {total_usd:.3f} $ · informe: {(qa_dir / 'report.md').relative_to(ctx.root)}")
    if blockers:
        raise QABlocked("QA bloquea el render: " + " | ".join(blockers[:6]))


# --- helpers ---------------------------------------------------------------------------------


def contact_sheet(rows: list[dict[str, Any]], shots: list, columns: int = 14) -> np.ndarray:
    tile_w, tile_h, label_h = 256, 144, 22
    colours = {"low": (0, 170, 255), "repeat": (0, 0, 230)}  # BGR: amber, red
    tiles = []
    for entry, shot in zip(rows, shots):
        frame = entry.get("_frame")
        if frame is None:
            tile = np.full((tile_h, tile_w, 3), 26, np.uint8)
            title = (shot.text or "")[:30]
            cv2.putText(tile, "DATOS", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
            cv2.putText(tile, title, (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 220, 220), 1)
        else:
            tile = cv2.resize(frame, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
        if entry.get("flag"):
            cv2.rectangle(tile, (0, 0), (tile_w - 1, tile_h - 1), colours[entry["flag"]], 5)
        label = np.zeros((label_h, tile_w, 3), np.uint8)
        text = f"{entry['shotId']} {mmss(entry['start'])} {shot.type[:5]} {(entry.get('source') or '')[:8]}"
        cv2.putText(label, text, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        tiles.append(np.vstack([tile, label]))
    while len(tiles) % columns:
        tiles.append(np.zeros_like(tiles[0]))
    return np.vstack([np.hstack(tiles[i : i + columns]) for i in range(0, len(tiles), columns)])


def credits_text(rows: list[dict[str, Any]]) -> str:
    """Grouped by source, in order of first appearance, with the times each one is used."""

    groups: dict[str, dict[str, Any]] = {}
    generated = 0
    for entry in rows:
        source = entry.get("source")
        if not source:
            continue
        if source == "generated":
            generated += 1
            continue
        key = entry.get("url") or entry.get("candidateId") or entry["shotId"]
        group = groups.setdefault(key, {"entry": entry, "times": []})
        group["times"].append(mmss(entry["start"]))
    sections = {"terceros (YouTube)": [], "imágenes libres": [], "Pexels": []}
    for group in groups.values():
        e = group["entry"]
        times = ", ".join(dict.fromkeys(group["times"]))
        if e["source"] == "youtube":
            line = f"- {e.get('channel') or e['credit'].removeprefix('Fuente: ')} — «{e.get('title', '')}»: {e.get('url')} ({times})"
        else:
            line = f"- {e.get('attribution') or e['credit'].removeprefix('Fuente: ')} ({times})"
        sections.setdefault(category(e["source"]), []).append(line)
    parts = ["FUENTES Y CRÉDITOS", ""]
    titles = {"terceros (YouTube)": "Vídeos de terceros (fragmentos de menos de 5 s):",
              "imágenes libres": "Imágenes con licencia libre:", "Pexels": "Pexels:"}
    for name, lines in sections.items():
        if lines:
            parts += [titles.get(name, name), *lines, ""]
    if generated:
        parts += [f"{generated} imagen(es) generada(s) con IA.", ""]
    return "\n".join(parts)


def render_report(slug, timeline, status, blockers, warnings, low, repeats, by_count, by_time, footage_time,
                  spend, total_usd, rows) -> str:
    third = [e for e in rows if e.get("source") in THIRD_PARTY]
    longest = max((e.get("clipSeconds", 0) for e in third), default=0)
    lines = [
        f"# QA — {timeline.title} ({slug})", "",
        f"**Estado: {status}** · {len(timeline.shots)} planos · {timeline.durationInFrames / timeline.fps / 60:.1f} min", "",
        "| Comprobación | Resultado |", "|---|---|",
        f"| Clips de terceros de más de 5 s | **{sum('máximo 5 s' in b for b in blockers)}** (el más largo: {longest:.2f} s) |",
        f"| Planos de terceros sin crédito | **{sum('sin crédito' in b for b in blockers)}** |",
        f"| Posibles repeticiones | {len(repeats)} |",
        f"| Planos flojos a revisar | {len(low)} |",
        f"| Coste total de APIs | {total_usd:.3f} $ |", "",
    ]
    if blockers:
        lines += ["## Bloqueos (el render no se lanza)", "", *[f"- {b}" for b in blockers], ""]
    lines += ["## Reparto por fuente", "", "| Fuente | Planos | Tiempo en pantalla |", "|---|---|---|"]
    for name, seconds in by_time.most_common():
        lines.append(f"| {name} | {by_count[name]} | {seconds / footage_time:.0%} ({seconds:.0f} s) |")
    lines += ["", "## Planos flojos (marco ámbar en la hoja de contactos)", ""]
    lines += [f"- {item}" for item in low] or ["- Ninguno"]
    lines += ["", "## Posibles repeticiones (marco rojo)", ""]
    lines += [f"- {item}" for item in repeats] or ["- Ninguna"]
    lines += ["", "## Coste por etapa", "", "| Etapa · operación | USD |", "|---|---|"]
    lines += [f"| {k} | {v:.4f} |" for k, v in spend.most_common()]
    lines += [f"| **Total** | **{total_usd:.4f}** |", "",
              "Nota: el coste es acumulado del proyecto (incluye re-ejecuciones y pruebas).", ""]
    return "\n".join(lines)


def validate(ctx: RunContext) -> bool:
    status = json.loads((ctx.out_dir / "qa" / "qa.json").read_text("utf-8"))["status"]
    if status != "OK":
        raise QABlocked("La última QA está bloqueada")
    return (ctx.out_dir / "manifest.json").is_file() and (ctx.out_dir / "creditos.txt").is_file()
