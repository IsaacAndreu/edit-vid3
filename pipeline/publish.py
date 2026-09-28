"""out/<slug>/youtube.txt — everything to paste into YouTube Studio when uploading by hand.

Title (titulo.txt), a short description and tags written from the script (one cheap LLM call; the
file is still written without them if it fails), the chapter list with its timestamps (the first
at 0:00, as YouTube requires) and the source names (the description stays under YouTube's 5000
characters; the full list with links and times is creditos.txt). Nothing is uploaded.
"""

from __future__ import annotations

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
deporte, competiciones, en el idioma del guion y alguna en inglés"]}. No inventes datos que no
estén en el guion.
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


def write(ctx: RunContext, timeline: Timeline, rows: list[dict[str, Any]]) -> None:
    title_file = ctx.materials_dir / "titulo.txt"
    title = title_file.read_text("utf-8").strip() if title_file.is_file() else ctx.slug
    extra: dict[str, Any] = {}
    script = ctx.materials_dir / "guion.txt"
    if script.is_file():
        try:
            extra = complete_json(ctx, stage=STAGE, section="planner", system=SYSTEM,
                                  user=script.read_text("utf-8")[:12000], max_tokens=800)
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
    (ctx.out_dir / OUTPUT).write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
