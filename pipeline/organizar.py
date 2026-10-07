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

SECTIONS = ("TÍTULO", "DESCRIPCIÓN", "ETIQUETAS", "COMENTARIO FIJADO", "POST DE COMUNIDAD", "SUBTÍTULOS",
            "IDEAS PARA LA MINIATURA")


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
        if not (folder / "fotogramas").is_dir() and (folder / "video-final.mp4").is_file():
            stills_from_final(folder)                          # videos made before the stills existed
        files += [{"label": f"Fotograma {n}", "path": f"fotogramas/{p.name}", "still": True}
                  for n, p in enumerate(sorted((folder / "fotogramas").glob("fotograma-*.jpg"),
                                               key=lambda p: int(re.findall(r"\d+", p.stem)[-1])), start=1)]
        files += [{"label": "Recorte del protagonista (PNG)", "path": f"fotogramas/{p.name}"}
                  for p in sorted((folder / "fotogramas").glob("recorte.*"))]
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


def stills_from_final(folder: Path, count: int = 8) -> int:
    """Stills of an already finished video (its final file, graphics included), spread over it, skipping the ends."""

    import subprocess

    video = folder / "video-final.mp4"
    try:
        duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                         str(video)], capture_output=True, text=True, timeout=30).stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return 0
    out = folder / "fotogramas"
    out.mkdir(exist_ok=True)
    made = 0
    for n in range(count):
        at = duration * (0.05 + 0.85 * n / max(1, count - 1))
        target = out / f"fotograma-{n + 1}.jpg"
        done = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
                               "-q:v", "2", str(target)], capture_output=True, timeout=60)
        made += int(done.returncode == 0 and target.is_file())
    return made


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
    wins = winners(root)
    for channel, entry in per.items():
        entry["winners"] = wins.get(channel, [])
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
    return int(sum(counts) / len(counts)) if counts else 0


def draft_script(root: Path, channel: str, idea: dict[str, Any]) -> dict[str, Any]:
    """{title, script, words} for the «Nuevo vídeo» form."""

    from .context import RunContext
    from .llm import complete_json

    title = str(idea.get("title") or "").strip()
    if not title:
        raise ValueError("La idea necesita un título")
    ctx = RunContext.create("_guiones", root=root, channel=channel or None)
    words = _words_per_video(root, channel) or int(ctx.section("ideas").get("words") or 2000)   # a new channel: its profile
    format_name = str(idea.get("format") or "")
    if format_name:
        from .formats import spec

        writing = str(spec(root, format_name).get("escritura") or "").strip()
    else:                                        # the channel's own format, if it has one
        format_name = str(ctx.config.get("format") or "")
        writing = str((ctx.format or {}).get("escritura") or "").strip()
    brief = [f"CANAL: {channel}", f"IDEA: {title}"]
    for key, label in (("note", "NOTA"), ("angle", "ÁNGULO"), ("hook", "GANCHO"), ("research", "COMPROBAR")):
        if idea.get(key):
            brief.append(f"{label}: {idea[key]}")
    if idea.get("outline"):
        brief.append("ESQUEMA:\n" + "\n".join(f"- {x}" for x in idea["outline"]))
    brief.append(f"LONGITUD: unas {words} palabras (como los vídeos del canal).")
    if writing:
        brief.append(f"ESTRUCTURA OBLIGATORIA DEL FORMATO «{format_name}»:\n{writing}")
    reference = _reference_script(root, channel)
    if reference:
        brief.append(f"GUION DE REFERENCIA DEL CANAL (solo el estilo):\n{reference}")
    result = complete_json(ctx, stage="guiones", section="planner", system=DRAFT_SYSTEM, user="\n\n".join(brief),
                           max_tokens=max(9000, int(words * 2.4)), use_cache=False)       # long documentaries too
    script = str(result.get("script") or "").strip()
    if len(script.split()) < 200:
        raise RuntimeError("El borrador ha salido demasiado corto; vuelve a probar")
    return {"title": str(result.get("title") or title).strip(), "script": script + "\n", "words": len(script.split()),
            "check": script.count("[COMPROBAR]"), "format": format_name}


# --- «doblar lo que gana»: more of what works -------------------------------------------------------------------

SIMILAR = "out/_ideas_similares"

SIMILAR_SYSTEM = """
Eres el estratega de contenidos de un canal documental de YouTube. Te paso un vídeo del canal que ha funcionado
MUCHO mejor que los demás (su título, su formato y el arranque del guion) y los temas que el canal ya ha hecho.
Propón {count} temas NUEVOS que repitan lo que hizo funcionar ese vídeo (el mismo tipo de historia, de gancho y de
promesa del título, para el mismo público), sin repetir ninguno de los hechos. Devuelve SOLO JSON:
{"ideas": [{"title": "título de trabajo con gancho", "note": "el ángulo en 1 frase: por qué es «otro como ese»"}]}
""".strip()


def winners(root: Path, top: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Per channel, the videos that beat the channel's usual on YouTube (from Estadísticas), best first."""

    try:
        from .estadisticas import report

        videos = report(root)["videos"]
    except Exception:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for v in videos:
        yt = v.get("youtube") or {}
        if not yt.get("views"):
            continue
        out.setdefault(v["channel"], []).append({"slug": v["slug"], "title": yt.get("title") or v["title"],
                                                 "views": yt["views"], "vsChannel": yt.get("vsChannel"),
                                                 "thumbnail": yt.get("thumbnail") or ""})
    for channel, rows in out.items():
        rows.sort(key=lambda r: (-(r["vsChannel"] or 0), -r["views"]))
        good = [r for r in rows if (r["vsChannel"] or 0) >= 1.3]
        out[channel] = (good or rows[:1] if len(rows) >= 2 else [])[:top]
        for r in out[channel]:
            r["format"] = _format_name(root, r["slug"])
    return {c: r for c, r in out.items() if r}


def _format_name(root: Path, slug: str) -> str:
    try:
        from .context import RunContext

        return str(RunContext.create(slug, root=root).config.get("format") or "")
    except Exception:
        return ""


def similar_ideas(root: Path, slug: str, count: int = 5, refresh: bool = False) -> dict[str, Any]:
    """New topics «like this one that worked»: same kind of story, hook and audience, none already done."""

    import json

    from . import agenda
    from .context import RunContext, find_video
    from .llm import complete_json

    cache = root / SIMILAR / f"{slug}.json"
    if cache.is_file() and not refresh:
        return json.loads(cache.read_text("utf-8"))
    folder = find_video(root, slug)
    ctx = RunContext.create(slug, root=root)
    title = (folder / "titulo.txt").read_text("utf-8").strip() if (folder / "titulo.txt").is_file() else slug
    script = (folder / "guion.txt").read_text("utf-8")[:1500] if (folder / "guion.txt").is_file() else ""
    channel = next((v["channel"] for v in agenda.videos(root) if v["slug"] == slug), "")
    done = [v["title"] or v["slug"] for v in agenda.videos(root) if v["channel"] == channel]
    format_name = str(ctx.config.get("format") or "")
    result = complete_json(ctx, stage="ideas", section="planner", max_tokens=1200, use_cache=False,
                           system=SIMILAR_SYSTEM.replace("{count}", str(count)),
                           user=f"VÍDEO QUE FUNCIONÓ: {title}\nFORMATO: {format_name or '(el del canal)'}\n\nARRANQUE DEL GUION:\n{script}"
                                f"\n\nTEMAS YA HECHOS (no repetir):\n" + "\n".join(f"- {t}" for t in done[-80:]))
    ideas = [{"title": str(i.get("title") or "").strip(), "note": str(i.get("note") or "").strip(), "format": format_name}
             for i in result.get("ideas", []) if isinstance(i, dict) and str(i.get("title") or "").strip()][:count]
    data = {"slug": slug, "title": title, "channel": channel, "format": format_name, "ideas": ideas}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data
