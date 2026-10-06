"""The two pages of the daily routine: «Para subir» (what is made and not out yet, with everything YouTube Studio
asks for) and «Guiones» (which days of the calendar have no video yet, per channel, and a first draft of a script
from an idea).

- Para subir: the finished videos not marked as uploaded, in the order they go out (the calendar's slot), each with
  the sections of youtube.txt to copy (titles, description with chapters, tags, pinned comment, community post) and
  the files to download (video, thumbnails, subtitles, shorts). «Ya está subido» marks it (housekeeping.published).
- Guiones: the calendar's next `days` days, per channel: the slots with no video at all (a script to write) and the
  ones whose video still lacks its script; the board's ideas for that channel next to them.
- Draft: one LLM call writes a script in the channel's voice (its latest script as the style reference) with `## `
  chapters, from an idea. Facts it is not sure of come marked [COMPROBAR]: it is a draft for you to fix.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SECTIONS = ("TÍTULO", "DESCRIPCIÓN", "ETIQUETAS", "COMENTARIO FIJADO", "POST DE COMUNIDAD", "SUBTÍTULOS")


def youtube_sections(text: str) -> dict[str, str]:
    """youtube.txt → {"TÍTULO": "...", "DESCRIPCIÓN": "...", …} (a header line starts each block)."""

    out: dict[str, str] = {}
    current, lines = None, []
    for line in text.splitlines():
        header = next((s for s in SECTIONS if line.strip().upper().startswith(s)), None)
        if header and (line.strip().upper() == header or line.strip().upper().startswith(header + " (")
                       or line.strip().upper().startswith(header + ":")):
            if current:
                out[current] = "\n".join(lines).strip()
            current, lines = header, ([line.split(":", 1)[1].strip()] if ":" in line else [])
            continue
        lines.append(line)
    if current:
        out[current] = "\n".join(lines).strip()
    return out


def to_upload(root: Path) -> list[dict[str, Any]]:
    from . import agenda

    listed = agenda.videos(root)
    slots = {s["video"]["slug"]: s for s in agenda.plan(root, days=60, listed=listed) if s["video"]}
    out = []
    for video in listed:
        if video["status"] != "hecho":
            continue
        folder = root / "out" / video["slug"]
        try:
            sections = youtube_sections((folder / "youtube.txt").read_text("utf-8"))
        except OSError:
            sections = {}
        titles = [re.sub(r"^\d+\.\s*", "", t.strip(" -•\t")) for t in sections.get("TÍTULO", "").splitlines() if t.strip()]
        files = []
        if (folder / "video-final.mp4").is_file():
            files.append({"label": "Vídeo", "path": "video-final.mp4",
                          "mb": round((folder / "video-final.mp4").stat().st_size / 1e6)})
        files += [{"label": f"Miniatura {n}", "path": f"miniaturas/{p.name}", "image": True}
                  for n, p in enumerate(sorted((folder / "miniaturas").glob("*.jpg")), start=1)]
        files += [{"label": f"Subtítulos ({p.stem.split('.')[-1]})", "path": p.name} for p in sorted(folder.glob("subtitulos*.srt"))]
        files += [{"label": f"Short {n}", "path": f"shorts/{p.name}"}
                  for n, p in enumerate(sorted((folder / "shorts").glob("*.mp4")), start=1)]
        slot = slots.get(video["slug"]) or {}
        out.append({
            **video, "titles": titles, "sections": {k: v for k, v in sections.items() if k != "TÍTULO"},
            "files": files, "date": slot.get("date"), "time": slot.get("time"),
            "shortsText": _read(folder / "shorts" / "shorts.txt"),
        })
    return sorted(out, key=lambda v: (v["date"] or "9999", v["doneAt"] or 0))


def _read(path: Path) -> str:
    try:
        return path.read_text("utf-8").strip()
    except OSError:
        return ""


def scripts_needed(root: Path, days: int = 14) -> list[dict[str, Any]]:
    """Per channel with a calendar: the coming days with no video (a script to write), the videos still without
    a script, and the board's ideas for it."""

    from . import agenda

    listed = agenda.videos(root)
    slots = agenda.plan(root, days=days, listed=listed)
    ideas = agenda.board(root)["idea"]
    per: dict[str, dict[str, Any]] = {}
    for slot in slots:
        if slot["past"]:
            continue
        entry = per.setdefault(slot["channel"], {"channel": slot["channel"], "empty": [], "noScript": [], "slots": 0})
        entry["slots"] += 1
        if slot["video"] is None:
            entry["empty"].append({"date": slot["date"], "time": slot["time"], "deadline": slot["deadline"]})
        elif slot["video"]["status"] == "falta guion":
            entry["noScript"].append({"date": slot["date"], "slug": slot["video"]["slug"]})
    ready = {}
    for video in listed:
        if video["status"] in ("hecho", "en cola", "haciendo", "error", "falta voz"):
            ready[video["channel"]] = ready.get(video["channel"], 0) + (video["status"] != "falta voz")
    for channel, entry in per.items():
        entry["missing"] = len(entry["empty"]) + len(entry["noScript"])
        entry["ideas"] = [i for i in ideas if i["channel"] in (channel, "")][:8]
        entry["ready"] = ready.get(channel, 0)
    return sorted(per.values(), key=lambda e: (-e["missing"], e["channel"]))


def scripts_text(root: Path, days: int = 7) -> str:
    """For the Sunday message: how many scripts each channel needs for the coming week."""

    needed = [e for e in scripts_needed(root, days) if e["missing"]]
    if not needed:
        return "📝 Guiones: la semana que viene está cubierta en todos los canales."
    total = sum(e["missing"] for e in needed)
    lines = [f"📝 Te faltan {total} guion(es) para los próximos {days} días:"]
    for e in needed:
        when = ", ".join(_short_day(x["date"]) for x in [*e["empty"], *e["noScript"]])
        lines.append(f"  • {e['channel']}: {e['missing']} ({when})")
    return "\n".join(lines)


def _short_day(iso: str) -> str:
    names = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    d = date.fromisoformat(iso)
    return f"{names[d.weekday()]} {d.day}"


# --- a first draft of a script --------------------------------------------------------------------------------

DRAFT_SYSTEM = """
Eres el guionista de un canal documental de YouTube. Escribe el GUION COMPLETO de un vídeo a partir de una idea,
con la voz y el estilo del guion de referencia del canal (ritmo, tono, cómo arranca y cómo cierra), sin copiar sus
frases. Devuelve SOLO JSON: {"title": "título de trabajo", "script": "el guion"}.
Reglas del guion:
- Texto para leer en voz alta (lo lee una voz sintética): frases cortas, sin acotaciones, sin emojis, sin listas.
- Arranque de 15-20 s que enganche con lo más fuerte de la historia; nada de «hola, bienvenidos».
- 4-7 capítulos marcados con una línea propia «## TÍTULO EN MAYÚSCULAS» (no antes del arranque).
- Cifras, fechas y nombres solo si estás seguro. Si no lo estás, escribe el dato y detrás [COMPROBAR].
- Cierra con una pregunta a la audiencia y una frase que lleve al siguiente vídeo.
""".strip()


def _reference_script(root: Path, channel: str) -> str:
    from .context import video_folders
    from .web import _channel_of

    mine = [f for f in video_folders(root) if (f / "guion.txt").is_file() and _channel_of(root, f) == channel]
    if not mine:
        return ""
    latest = max(mine, key=lambda f: (f / "guion.txt").stat().st_mtime)
    return (latest / "guion.txt").read_text("utf-8")[:3500]


def _words_per_video(root: Path, channel: str) -> int:
    from .context import video_folders
    from .web import _channel_of

    counts = [len((f / "guion.txt").read_text("utf-8").split()) for f in video_folders(root)
              if (f / "guion.txt").is_file() and _channel_of(root, f) == channel]
    return int(sum(counts) / len(counts)) if counts else 2000


def draft_script(root: Path, channel: str, idea: dict[str, Any]) -> dict[str, Any]:
    """{title, script, words} for the «Nuevo vídeo» form."""

    from .context import RunContext
    from .llm import complete_json

    title = str(idea.get("title") or "").strip()
    if not title:
        raise ValueError("La idea necesita un título")
    ctx = RunContext.create("_guiones", root=root, channel=channel or None)
    words = _words_per_video(root, channel)
    brief = [f"CANAL: {channel}", f"IDEA: {title}"]
    for key, label in (("note", "NOTA"), ("angle", "ÁNGULO"), ("hook", "GANCHO"), ("research", "COMPROBAR")):
        if idea.get(key):
            brief.append(f"{label}: {idea[key]}")
    if idea.get("outline"):
        brief.append("ESQUEMA:\n" + "\n".join(f"- {x}" for x in idea["outline"]))
    brief.append(f"LONGITUD: unas {words} palabras (como los vídeos del canal).")
    reference = _reference_script(root, channel)
    if reference:
        brief.append(f"GUION DE REFERENCIA DEL CANAL (solo el estilo):\n{reference}")
    result = complete_json(ctx, stage="guiones", section="planner", system=DRAFT_SYSTEM, user="\n\n".join(brief),
                           max_tokens=9000, use_cache=False)
    script = str(result.get("script") or "").strip()
    if len(script.split()) < 200:
        raise RuntimeError("El borrador ha salido demasiado corto; vuelve a probar")
    return {"title": str(result.get("title") or title).strip(), "script": script + "\n", "words": len(script.split()),
            "check": script.count("[COMPROBAR]")}
