"""«Decisiones del relleno»: the shots where the program could not use the judge's first choice, for you to check.

The fallback stage (pipeline/fallback.py) handles every shot whose clip could not be used as chosen: the judge said
no to every option (the most common case), the clip showed another person, repeated a picture already on screen,
was a cartoon or a broken video, an agency photo with a watermark, or did not download. It then looks for something
else (another clip of the protagonist, of the same event, a photo, stock footage…).

Here each of those shots shows: the sentence, why the program had to look for something else, what it finally
put, and the other analysed options with their frames. You can:
- say «bien así»: what it put is right;
- pick another option, «usar esta»: the video gets that one (as if chosen in the editor) when you press «Aplicar y
  rehacer», and the program learns — a clip the identity check had thrown out as «another person» is never thrown
  out again, and the summary says which checks are too strict (e.g. the judge rejecting everything when there was a
  good option).
Labels go with the «Errores» ones (out/_errores/etiquetas.json); picks to out/_errores/elegidos.json.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PICKS = "out/_errores/elegidos.json"
APPROVED = "out/_errores/aprobados.json"        # fragments you said are right: never thrown out again
REASONS = {
    "el juez no aceptó": "El juez no aceptó ninguna opción",
    "descarga fallida": "No se pudo descargar",
    "repite la imagen": "Repetía una imagen ya usada",
    "marca de agua": "Foto de agencia con marca de agua",
    "dibujo": "Dibujo animado / videojuego",
    "roto": "Vídeo roto o en negro",
    "marcado como error": "Lo marcaste mal en «Errores»",
    "sin opciones": "No había opciones utilizables",
}


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def kind_of(reason: str) -> str:
    low = reason.lower()
    for key, name in REASONS.items():
        if key in low:
            return name
    return "Otra persona en pantalla" if ("persona" in low or "cara" in low or "rótulo" in low or "nombre" in low) else reason[:80]


def option_key(candidate_id: str, start: float | None) -> str:
    return f"{candidate_id}@{'' if start is None else round(float(start), 2)}"


def items(root: Path, slug: str, limit: int = 6) -> list[dict[str, Any]]:
    """Every shot the fallback had to handle, with its options."""

    from .editor import _options
    from .context import RunContext
    from .feedback import METHODS, labels

    work = root / "work" / slug
    fallback = _read(work / "fallback.json") or {}
    selections = {s["shotId"]: s for s in (_read(work / "selection.json") or {}).get("selections", [])}
    texts = {s["id"]: s.get("text", "") for s in (_read(work / "shots.json") or {}).get("shots", [])}
    picks = {k.split("/", 1)[1]: v for k, v in (_read(root / PICKS) or {}).items() if k.startswith(f"{slug}/")}
    marked = labels(root)
    ctx = RunContext.create(slug, root=root, config={})
    rows: list[tuple[str, dict[str, Any] | None, str]] = [(i["shotId"], i, i.get("reason", "")) for i in fallback.get("items", [])]
    rows += [(sid, None, why) for sid, why in (fallback.get("unresolved") or {}).items()]
    out = []
    for shot_id, item, reason in sorted(rows, key=lambda r: r[0]):
        chosen = selections.get(shot_id) or {}
        options, candidates = _options(ctx, shot_id)
        shown = []
        original = chosen if chosen.get("status") == "selected" else None
        if original:                                   # the judge's choice the fallback threw out
            shown.append({"key": option_key(original["candidateId"], original.get("start")), "original": True,
                          "title": original.get("title") or "", "channel": original.get("channel") or "",
                          "kind": original.get("kind"), "score": original.get("score")})
        on_screen = option_key(item["candidateId"], item.get("start")) if item else ""
        for option in options:
            key = option_key(option["candidateId"], option.get("start"))
            if key == on_screen or any(s["key"] == key for s in shown):
                continue
            candidate = candidates.get(option["candidateId"], {})
            shown.append({"key": key, "original": False, "title": candidate.get("title", ""),
                          "channel": candidate.get("channel", ""), "kind": option.get("kind"),
                          "score": round(float(option.get("total") or 0), 2)})
            if len(shown) >= limit:
                break
        judge = (chosen.get("judge") or {}) if isinstance(chosen.get("judge"), dict) else {}
        label = marked.get(f"{slug}/{shot_id}")
        out.append({
            "shot": shot_id, "text": texts.get(shot_id, ""), "reason": reason, "kind": kind_of(reason),
            "judgeReason": judge.get("reason") or "", "method": METHODS.get((item or {}).get("method"), (item or {}).get("method") or ""),
            "resolved": item is not None, "options": shown, "pick": (picks.get(shot_id) or {}).get("key"),
            "verdict": (label or {}).get("verdict"),
        })
    return out


def frame(root: Path, slug: str, shot_id: str, key: str) -> Path | None:
    """A picture of one option (or «final»: what is on screen now), cached in out/<slug>/decisiones/."""

    import cv2

    from .feedback import frame as final_frame
    from .schemas import ShotCandidates

    if key == "final":
        return final_frame(root, slug, shot_id)
    target = root / "out" / slug / "decisiones" / f"{hashlib.sha256(f'{shot_id}:{key}'.encode()).hexdigest()[:16]}.jpg"
    if target.is_file():
        return target
    work = root / "work" / slug
    candidate_id, _, start_text = key.rpartition("@")
    start = float(start_text) if start_text else None
    scores = (_read(work / "scores" / f"{shot_id}.json") or {}).get("options", [])
    selection = next((s for s in (_read(work / "selection.json") or {}).get("selections", [])
                      if s["shotId"] == shot_id and s.get("candidateId") == candidate_id), None)
    option = next((o for o in scores if o["candidateId"] == candidate_id
                   and (start is None or o.get("start") is None or abs(float(o["start"]) - start) < 0.05)), None) or selection
    if option is None:
        return None
    try:
        found = {c.id: c for c in ShotCandidates.model_validate_json(
            (work / "candidates" / f"{shot_id}.json").read_text("utf-8")).candidates}
    except (OSError, ValueError):
        found = {}
    picture = None
    if option.get("kind") == "image" and option.get("analysisPath"):
        picture = cv2.imread(str(root / option["analysisPath"]))
    elif option.get("start") is not None and option.get("end") is not None and candidate_id in found:
        from .judge import _video_frames

        frames = _video_frames(SimpleNamespace(start=float(option["start"]), end=float(option["end"]),
                                               analysisPath=option.get("analysisPath")), found[candidate_id], root)
        picture = frames[len(frames) // 2] if frames else None
    if picture is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    height, width = picture.shape[:2]
    if width > 480:
        picture = cv2.resize(picture, (480, int(height * 480 / width)))
    cv2.imwrite(str(target), picture, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return target


def decide(root: Path, slug: str, shot_id: str, *, ok: bool | None = None, pick: str | None = None) -> dict[str, Any]:
    """ok=True: what the program put is right. pick=<option key>: this one should go there instead."""

    from . import feedback

    found = next((i for i in items(root, slug) if i["shot"] == shot_id), None)
    if found is None:
        raise FileNotFoundError(shot_id)
    if ok:
        feedback.label(root, slug, shot_id, "correcta")
        data = _read(root / PICKS) or {}
        data.pop(f"{slug}/{shot_id}", None)
        _write(root / PICKS, data)
        return {"ok": True}
    option = next((o for o in found["options"] if o["key"] == pick), None)
    if option is None:
        raise ValueError("Esa opción ya no está")
    data = _read(root / PICKS) or {}
    data[f"{slug}/{shot_id}"] = {**option, "reason": found["reason"], "kind": found["kind"], "text": found["text"],
                                 "judgeRejectedAll": "juez no aceptó" in found["reason"],
                                 "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _write(root / PICKS, data)
    try:                                               # what was on screen was not the best: for the «Errores» summary
        feedback.label(root, slug, shot_id, "incorrecta", "habia_mejor")
    except (FileNotFoundError, ValueError):
        pass
    if option.get("original"):                         # the clip a check threw out was right: never again
        candidate_id, _, start = option["key"].rpartition("@")
        approved = _read(root / APPROVED) or []
        approved.append({"candidateId": candidate_id, "start": float(start) if start else None, "slug": slug,
                         "shot": shot_id, "why": found["reason"]})
        _write(root / APPROVED, approved)
    return {"ok": True, "pick": pick}


def approved_fragments(root: Path) -> dict[str, list[tuple[float | None, float | None]]]:
    """candidateId → [(start, start+5)] you said were right after a check threw them out."""

    out: dict[str, list[tuple[float | None, float | None]]] = {}
    for entry in _read(root / APPROVED) or []:
        start = entry.get("start")
        out.setdefault(entry["candidateId"], []).append((start, None if start is None else start + 5))
    return out


def apply(root: Path, slug: str) -> int:
    """The picks of this video into the editor's choices and selection.json: the next run downloads them."""

    from . import editor
    from .context import RunContext

    picks = {k.split("/", 1)[1]: v for k, v in (_read(root / PICKS) or {}).items() if k.startswith(f"{slug}/")}
    if not picks:
        return 0
    ctx = RunContext.create(slug, root=root)
    edits = editor.load(ctx)
    for shot_id, pick in picks.items():
        candidate_id, _, start = pick["key"].rpartition("@")
        edits.setdefault("footage", {})[shot_id] = {"candidateId": candidate_id, **({"start": float(start)} if start else {})}
    editor.save(ctx, edits)
    editor.patch_selection(ctx)
    return len(picks)


def summary(root: Path) -> dict[str, Any]:
    """How the checks did: picks where the judge had rejected everything, and per reason."""

    picks = list((_read(root / PICKS) or {}).values())
    by_reason: dict[str, int] = {}
    for p in picks:
        by_reason[p.get("kind") or "?"] = by_reason.get(p.get("kind") or "?", 0) + 1
    tips = []
    strict = sum(1 for p in picks if p.get("judgeRejectedAll"))
    if strict >= 3:
        tips.append(f"En {strict} planos el juez rechazó todo y tú elegiste una de sus opciones: es demasiado estricto. "
                    "Baja judge.min_accept (0,22 → 0,18) o judge.min_score en config.yaml.")
    restored = sum(1 for p in picks if p.get("original"))
    if restored >= 3:
        tips.append(f"{restored} clips descartados por las comprobaciones eran buenos: la de identidad es demasiado estricta "
                    "(fallback.identity_scope: protagonist, o face_check: false).")
    return {"picks": len(picks), "byReason": by_reason, "tips": tips}
