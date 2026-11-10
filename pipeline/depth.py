"""Photos with depth (visual.depth: true): a parallax photo whose subject can be cut out gets that cutout, the same
size as the photo, and the render moves it in front of the photo at its own pace (remotion ParallaxPhoto), the
«2.5D» move of history documentaries. Off by default; a photo without a clear subject keeps the plain move.

    visual:
      depth: true
      depth_model: u2net      # rembg model: u2net (anything) | u2net_human_seg (people only)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from .context import RunContext

DIR = "depth"


def subject(image: np.ndarray, session: Any) -> np.ndarray | None:
    """The photo's main subject as a full-size RGBA (BGRA) image, or None when the mask is not one clear subject:
    too small, most of the frame, or touching three sides (a landscape, a crowd)."""

    import cv2
    from rembg import remove

    rgba = remove(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), session=session)
    alpha = rgba[..., 3]
    solid = alpha > 128
    coverage = float(solid.mean())
    if not 0.05 <= coverage <= 0.55:
        return None
    edges = [solid[0].mean(), solid[-1].mean(), solid[:, 0].mean(), solid[:, -1].mean()]
    if sum(e > 0.25 for e in edges) >= 3:
        return None
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)


def plate_of(cutout: str) -> str:
    """The photo with its subject painted out (what shows behind the subject when it moves), next to the cutout."""

    return cutout[: -len(".png")] + "-plate.jpg"


def files(media: dict[str, Any]) -> set[str]:
    """The extra files a shot's media needs in the render (its cutout and plate)."""

    cutout = media.get("cutout")
    return {cutout, plate_of(cutout)} if cutout else set()


def plate(image: np.ndarray, cut: np.ndarray) -> np.ndarray:
    """The photo with the subject's area (a little wider) filled from around it."""

    import cv2

    mask = (cut[..., 3] > 16).astype(np.uint8) * 255
    mask = cv2.dilate(mask, np.ones((25, 25), np.uint8))
    scale = min(1.0, 900 / max(image.shape[:2]))          # inpainting is slow on big photos: done small, then up
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    small_mask = cv2.resize(mask, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    filled = cv2.inpaint(small, small_mask, 9, cv2.INPAINT_TELEA)
    if scale < 1:
        filled = cv2.resize(filled, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_CUBIC)
    keep = (mask == 0)[..., None]
    return np.where(keep, image, filled)


def add(ctx: RunContext, timeline: Any) -> Any:
    """The timeline with `cutout` on every parallax photo that has a clear subject (cached by the photo's bytes)."""

    cfg = ctx.section("visual")
    if not cfg.get("depth"):
        return timeline
    photos = [s for s in timeline.shots if s.media and s.media.kind == "image" and s.media.layout == "parallax"]
    if not photos:
        return timeline
    try:
        import cv2
        from rembg import new_session
    except ImportError:
        print("   Fotos sin profundidad: instala 'rembg[cpu]'")
        return timeline
    session = new_session(str(cfg.get("depth_model", "u2net")))
    out_dir = ctx.work_dir / DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    found: dict[str, str] = {}
    for shot in photos:
        src = shot.media.src
        if src in found:
            continue
        path = ctx.work_dir / src
        try:
            data = path.read_bytes()
        except OSError:
            continue
        target = out_dir / f"{hashlib.sha1(data).hexdigest()[:16]}.png"
        none = target.with_suffix(".none")
        if not target.is_file() and not none.is_file():
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            cut = subject(image, session) if image is not None else None
            if cut is None:
                none.write_text("", encoding="utf-8")       # asked once: no clear subject
            else:
                cv2.imwrite(str(target.with_name(target.stem + "-plate.jpg")), plate(image, cut), [cv2.IMWRITE_JPEG_QUALITY, 92])
                cv2.imwrite(str(target), cut)
        if target.is_file():
            found[src] = str(target.relative_to(ctx.work_dir)).replace("\\", "/")
    shots = [s.model_copy(update={"media": s.media.model_copy(update={"cutout": found[s.media.src]})})
             if s.media and s.media.src in found and s.media.layout == "parallax" else s for s in timeline.shots]
    if found:
        print(f"   Fotos con profundidad: {len(found)} de {len({s.media.src for s in photos})}")
    return timeline.model_copy(update={"shots": shots})
