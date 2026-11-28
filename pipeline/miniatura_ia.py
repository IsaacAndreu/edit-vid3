"""Thumbnails made by OpenAI's image model from REFERENCE thumbnails: the same visual formula (layout, where the person
and the text go, the lettering, the colour treatment), adapted to our video (its frames, its protagonist, its text).

    python main.py --miniatura-ia <vídeo> [--ref <enlace o imagen>]… [--texto «…»]

Where the references come from (up to `miniaturas.ia_refs`, 3), the first ones found:
- `--ref`: a YouTube link or id (its thumbnail is downloaded) or an image file;
- materiales/<vídeo>/referencias-miniatura/ (images) and materiales/<vídeo>/miniatura-ref.txt (links, one per line);
- referencias/miniaturas/<canal>/ (the channel's model thumbnails).
Our side: out/<vídeo>/fotogramas/ (the stills ranked by how they read small, fotograma-1 first) and the protagonist's
cutout; without them, a frame of the finished video. The text on each thumbnail is one of the package's thumbnail
texts (youtube.txt), or `--texto`.

`miniaturas.ia: true` makes them by itself at the end of every video (package stage), never failing the video. Off by
default: each one is a paid image (`ia_quality: medium`, about 0.05-0.10 $), recorded in the API spend.
Result: out/<vídeo>/miniaturas-ia/miniatura-ia-N.jpg (1280x720, what YouTube takes), shown in the studio.
"""

from __future__ import annotations

import base64
import re
import subprocess
from pathlib import Path
from typing import Any

from .context import RunContext
from .costs import record_cost

STAGE = "package"
DIR = "miniaturas-ia"
IMAGES = (".jpg", ".jpeg", ".png", ".webp")
YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$")

PROMPT = """Design a YouTube thumbnail (16:9) for a new video.

The first {refs} image(s) are REFERENCE thumbnails that work very well. Copy their visual formula: composition and
framing, where the person and the text sit and how big they are, the lettering (weight, outline, shadow, colours), the
colour grading and contrast, and any graphic devices (arrows, circles, glow, split screen). Do NOT copy their people,
their words, their logos or their channel branding.

The next {ours} image(s) come from OUR video, «{title}». The person, the place and the action in the thumbnail must
come from them: keep the person exactly as they look in these images (face, hair, outfit), never another person.

The only words written on the thumbnail, exactly as given, in {language}: «{text}». Nothing else written: no logos,
no watermarks, no extra captions. It must read at a glance at small size on a phone.{extra}"""


def video_id(text: str) -> str | None:
    match = YOUTUBE_ID.search(str(text or "").strip())
    return (match.group(1) or match.group(2)) if match else None


def _images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGES) if folder.is_dir() else []


def youtube_thumbnail(ctx: RunContext, vid: str) -> Path | None:
    """The video's largest thumbnail (maxres, else hq), cached in cache/miniaturas/."""

    import requests

    target = ctx.cache_dir / "miniaturas" / f"{vid}.jpg"
    if target.is_file():
        return target
    for name in ("maxresdefault", "hqdefault"):
        try:
            response = requests.get(f"https://i.ytimg.com/vi/{vid}/{name}.jpg", timeout=20)
        except Exception:
            continue
        # a missing maxres comes back as a 120x90 grey placeholder of ~1 KB
        if response.status_code == 200 and len(response.content) > 5000:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
            return target
    return None


def references(ctx: RunContext, given: list[str] | None = None) -> list[Path]:
    """The reference thumbnails, in order of preference, at most `miniaturas.ia_refs`."""

    most = int(ctx.section("miniaturas").get("ia_refs", 3))
    links: list[str] = list(given or [])
    listed = ctx.materials_dir / "miniatura-ref.txt"
    if listed.is_file():
        links += [line.strip() for line in listed.read_text("utf-8").splitlines() if line.strip() and not line.startswith("#")]
    found: list[Path] = []
    for item in links:
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = ctx.root / path
        if path.is_file() and path.suffix.lower() in IMAGES:
            found.append(path)
        elif vid := video_id(item):
            if got := youtube_thumbnail(ctx, vid):
                found.append(got)
            else:
                print(f"   Miniatura de referencia de {vid} no disponible")
    found += _images(ctx.materials_dir / "referencias-miniatura")
    if ctx.channel:
        found += _images(ctx.root / "referencias" / "miniaturas" / ctx.channel)
    return list(dict.fromkeys(found))[:most]


def our_images(ctx: RunContext) -> list[Path]:
    """Our video's best stills and the protagonist's cutout (at most `miniaturas.ia_ours`, 3)."""

    most = int(ctx.section("miniaturas").get("ia_ours", 3))
    stills = ctx.out_dir / "fotogramas"
    ours = [p for p in _images(stills) if p.stem.startswith("fotograma")][: max(1, most - 1)]
    ours += [p for p in _images(stills) if p.stem == "recorte"]
    if not ours:
        frame = ctx.work_dir / "thumbs" / "ia-fotograma.jpg"
        final = ctx.out_dir / "video-final.mp4"
        if final.is_file():
            frame.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "20", "-i", str(final), "-frames:v", "1",
                            "-vf", "scale=1536:-2", "-q:v", "3", str(frame)], capture_output=True)
        ours = [frame] if frame.is_file() else []
    return ours[:most]


def texts(ctx: RunContext, given: str = "") -> list[str]:
    if given.strip():
        return [given.strip()]
    from .package import ask_titles

    got = [str(t).strip() for t in (ask_titles(ctx).get("thumbTexts") or []) if str(t).strip()]
    if not got:
        from .align import read_title

        got = [read_title(ctx)]
    return list(dict.fromkeys(got))


def prompt(ctx: RunContext, title: str, text: str, refs: int, ours: int) -> str:
    extra = str(ctx.section("miniaturas").get("ia_prompt") or "").strip()
    code = str(ctx.section("align").get("language", "es"))
    names = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French", "it": "Italian", "de": "German"}
    return PROMPT.format(refs=refs, ours=ours, title=title, text=text, language=names.get(code, ctx.language),
                         extra=f"\n\n{extra}" if extra else "")


def cost(ctx: RunContext, usage: Any) -> float:
    cfg = ctx.section("miniaturas")
    prices = {"text_input": 5.0, "image_input": 10.0, "image_output": 40.0,
              **(ctx.section("fallback").get("image_usd_per_mtok") or {})}
    if usage is None:
        return float(cfg.get("ia_usd_estimate", 0.08))
    details = getattr(usage, "input_tokens_details", None)
    image_in = int(getattr(details, "image_tokens", 0) or 0)
    text_in = int(getattr(details, "text_tokens", 0) or 0) or max(0, int(getattr(usage, "input_tokens", 0) or 0) - image_in)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    return (text_in * float(prices["text_input"]) + image_in * float(prices["image_input"])
            + out * float(prices["image_output"])) / 1e6


def generate(ctx: RunContext, images: list[Path], text_prompt: str, target: Path, client: Any = None) -> float:
    """One edited image from `images` and the prompt, saved as a 1280x720 JPEG at `target`. Returns what it cost."""

    import cv2
    import numpy as np

    cfg = ctx.section("miniaturas")
    model = str(cfg.get("ia_model") or ctx.section("fallback").get("image_model", "gpt-image-2"))
    if client is None:
        from openai import OpenAI

        key = ctx.env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("falta OPENAI_API_KEY en .env")
        client = OpenAI(api_key=key, timeout=300, max_retries=1)
    from .budget import before_paid_call

    before_paid_call(ctx)
    files = [open(p, "rb") for p in images]
    try:
        response = client.images.edit(model=model, image=files, prompt=text_prompt, size="1536x1024",
                                      quality=str(cfg.get("ia_quality", "medium")), n=1)
    finally:
        for f in files:
            f.close()
    raw = base64.b64decode(response.data[0].b64_json)
    picture = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if picture is None:
        raise RuntimeError("la imagen devuelta no se pudo leer")
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), cv2.resize(picture, (1280, 720), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 90])
    usd = cost(ctx, getattr(response, "usage", None))
    record_cost(ctx, stage=STAGE, provider="openai", operation=f"{model} miniatura", usd=usd,
                details={"refs": len(images), "file": target.name})
    return usd


def run(ctx: RunContext, refs: list[str] | None = None, text: str = "", count: int | None = None,
        client: Any = None) -> list[Path]:
    """The thumbnails, one per thumbnail text (at most `miniaturas.ia_count`, 2). Raises when there is nothing to
    copy or nothing of ours to show."""

    from .align import read_title

    found = references(ctx, refs)
    if not found:
        raise FileNotFoundError(
            "No hay miniaturas de referencia: pasa --ref <enlace de YouTube o imagen>, o guárdalas en "
            f"materiales/…/{ctx.slug}/referencias-miniatura/ o en referencias/miniaturas/{ctx.channel or '<canal>'}/")
    ours = our_images(ctx)
    if not ours:
        raise FileNotFoundError(f"No hay fotogramas del vídeo: falta out/{ctx.slug}/fotogramas/ o el vídeo final")
    title = read_title(ctx)
    wanted = int(count if count is not None else ctx.section("miniaturas").get("ia_count", 2))
    lines = texts(ctx, text)
    lines = (lines * wanted)[:wanted] if lines else []
    out: list[Path] = []
    spent = 0.0
    for n, line in enumerate(lines, 1):
        target = ctx.out_dir / DIR / f"miniatura-ia-{n}.jpg"
        try:
            spent += generate(ctx, [*found, *ours], prompt(ctx, title, line, len(found), len(ours)), target, client)
            out.append(target)
            print(f"   Miniatura IA {n}: «{line}» → out/{ctx.slug}/{DIR}/{target.name}")
        except Exception as error:          # one refused or failed: the others still come
            print(f"   Miniatura IA {n} no disponible: {type(error).__name__}: {str(error)[:200]}")
    print(f"   Miniaturas IA: {len(out)} de {len(lines)} · {len(found)} referencias · {len(ours)} imágenes del vídeo"
          f" · {spent:.2f} $")
    return out
