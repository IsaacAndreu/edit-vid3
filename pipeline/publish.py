"""out/<slug>/youtube.txt — everything to paste into YouTube Studio when uploading by hand.

Title (titulo.txt), a short description and tags written from the script (one cheap LLM call; the
file is still written without them if it fails), the chapter list with its timestamps (the first
at 0:00, as YouTube requires) and the source names (the description stays under YouTube's 5000
characters; the full list with links and times is creditos.txt). Nothing is uploaded.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .context import RunContext
from .llm import complete_json
from .schemas import Timeline

STAGE = "qa"
OUTPUT = "youtube.txt"

SYSTEM = """
Eres el community manager de un canal de YouTube de documentales. Con el guion de un vídeo
devuelve SOLO JSON: {"description": "2-3 frases en el idioma del guion que enganchen sin
destripar el final, sin emojis ni hashtags", "tags": ["8-15 etiquetas cortas: nombres propios,
deporte, competiciones, en el idioma del guion y alguna en inglés"],
"pinnedComment": "comentario para fijar: 1-2 frases con una pregunta que provoque opiniones y
debate sobre la historia (¿quién es el mejor…?, ¿qué habrías hecho…?), sin destripar el final",
"communityPost": "post de comunidad para anunciar el vídeo: 2-3 frases con gancho + una pregunta
o encuesta (con 2-4 opciones al final)"}. No inventes datos que no estén en el guion.
""".strip()


def mmss(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def chapter_lines(timeline: Timeline, intro: str = "Intro") -> list[str]:
    """YouTube chapters: first at 0:00, at least 3, each at least 10 s long; otherwise none."""

    marks = [(0.0, intro)]
    for shot in timeline.shots:
        if shot.type == "chapter" and shot.chapterTitle:
            seconds = shot.from_ / timeline.fps
            title = shot.chapterTitle.capitalize()
            if seconds - marks[-1][0] >= 10:
                marks.append((seconds, title))
            else:
                marks[-1] = (marks[-1][0], title if marks[-1][0] > 0 else marks[-1][1])
    if len(marks) < 3:
        return []
    return [f"{mmss(t)} {name}" for t, name in marks]


DESCRIPTION_LIMIT = 5000   # YouTube's hard limit for the description


def compact_credits(rows: list[dict[str, Any]], budget: int) -> str:
    """Source names only, grouped — the full list with links and times stays in creditos.txt."""

    groups: dict[str, list[str]] = {"Vídeos": [], "Fotografías": [], "Imágenes con licencia libre": [], "Pexels": []}
    where = {"youtube": "Vídeos", "web": "Fotografías", "pexels": "Pexels"}
    for row in rows:
        source = row.get("source")
        if not source or source == "generated":
            continue
        name = str(row.get("credit") or "").removeprefix("Fuente: ").strip()
        group = groups[where.get(source, "Imágenes con licencia libre")]
        if name and name not in group:
            group.append(name)
    text = "Fuentes (fragmentos de menos de 5 s, con fines de comentario):\n" + "\n".join(
        f"{label}: {', '.join(names)}" for label, names in groups.items() if names
    )
    return text if len(text) <= budget else text[: max(0, budget - 40)].rsplit(",", 1)[0] + " y otros."


def _srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def subtitles(timeline: Timeline, words: list[dict[str, Any]], line: int = 42, max_seconds: float = 6.0) -> str:
    """SRT of the narration at its place in the video (after the cold open, around the moments):
    cues of ≤ 2 lines of ≤ 42 characters, cut at sentence ends, pauses and long commas."""

    fps = timeline.fps
    gaps = timeline.audio.voiceGaps

    def final(t: float) -> float:
        frame = round(t * fps)
        return (timeline.audio.voiceFrom + frame + sum(b for at, b in gaps if at <= frame)) / fps

    cues: list[list[dict[str, Any]]] = []
    for word in words:
        current = cues[-1] if cues else None
        text = " ".join(w["text"] for w in current) if current else ""
        if (current is None or len(text) + 1 + len(word["text"]) > 2 * line
                or final(word["start"]) - final(current[-1]["end"]) > 0.8
                or final(word["end"]) - final(current[0]["start"]) > max_seconds
                or re.search(r"[.!?…]$", current[-1]["text"])
                or (re.search(r"[,;:]$", current[-1]["text"]) and len(text) > line * 0.8)):
            cues.append([word])
        else:
            current.append(word)
    out = []
    for n, cue in enumerate(cues, 1):
        start, end = final(cue[0]["start"]), final(cue[-1]["end"]) + 0.25
        if n < len(cues):
            end = min(end, final(cues[n][0]["start"]) - 0.02)
        text = " ".join(w["text"] for w in cue)
        if len(text) > line:                         # two lines, split near the middle
            cut = min((i for i, ch in enumerate(text) if ch == " "), key=lambda i: abs(i - len(text) / 2))
            text = text[:cut] + "\n" + text[cut + 1:]
        out.append(f"{n}\n{_srt_time(start)} --> {_srt_time(max(end, start + 0.5))}\n{text}\n")
    return "\n".join(out)


def write(ctx: RunContext, timeline: Timeline, rows: list[dict[str, Any]]) -> None:
    title_file = ctx.materials_dir / "titulo.txt"
    title = title_file.read_text("utf-8").strip() if title_file.is_file() else ctx.slug
    extra: dict[str, Any] = {}
    script = ctx.materials_dir / "guion.txt"
    if script.is_file():
        try:
            extra = complete_json(ctx, stage=STAGE, section="planner", system=SYSTEM,
                                  user=f"IDIOMA DE LA DESCRIPCIÓN Y ETIQUETAS: {ctx.language}\n\n"
                                       + script.read_text("utf-8")[:12000], max_tokens=800)
        except Exception as error:  # the file is useful without them
            print(f"   youtube.txt sin descripción/etiquetas: {str(error)[:120]}")
    body = [str(extra["description"]).strip()] if extra.get("description") else []
    chapters = chapter_lines(timeline)
    if chapters:
        body += ["", *chapters]
    used = len("\n".join(body)) + 4
    body += ["", compact_credits(rows, DESCRIPTION_LIMIT - used)]
    lines = ["TÍTULO", title, "", "DESCRIPCIÓN", *body, "", "ETIQUETAS"]
    tags = [str(t).strip() for t in extra.get("tags", []) if str(t).strip()]
    lines.append(", ".join(dict.fromkeys(tags))[:490])
    if extra.get("pinnedComment"):
        lines += ["", "COMENTARIO FIJADO (publícalo tú y fíjalo)", str(extra["pinnedComment"]).strip()]
    if extra.get("communityPost"):
        lines += ["", "POST DE COMUNIDAD (el día de la publicación)", str(extra["communityPost"]).strip()]
    words = ctx.work_dir / "words.json"
    if words.is_file():
        code = str(ctx.section("align").get("language", "es"))
        srt = ctx.out_dir / f"subtitulos.{code}.srt"
        srt.write_text(subtitles(timeline, json.loads(words.read_text("utf-8"))["words"]), encoding="utf-8")
        lines += ["", f"SUBTÍTULOS: sube {srt.name} en YouTube Studio → Subtítulos"]
    (ctx.out_dir / OUTPUT).write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
