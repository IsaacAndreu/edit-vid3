"""Final stage — out/<slug>/miniaturas/ (3 thumbnails), 3 title options in youtube.txt, and a message.

Titles and thumbnail lines are written from the script, taking the pattern (not the words) of the
titles that work best for the competition right now (out/_ideas/outliers.json, from `--ideas`).
Thumbnails are templates, not generated images of real people: the protagonist's cutout (people
stage) over a darkened frame of their peak moment (cold open / hook), a short huge line and an
accent colour that changes between the three. When the video is done you get the three
thumbnails and titles by email/Telegram (whatever is configured in .env).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import cv2

from . import notify
from .context import RunContext
from .llm import complete_json
from .render import Renderer
from .schemas import Timeline

STAGE = "package"
THUMB_DIR = "miniaturas"
ACCENTS = ["#ffd400", "#ff3b30", "#22d3ee"]

SYSTEM = """
Eres el responsable de títulos y miniaturas de un canal de YouTube en español de historias de
atletas. Con el guion del vídeo (y los títulos que mejor funcionan ahora en la competencia, solo
como patrón) devuelve SOLO JSON:
{"titles": ["3 títulos distintos en español, máx. 70 caracteres, con tensión y el nombre del atleta"],
 "thumbTexts": ["3 frases MUY cortas (2-5 palabras) para la miniatura, distintas del título, p. ej. 'ÚLTIMO DE 91' o 'NADIE LO VIO VENIR'"]}
No inventes datos: cifras y hechos solo si están en el guion. No copies títulos de la competencia.
""".strip()


def background_frames(ctx: RunContext, timeline: Timeline, count: int = 3) -> list[str]:
    """Middle frames of the cold-open clips, then of the hook's video shots, as 1280x720 JPEGs."""

    shots = [s for s in timeline.shots if s.coldOpen and s.media]
    shots += [s for s in timeline.shots if not s.coldOpen and s.media and s.media.kind == "video"
              and s.from_ < 40 * timeline.fps]
    out_dir = ctx.work_dir / "thumbs"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[str] = []
    for shot in shots:
        capture = cv2.VideoCapture(str(ctx.work_dir / shot.media.src))
        capture.set(cv2.CAP_PROP_POS_FRAMES, (capture.get(cv2.CAP_PROP_FRAME_COUNT) or 2) // 2)
        ok, frame = capture.read()
        capture.release()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = max(1280 / w, 720 / h)
        frame = cv2.resize(frame, (round(w * scale), round(h * scale)))
        y, x = (frame.shape[0] - 720) // 2, (frame.shape[1] - 1280) // 2
        target = out_dir / f"bg-{len(frames) + 1}.jpg"
        cv2.imwrite(str(target), frame[y : y + 720, x : x + 1280], [cv2.IMWRITE_JPEG_QUALITY, 90])
        frames.append(str(target.relative_to(ctx.work_dir)).replace("\\", "/"))
        if len(frames) == count:
            break
    return frames


def write_titles(path: Path, titles: list[str]) -> None:
    """Replace the TÍTULO block of youtube.txt with the three options."""

    if not path.is_file() or not titles:
        return
    text = path.read_text("utf-8")
    block = "TÍTULO (elige uno)\n" + "\n".join(f"{n}. {t}" for n, t in enumerate(titles, 1)) + "\n"
    path.write_text(re.sub(r"^TÍTULO[^\n]*\n(?:.+\n)*?(?=\n)", block, text, count=1), encoding="utf-8")


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "timeline.json", ctx.work_dir / "people.json", ctx.materials_dir / "guion.txt"]


def run(ctx: RunContext) -> None:
    timeline = Timeline.model_validate(ctx.read_json("timeline.json"))
    title_file = ctx.materials_dir / "titulo.txt"
    title = title_file.read_text("utf-8").strip() if title_file.is_file() else ctx.slug
    patterns = []
    outliers = ctx.root / "out" / "_ideas" / "outliers.json"
    if outliers.is_file():
        patterns = [o["title"] for o in json.loads(outliers.read_text("utf-8"))[:12]]
    script = (ctx.materials_dir / "guion.txt").read_text("utf-8")[:12000]
    try:
        result: dict[str, Any] = complete_json(
            ctx, stage=STAGE, section="planner", system=SYSTEM, max_tokens=800,
            user=f"TÍTULO DE TRABAJO: {title}\n\nTÍTULOS QUE MEJOR FUNCIONAN EN LA COMPETENCIA:\n"
                 + ("\n".join(f"- {p}" for p in patterns) or "(sin datos)") + f"\n\nGUION:\n{script}")
    except Exception as error:
        print(f"   Sin títulos/textos del LLM: {str(error)[:120]}")
        result = {}
    titles = [str(t).strip() for t in result.get("titles", []) if str(t).strip()][:3] or [title]
    texts = [str(t).strip() for t in result.get("thumbTexts", []) if str(t).strip()][:3] or [title]
    while len(texts) < 3:
        texts.append(texts[-1])

    cutout = None
    people = ctx.work_dir / "people.json"
    if people.is_file():
        found = json.loads(people.read_text("utf-8")).get("people", [])
        cutout = found[0]["image"] if found else None
    backgrounds = background_frames(ctx, timeline)
    variants = [{"text": texts[i], "accent": ACCENTS[i], "flip": i == 1, "cutout": cutout,
                 "background": backgrounds[i % len(backgrounds)] if backgrounds else None} for i in range(3)]
    renderer = Renderer(ctx)
    frames_dir = renderer.dir / "thumbs"
    shutil.rmtree(frames_dir, ignore_errors=True)
    public = {v["background"] for v in variants if v["background"]} | ({cutout} if cutout else set())
    renderer.remotion("Thumbnails", {"variants": variants}, frames_dir,
                      ["--sequence", "--image-format=jpeg", "--jpeg-quality=92"], public)
    out_dir = ctx.out_dir / THUMB_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for n, frame in enumerate(sorted(frames_dir.iterdir(), key=lambda p: int(re.findall(r"\d+", p.stem)[-1])), 1):
        target = out_dir / f"miniatura-{n}.jpg"
        shutil.move(str(frame), target)
        thumbs.append(target)
    shutil.rmtree(frames_dir, ignore_errors=True)
    write_titles(ctx.out_dir / "youtube.txt", titles)
    print(f"   {len(thumbs)} miniaturas · títulos: " + " | ".join(titles))
    minutes = timeline.durationInFrames / timeline.fps / 60
    body = ("Títulos:\n" + "\n".join(f"{n}. {t}" for n, t in enumerate(titles, 1))
            + f"\n\nVídeo ({minutes:.1f} min): {ctx.out_dir / 'video-final.mp4'}"
            + f"\nDescripción, capítulos y etiquetas: {ctx.out_dir / 'youtube.txt'}")
    shorts = sorted((ctx.out_dir / "shorts").glob("short-*.mp4"))
    if shorts:
        body += f"\nShorts: {len(shorts)} en {ctx.out_dir / 'shorts'} (títulos en shorts.txt)"
    from .factcheck import summary

    if line := summary(ctx):
        body += "\n" + line
    notify.send(ctx, f"Vídeo listo: {titles[0]}", body, thumbs)


def validate(ctx: RunContext) -> bool:
    return all((ctx.out_dir / THUMB_DIR / f"miniatura-{n}.jpg").is_file() for n in (1, 2, 3))
