"""`## ` chapter lines written into a new video's script, when it has none.

With chapters in guion.txt the planner uses yours instead of guessing them while it cuts the video, the chapter cards
fall at the right sentence and you can see and change them before the video is made (studio → Guion). They are
never read aloud (tts.narration_text and a recorded voice simply skip them).

Only for a video that has not started (no stage done yet: its stages would otherwise all run again), and only once:
the original script is kept as guion.sin-capitulos.txt. `chapters.auto: false` in a channel turns it off.
"""

from __future__ import annotations

import re
from typing import Any

from .context import RunContext

STAGE = "capitulos"
BACKUP = "guion.sin-capitulos.txt"

SYSTEM = """
Eres editor de documentales de YouTube. Recibes los párrafos numerados del guion de un vídeo.
Divide el vídeo en 4-7 capítulos que sigan la historia (no el primer párrafo: el arranque va sin capítulo).
Devuelve SOLO un objeto JSON: {"chapters": [{"paragraph": 3, "title": "TÍTULO CORTO EN MAYÚSCULAS"}]}
- "paragraph": el número del párrafo con el que empieza el capítulo, en orden creciente, nunca el 0.
- "title": máx. 32 caracteres, en el idioma del guion, concreto y con gancho (p. ej. "LA CLÁUSULA DE PARIDAD").
""".strip()


def _paragraphs(script: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", script.strip()) if b.strip()]
    if len(blocks) < 4:                       # one paragraph per line
        blocks = [line.strip() for line in script.splitlines() if line.strip()]
    return blocks


def has_chapters(script: str) -> bool:
    return any(line.strip().startswith("## ") for line in script.splitlines())


def started(ctx: RunContext) -> bool:
    stages = ctx.work_dir / ".stages"
    return stages.is_dir() and any(stages.glob("*.json"))


def with_chapters(script: str, chapters: list[dict[str, Any]]) -> str:
    """The script with a `## TITLE` line before each chosen paragraph."""

    paragraphs = _paragraphs(script)
    at: dict[int, str] = {}
    for item in chapters:
        try:
            n, title = int(item["paragraph"]), " ".join(str(item["title"]).split()).upper()[:48]
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < n < len(paragraphs) and title and n not in at:
            at[n] = title
    if len(at) < 2:
        raise ValueError(f"solo {len(at)} capítulos válidos")
    out = []
    for n, paragraph in enumerate(paragraphs):
        if n in at:
            out.append(f"## {at[n]}")
        out.append(paragraph)
    return "\n\n".join(out) + "\n"


def ensure(ctx: RunContext) -> bool:
    """Write the chapters into guion.txt if it has none and the video has not started. True if it wrote them."""

    script_path = ctx.materials_dir / "guion.txt"
    if not script_path.is_file() or not ctx.section("chapters").get("auto", True) or started(ctx):
        return False
    script = script_path.read_text("utf-8")
    if has_chapters(script) or (ctx.materials_dir / BACKUP).is_file():
        return False
    paragraphs = _paragraphs(script)
    if len(paragraphs) < 5:
        return False
    listing = "\n".join(f"[{n}] {p[:400]}" for n, p in enumerate(paragraphs))
    try:
        from .llm import complete_json

        result = complete_json(ctx, stage=STAGE, section="planner", system=SYSTEM, user=listing, max_tokens=800)
        text = with_chapters(script, result.get("chapters") or [])
    except Exception as error:               # no chapters: the planner guesses them as before
        print(f"   Capítulos automáticos: no se pudieron poner ({type(error).__name__}: {str(error)[:150]})")
        return False
    (ctx.materials_dir / BACKUP).write_text(script, encoding="utf-8")
    script_path.write_text(text, encoding="utf-8")
    titles = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    print(f"   Capítulos puestos en el guion: {' | '.join(titles)} (el original queda en {BACKUP})")
    return True
