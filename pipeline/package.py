"""Final stage — out/<slug>/miniaturas/ (3 thumbnails), 3 title options in youtube.txt, and a message.

Titles and thumbnail lines are written from the script, taking the pattern (not the words) of the
titles that work best for the competition right now (out/_ideas/outliers.json, from `--ideas`).
Thumbnails are templates, not generated images of real people: the protagonist's cutout (people
stage) over a darkened frame of their peak moment (cold open / hook), a short huge line and an
accent colour that changes between the three. When the video is done you get the three
thumbnails and titles by email/Telegram (whatever is configured in .env).

`package.thumbnail_style: concept` (the business channel): like the top economy channels, each
thumbnail is ONE visual idea — a generated image (a building lit in the channel colour inside a white
city model, a chart line diving next to the product…) with a clean background, the key element in
the brand colour and 0-4 words on a label. No real faces, logos or text in the image itself.
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
from .costs import record_cost
from .llm import complete_json
from .render import Renderer
from .schemas import Timeline

STAGE = "package"
THUMB_DIR = "miniaturas"
ACCENTS = ["#ffd400", "#ff3b30", "#22d3ee"]

SYSTEM = """
Eres el responsable de títulos y miniaturas de un canal de YouTube documental (historias de atletas, de empresas…). Con el guion del vídeo (y los títulos que mejor funcionan ahora en la competencia, solo
como patrón) devuelve SOLO JSON:
{"titles": ["3 títulos distintos EN EL IDIOMA DEL GUION, máx. 70 caracteres, con tensión y el nombre del protagonista (atleta, empresa, marca…)"],
 "thumbTexts": ["3 frases MUY cortas (2-5 palabras) para la miniatura, en el idioma del guion, distintas del título, p. ej. 'ÚLTIMO DE 91' o 'NADIE LO VIO VENIR'"]}
No inventes datos: cifras y hechos solo si están en el guion. No copies títulos de la competencia.
""".strip()


CONCEPT_SYSTEM = """
Además, propón 3 miniaturas CONCEPTUALES distintas, como las de los canales de documentales de economía que más
funcionan: UNA sola idea visual que resuma el vídeo y dé curiosidad (un edificio o producto reconocible, una
gráfica que se hunde junto al objeto, una maqueta de ciudad con UN edificio destacado, una persona de espaldas
ante algo enorme…), fondo limpio y el elemento clave en el color del canal. Añade a la respuesta:
"concepts": [{"scene": "la imagen EN INGLÉS, concreta y visual, 1-2 frases; sin texto, sin logotipos y sin caras
reconocibles de personas reales", "text": "0-4 palabras EN MAYÚSCULAS en el idioma del guion, o '' (a veces sin texto
es mejor)", "side": "left" o "right" (el lado que la imagen deja libre para el texto)}]
""".strip()

COLOR_NAMES = [(15, "red"), (40, "orange"), (65, "yellow"), (165, "lime green"), (195, "cyan"), (255, "blue"),
               (290, "purple"), (335, "magenta"), (360, "red")]


def color_name(hex_color: str) -> str:
    """'#19fe5b' → 'lime green' (image models follow colour words better than hex codes)."""

    import colorsys

    value = hex_color.lstrip("#")
    if len(value) != 6:
        return "bright yellow"
    r, g, b = (int(value[i: i + 2], 16) / 255 for i in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    if saturation < 0.25:
        return "white" if lightness > 0.6 else "black"
    degrees = hue * 360
    return next(name for limit, name in COLOR_NAMES if degrees <= limit)


def concept_image(ctx: RunContext, scene: str, accent: str, side: str, n: int) -> str | None:
    """A 16:9 concept picture for thumbnail n (work/<slug>/thumbs/concept-n.png), cached by prompt."""

    import base64

    from .sourcing.common import key

    cfg = ctx.section("package")
    model = str(cfg.get("concept_model") or ctx.section("fallback").get("image_model", "gpt-image-2"))
    quality = str(cfg.get("concept_quality", "medium"))
    prompt = (
        "YouTube thumbnail concept image, 16:9 landscape. " + scene.strip() + " "
        f"One single clear subject, clean uncluttered background, crisp 3D render / studio photo look, strong contrast. "
        f"The key element is {color_name(accent)} ({accent}) and it is the ONLY saturated colour; everything else is "
        f"neutral white, grey or black. Leave the {'left' if side == 'left' else 'right'} third empty for a text label. "
        "No text, no letters, no numbers, no logos, no watermarks, no recognizable real people's faces."
    )
    cached = ctx.cache_dir / "generated" / f"thumb-{key(model, prompt, quality)}.png"
    if not cached.is_file():
        from openai import OpenAI

        client = OpenAI(api_key=ctx.env("OPENAI_API_KEY"))
        response = client.images.generate(model=model, prompt=prompt, size="1536x1024", quality=quality, n=1)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(base64.b64decode(response.data[0].b64_json))
        usage = getattr(response, "usage", None)
        prices = ctx.section("fallback").get("image_usd_per_mtok", {"text_input": 5.0, "image_output": 40.0})
        usd = ((getattr(usage, "input_tokens", 0) * float(prices.get("text_input", 5.0))
                + getattr(usage, "output_tokens", 0) * float(prices.get("image_output", 40.0))) / 1e6
               if usage is not None else float(cfg.get("concept_usd_estimate", 0.06)))
        record_cost(ctx, stage=STAGE, provider="openai", operation=model, usd=usd, details={"thumbnail": n})
    target = ctx.work_dir / "thumbs" / f"concept-{n}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, target)
    return str(target.relative_to(ctx.work_dir)).replace("\\", "/")


def background_frames(ctx: RunContext, timeline: Timeline, count: int = 3, out_dir: Path | None = None,
                      size: tuple[int, int] = (1280, 720), spread: bool = False) -> list[str]:
    """Middle frames of the cold-open clips, then of the hook's video shots, as 1280x720 JPEGs. With `spread`, after
    the cold open the video shots of the whole video, evenly (stills for your own thumbnail)."""

    shots = [s for s in timeline.shots if s.coldOpen and s.media]
    if spread:
        rest = [s for s in timeline.shots if not s.coldOpen and s.media and s.media.kind == "video"]
        step = max(1, len(rest) // max(1, count))
        shots += rest[::step]
    else:
        shots += [s for s in timeline.shots if not s.coldOpen and s.media and s.media.kind == "video"
                  and s.from_ < 40 * timeline.fps]
    width, height = size
    out_dir = out_dir or ctx.work_dir / "thumbs"
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
        scale = max(width / w, height / h)
        frame = cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_CUBIC)
        y, x = (frame.shape[0] - height) // 2, (frame.shape[1] - width) // 2
        target = out_dir / f"{'fotograma' if spread else 'bg'}-{len(frames) + 1}.jpg"
        cv2.imwrite(str(target), frame[y : y + height, x : x + width], [cv2.IMWRITE_JPEG_QUALITY, 92])
        frames.append(str(target.relative_to(ctx.work_dir if not spread else out_dir.parent)).replace("\\", "/"))
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
    from .align import read_title

    title = read_title(ctx)
    patterns = []
    from .ideas import outliers_path

    outliers = outliers_path(ctx)
    if outliers:
        patterns = [o["title"] for o in json.loads(outliers.read_text("utf-8"))[:12]]
    hint = " ".join(str(h).strip() for h in (ctx.format.get("titulos"), ctx.section("package").get("hint")) if h)
    script = (ctx.materials_dir / "guion.txt").read_text("utf-8")[:12000]
    concept = str(ctx.section("package").get("thumbnail_style", "frame")) == "concept"
    try:
        result: dict[str, Any] = complete_json(
            ctx, stage=STAGE, section="planner", max_tokens=1600 if concept else 800,
            system=SYSTEM + (f"\n{CONCEPT_SYSTEM}" if concept else "") + (f"\nEN ESTE CANAL: {hint}" if hint else "") + f"\nIDIOMA OBLIGATORIO de titles y thumbTexts: {ctx.language}, aunque los ejemplos estén en otro idioma.",
            user=f"IDIOMA DE LOS TÍTULOS Y TEXTOS: {ctx.language}\nTÍTULO DE TRABAJO: {title}\n\nTÍTULOS QUE MEJOR FUNCIONAN EN LA COMPETENCIA:\n"
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
    if not ctx.section("miniaturas").get("enabled", False):    # you make the thumbnails yourself
        write_titles(ctx.out_dir / "youtube.txt", titles)
        stills = material_for_thumbnail(ctx, timeline, texts, cutout)
        print(f"   Miniaturas: las haces tú · {stills} fotogramas en out/{ctx.slug}/{STILLS_DIR}/ y 3 textos en youtube.txt")
        _finish(ctx, timeline, titles, [], preview=_preview_frame(ctx))
        return
    backgrounds = background_frames(ctx, timeline)
    brand = ctx.section("brand")
    accents = [str(brand.get("accent") or ACCENTS[0]), str(brand.get("accent2") or ACCENTS[1]), ACCENTS[2]] if brand else ACCENTS
    variants = [{"text": texts[i], "accent": accents[i], "flip": i == 1, "cutout": cutout,
                 "background": backgrounds[i % len(backgrounds)] if backgrounds else None} for i in range(3)]
    if concept:
        ideas = [c for c in result.get("concepts", []) if isinstance(c, dict) and str(c.get("scene") or "").strip()][:3]
        for i, idea in enumerate(ideas):
            side = "left" if str(idea.get("side")) == "left" else "right"
            try:
                image = concept_image(ctx, str(idea["scene"]), accents[0], side, i + 1)
            except Exception as error:  # no key or the model refused: that one stays a frame thumbnail
                print(f"   Miniatura conceptual {i + 1} no disponible: {str(error)[:120]}")
                continue
            words = " ".join(str(idea.get("text") or "").split()[:4])
            variants[i] = {"text": words, "accent": accents[0], "image": image, "side": side}
    renderer = Renderer(ctx)
    frames_dir = renderer.sequence_dir("thumbs")       # never a path with a dot (Remotion)
    shutil.rmtree(frames_dir, ignore_errors=True)
    public = ({v["background"] for v in variants if v.get("background")} | {v["image"] for v in variants if v.get("image")}
              | ({cutout} if cutout and any(v.get("cutout") for v in variants) else set()))
    renderer.remotion("Thumbnails", {"variants": variants, "brand": brand}, frames_dir,
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
    _finish(ctx, timeline, titles, thumbs)


STILLS_DIR = "fotogramas"


def material_for_thumbnail(ctx: RunContext, timeline: Timeline, texts: list[str], cutout: str | None) -> int:
    """For the thumbnail you make yourself: 8 clean 1920x1080 stills of the video (cold open first, then spread over
    the whole video), the protagonist's cutout (transparent PNG) and 3 short texts in youtube.txt. How many stills."""

    out_dir = ctx.out_dir / STILLS_DIR
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        stills = background_frames(ctx, timeline, int(ctx.section("miniaturas").get("stills", 8)), out_dir,
                                   (1920, 1080), spread=True)
    except Exception as error:               # stills are a help, never a reason to fail the video
        print(f"   Fotogramas para la miniatura no disponibles: {str(error)[:120]}")
        stills = []
    if cutout and (ctx.work_dir / cutout).is_file():
        shutil.copy2(ctx.work_dir / cutout, out_dir / ("recorte" + Path(cutout).suffix))
    youtube = ctx.out_dir / "youtube.txt"
    if youtube.is_file() and texts:
        text = youtube.read_text("utf-8")
        block = "IDEAS PARA LA MINIATURA (texto corto)\n" + "\n".join(f"- {t}" for t in dict.fromkeys(texts)) + "\n"
        text = re.sub(r"\nIDEAS PARA LA MINIATURA[^\n]*\n(?:- .*\n)*", "\n", text)
        youtube.write_text(text.rstrip("\n") + "\n\n" + block, encoding="utf-8")
    return len(stills)


def _preview_frame(ctx: RunContext) -> Path | None:
    """A frame of the final video for the phone notice when there are no thumbnails (not a thumbnail)."""

    import subprocess

    final = ctx.out_dir / "video-final.mp4"
    target = ctx.work_dir / "thumbs" / "aviso.jpg"
    if not final.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "20", "-i", str(final), "-frames:v", "1",
                           "-vf", "scale=1280:-2", "-q:v", "3", str(target)], capture_output=True)
    return target if done.returncode == 0 and target.is_file() else None


def _finish(ctx: RunContext, timeline: Timeline, titles: list[str], thumbs: list[Path], preview: Path | None = None) -> None:
    from .report import write as report

    card = report(ctx)                                  # also out/<slug>/resumen.md
    shorts = sorted((ctx.out_dir / "shorts").glob("short-*.mp4"))
    extra = f"\n• Shorts: {len(shorts)} (títulos en shorts.txt)" if shorts else ""
    verdict = card.splitlines()[0] if card else ""            # «✅ Listo para subir» / «⚠️ Revisar: …»
    notify.video_ready(ctx, title=titles[0], duration=timeline.durationInFrames / timeline.fps, verdict=verdict,
                       details=("\n".join(card.splitlines()[1:]) + extra).strip(),
                       thumbnails=thumbs or ([preview] if preview else []), titles=titles)


def outputs(ctx: RunContext) -> list[Path]:
    if not ctx.section("miniaturas").get("enabled", False):
        return [ctx.out_dir / "youtube.txt"]
    return [ctx.out_dir / THUMB_DIR / "miniatura-1.jpg"]


def validate(ctx: RunContext) -> bool:
    if not ctx.section("miniaturas").get("enabled", False):
        return (ctx.out_dir / "youtube.txt").is_file()
    return all((ctx.out_dir / THUMB_DIR / f"miniatura-{n}.jpg").is_file() for n in (1, 2, 3))
