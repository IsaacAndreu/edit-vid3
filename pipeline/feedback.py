"""«Errores»: you mark the clips of a finished video as right or wrong, and the program learns from it.

The studio shows every shot of a video (a frame of the final video, the sentence it goes with, where the clip came
from) with three buttons: Correcta, Incorrecta (+ why) and Dudosa. The labels live in out/_errores/etiquetas.json,
for all videos together, and are used three ways:

- a fragment marked wrong is never used again, in any video (judge.used_elsewhere adds them); another person blocks a
  few seconds around it, and a cartoon or a watermark the whole source video;
- `Rehacer con correcciones` reruns this video from the fallback stage: the shots marked wrong get a replacement
  (work/<slug>/revision.json is an input of that stage);
- «Para ir mejorando»: how many clips were right, per reason and per way the clip was found (judge, fallback by
  protagonist, stock…), so it is clear which part of the program makes the mistakes.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

LABELS = "out/_errores/etiquetas.json"
REVISION = "revision.json"                    # in work/<slug>/: this video's wrong shots (input of fallback)
VERDICTS = ("correcta", "incorrecta", "dudosa")
REASONS = {
    "persona_equivocada": "Sale otra persona",
    "no_tiene_que_ver": "No tiene que ver con la frase",
    "dibujo_animado": "Dibujo animado / videojuego",
    "roto": "Roto, negro o muy mala calidad",
    "texto_marca_agua": "Texto encima o marca de agua",
    "repetido": "Repetido",
    "habia_mejor": "Había una opción mejor",
    "otro": "Otro",
}
NOT_BLOCKED = {"habia_mejor", "repetido"}       # the clip itself is fine elsewhere: it is not put on the black list
WHOLE_SOURCE = {"dibujo_animado", "texto_marca_agua"}   # the whole source video is out
WIDER = {"persona_equivocada": 4.0}           # another athlete is usually on screen for a while: block around it too
METHODS = {"judge": "Juez (búsqueda del plano)", "score": "Puntuación directa", "editor": "Elegido a mano",
           "next-option": "Siguiente opción", "protagonist": "Otro clip del protagonista",
           "protagonist-filler": "Relleno del protagonista", "event-footage": "Clip del mismo evento",
           "web-photo": "Foto de la web", "library-photo": "Foto de la biblioteca", "pexels-video": "Vídeo de stock",
           "pexels-photo": "Foto de stock", "generated": "Imagen generada", "coldopen": "Arranque (cold open)"}
_LOCK = threading.Lock()


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


def labels(root: Path) -> dict[str, dict[str, Any]]:
    """"<slug>/<shotId>" → {verdict, reason, candidateId, start, end, method, text, source, at}."""

    return _read(root / LABELS) or {}


# --- what is on screen ---------------------------------------------------------------------------------------

def _sources(work: Path) -> dict[str, dict[str, Any]]:
    """shotId → where its clip came from (the fallback replacement wins over the judge's choice)."""

    out: dict[str, dict[str, Any]] = {}
    for s in (_read(work / "selection.json") or {}).get("selections", []):
        if s.get("status") == "selected":
            out[s["shotId"]] = {"candidateId": s.get("candidateId"), "start": s.get("start"), "end": s.get("end"),
                                "url": s.get("url"), "title": s.get("title"), "channel": s.get("channel"),
                                "method": s.get("decidedBy") or "judge", "source": s.get("source")}
    for item in (_read(work / "fallback.json") or {}).get("items", []):
        attribution = str(item.get("attribution") or "")
        title = attribution.split("\"")[1] if attribution.count("\"") >= 2 else ""
        out[item["shotId"]] = {"candidateId": item.get("candidateId"), "start": item.get("start"), "end": item.get("end"),
                               "url": item.get("url"), "title": title, "channel": str(item.get("credit") or "").removeprefix("Fuente: "),
                               "method": item.get("method"), "source": item.get("source")}
    return out


def shots(root: Path, slug: str) -> list[dict[str, Any]]:
    """The shots of the final video that show a clip or photo, in order, with their label if any."""

    work = root / "work" / slug
    timeline = _read(work / "timeline.json") or {}
    fps = float(timeline.get("fps") or 30)
    sources = _sources(work)
    texts = {s["id"]: s.get("text", "") for s in (_read(work / "shots.json") or {}).get("shots", [])}
    marked = labels(root)
    out = []
    for shot in timeline.get("shots", []):
        media = shot.get("media") or {}
        if not media.get("src"):
            continue
        base = shot["id"].split("-")[0]
        src = sources.get(base, {})
        if shot.get("coldOpen"):
            src = {**src, "method": "coldopen"}
        start = shot.get("from", 0) / fps
        out.append({
            "id": shot["id"], "at": round(start, 1), "mid": round(start + shot.get("durationInFrames", 0) / fps / 2, 2),
            "text": shot.get("text") or texts.get(base, ""), "credit": media.get("credit", ""),
            "kind": media.get("kind"), "source": media.get("source") or src.get("source"),
            "title": src.get("title") or "", "url": src.get("url") or "", "method": src.get("method") or "",
            "channel": src.get("channel") or "",
            "candidateId": src.get("candidateId"), "start": src.get("start"), "end": src.get("end"),
            "label": marked.get(f"{slug}/{shot['id']}"),
        })
    return out


def frame(root: Path, slug: str, shot_id: str) -> Path | None:
    """A frame of that shot from the final video (cached in out/<slug>/revision/), else from its own media."""

    target = root / "out" / slug / "revision" / f"{shot_id}.jpg"
    if target.is_file():
        return target
    item = next((s for s in shots(root, slug) if s["id"] == shot_id), None)
    if item is None:
        return None
    final = root / "out" / slug / "video-final.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    if final.is_file():
        command = ["ffmpeg", "-y", "-v", "error", "-ss", f"{item['mid']:.2f}", "-i", str(final), "-frames:v", "1",
                   "-vf", "scale=480:-2", "-q:v", "4", str(target)]
    else:
        timeline = _read(root / "work" / slug / "timeline.json") or {}
        shot = next((s for s in timeline.get("shots", []) if s["id"] == shot_id), {})
        src = root / "work" / slug / str((shot.get("media") or {}).get("src") or "")
        if not src.is_file():
            return None
        command = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4",
                   str(target)]
    done = subprocess.run(command, capture_output=True)
    return target if done.returncode == 0 and target.is_file() else None


# --- labelling -----------------------------------------------------------------------------------------------

def label(root: Path, slug: str, shot_id: str, verdict: str | None, reason: str = "") -> dict[str, Any]:
    """Set (or with verdict None, clear) the label of one shot."""

    if verdict is not None and verdict not in VERDICTS:
        raise ValueError(f"Veredicto desconocido: {verdict}")
    if verdict == "incorrecta" and reason not in REASONS:
        raise ValueError("Elige el motivo")
    item = next((s for s in shots(root, slug) if s["id"] == shot_id), None)
    if item is None:
        raise FileNotFoundError(shot_id)
    with _LOCK:
        data = labels(root)
        key = f"{slug}/{shot_id}"
        if verdict is None:
            data.pop(key, None)
        else:
            data[key] = {"verdict": verdict, "reason": reason if verdict == "incorrecta" else "",
                         **{k: item[k] for k in ("candidateId", "start", "end", "method", "text", "source", "url", "title",
                                                 "channel")},
                         "videoChannel": _video_channel(root, slug),
                         "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _write(root / LABELS, data)
        _revision(root, slug, data)
    return data.get(key) or {}


def _revision(root: Path, slug: str, data: dict[str, dict[str, Any]]) -> None:
    """work/<slug>/revision.json: this video's shots marked wrong (fallback replaces them)."""

    wrong = {k.split("/", 1)[1]: {"reason": v["reason"], "candidateId": v.get("candidateId"), "start": v.get("start")}
             for k, v in sorted(data.items()) if k.startswith(f"{slug}/") and v["verdict"] == "incorrecta"}
    path = root / "work" / slug / REVISION
    if wrong or path.is_file():
        if path.parent.is_dir():
            _write(path, {"wrong": wrong})


def wrong_fragments(root: Path) -> dict[str, list[tuple[float | None, float | None]]]:
    """candidateId → [(start, end)] never to use again; (None, None) = the whole source."""

    out: dict[str, list[tuple[float | None, float | None]]] = {}
    for entry in labels(root).values():
        cid = entry.get("candidateId")
        if entry.get("verdict") != "incorrecta" or not cid or entry.get("reason") in NOT_BLOCKED:
            continue
        whole = entry.get("reason") in WHOLE_SOURCE or entry.get("start") is None
        pad = WIDER.get(entry.get("reason"), 0.0)
        start, end = entry.get("start"), entry.get("end") if entry.get("end") is not None else entry.get("start")
        out.setdefault(cid, []).append((None, None) if whole else (max(0.0, start - pad), end + pad))
    return out


def is_wrong(fragments: dict[str, list[tuple[float | None, float | None]]], candidate_id: str | None,
             start: float | None, end: float | None) -> bool:
    for a, b in fragments.get(candidate_id or "", []):
        if a is None or start is None:
            return True
        if start < (b or a) + 0.5 and a < (end if end is not None else start) + 0.5:
            return True
    return False


def wrong_shots(work: Path) -> dict[str, str]:
    """shotId → reason, for this video (from work/<slug>/revision.json)."""

    return {sid: REASONS.get(v.get("reason"), v.get("reason") or "") for sid, v in
            ((_read(work / REVISION) or {}).get("wrong") or {}).items()}


# --- what the program learns from the labels ---------------------------------------------------------------

CHANNEL_FAULTS = {"no_tiene_que_ver", "dibujo_animado", "roto", "texto_marca_agua"}   # the source channel's fault
BLOCK_AFTER = 3                               # a YouTube channel with this many such clips marked wrong is out


def _video_channel(root: Path, slug: str) -> str:
    try:
        from .context import find_video
        from .web import _channel_of

        return _channel_of(root, find_video(root, slug))
    except Exception:
        return ""


def _with_channels(root: Path) -> list[dict[str, Any]]:
    """The labels, with the source channel and the video's channel filled in for old ones (saved without them)."""

    out, sources, channels = [], {}, {}
    for key, entry in labels(root).items():
        slug = key.split("/", 1)[0]
        entry = dict(entry)
        if not entry.get("channel") and entry.get("candidateId"):
            if slug not in sources:
                sources[slug] = {v.get("candidateId"): v.get("channel") for v in _sources(root / "work" / slug).values()}
            entry["channel"] = sources[slug].get(entry["candidateId"]) or ""
        if "videoChannel" not in entry:
            if slug not in channels:
                channels[slug] = _video_channel(root, slug)
            entry["videoChannel"] = channels[slug]
        out.append({**entry, "slug": slug})
    return out


def blocked_channels(root: Path, after: int = BLOCK_AFTER) -> dict[str, int]:
    """Source channel → clips marked wrong because of the source (unrelated, cartoon, broken, watermark), for the
    channels with at least `after` of them and more wrong than right: never searched or chosen again."""

    wrong: dict[str, int] = {}
    right: dict[str, int] = {}
    names: dict[str, str] = {}
    for entry in _with_channels(root):
        name = str(entry.get("channel") or "").strip()
        if not name or entry.get("source") not in (None, "youtube"):
            continue
        key = name.casefold()
        names.setdefault(key, name)
        if entry.get("verdict") == "incorrecta" and entry.get("reason") in CHANNEL_FAULTS:
            wrong[key] = wrong.get(key, 0) + 1
        elif entry.get("verdict") == "correcta":
            right[key] = right.get(key, 0) + 1
    return {names[k]: n for k, n in sorted(wrong.items(), key=lambda kv: -kv[1]) if n >= after and n > right.get(k, 0)}


def load_learned(root: Path) -> list[str]:
    """Before a video's stages: the channels you taught it to avoid go into the blocklist of every search/choice."""

    from .sourcing import common

    try:
        names = list(blocked_channels(root))
    except Exception:            # a broken labels file never stops a video
        names = []
    common.LEARNED_BLOCKED_CHANNELS = {n.casefold() for n in names}
    return names


def lessons(root: Path, video_channel: str, limit: int = 10) -> str:
    """Your corrections on this channel's videos, as short examples for the judge (newest first, mostly mistakes)."""

    entries = [e for e in _with_channels(root) if e.get("videoChannel") == video_channel and e.get("text")
               and e.get("verdict") in ("correcta", "incorrecta") and e.get("reason") != "habia_mejor"]
    entries.sort(key=lambda e: str(e.get("at") or ""), reverse=True)
    wrong = [e for e in entries if e["verdict"] == "incorrecta"][: max(1, limit * 2 // 3)]
    right = [e for e in entries if e["verdict"] == "correcta"][: limit - len(wrong)]
    lines = []
    for e in [*wrong, *right]:
        what = f"\"{str(e.get('title') or '')[:70]}\"" + (f" ({str(e.get('channel'))[:30]})" if e.get("channel") else "")
        verdict = ("WRONG: " + REASONS.get(e.get("reason"), e.get("reason") or "")) if e["verdict"] == "incorrecta" else "RIGHT"
        lines.append(f"- Narration «{' '.join(str(e['text']).split())[:110]}» → clip {what} → {verdict}")
    return "\n".join(lines)


# --- «Para ir mejorando» -------------------------------------------------------------------------------------

def summary(root: Path) -> dict[str, Any]:
    data = labels(root)
    per_video: dict[str, dict[str, int]] = {}
    per_reason: dict[str, int] = {}
    per_method: dict[str, dict[str, int]] = {}
    for key, entry in data.items():
        slug = key.split("/", 1)[0]
        verdict = entry["verdict"]
        per_video.setdefault(slug, {v: 0 for v in VERDICTS})[verdict] += 1
        method = entry.get("method") or "?"
        per_method.setdefault(method, {v: 0 for v in VERDICTS})[verdict] += 1
        if verdict == "incorrecta":
            per_reason[entry.get("reason") or "otro"] = per_reason.get(entry.get("reason") or "otro", 0) + 1
    total = {v: sum(x[v] for x in per_video.values()) for v in VERDICTS}
    judged = total["correcta"] + total["incorrecta"]
    tips = []
    worst = max(per_method.items(), key=lambda kv: kv[1]["incorrecta"] / max(1, kv[1]["correcta"] + kv[1]["incorrecta"]),
                default=None)
    if worst and worst[1]["incorrecta"] >= 3:
        n = worst[1]["correcta"] + worst[1]["incorrecta"]
        tips.append(f"La mayoría de fallos vienen de «{METHODS.get(worst[0], worst[0])}»: {worst[1]['incorrecta']} de {n} mal.")
    blocked = blocked_channels(root)
    if blocked:
        tips.append("Canales de YouTube que ya no se usan por tus correcciones: "
                    + ", ".join(f"{name} ({n} mal)" for name, n in blocked.items()) + ".")
    if per_reason.get("persona_equivocada", 0) >= 3:
        tips.append("Muchos clips con otra persona: sube fallback.identity_scope a «all» o añade fotos del atleta a la "
                    "biblioteca para que la comprobación de caras tenga con qué comparar.")
    if per_reason.get("no_tiene_que_ver", 0) >= 3:
        tips.append("Clips que no tienen que ver con la frase: pon judge.all: true en el canal para que el juez mire "
                    "todos los planos y no solo los dudosos.")
    if per_reason.get("dibujo_animado", 0) + per_reason.get("roto", 0) >= 2:
        tips.append("Dibujos o clips rotos que se colaron: ya no se volverán a usar esas fuentes.")
    return {
        "total": total, "accuracy": round(100 * total["correcta"] / judged) if judged else None,
        "videos": [{"slug": s, **v, "accuracy": round(100 * v["correcta"] / max(1, v["correcta"] + v["incorrecta"]))}
                   for s, v in sorted(per_video.items())],
        "reasons": [{"reason": r, "name": REASONS.get(r, r), "count": n} for r, n in sorted(per_reason.items(), key=lambda kv: -kv[1])],
        "methods": [{"method": m, "name": METHODS.get(m, m), **v,
                     "accuracy": round(100 * v["correcta"] / max(1, v["correcta"] + v["incorrecta"]))}
                    for m, v in sorted(per_method.items(), key=lambda kv: -kv[1]["incorrecta"])],
        "tips": tips, "reasonNames": REASONS,
    }
