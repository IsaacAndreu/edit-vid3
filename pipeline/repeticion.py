"""Repetition risk before uploading: what YouTube's partner programme calls mass-produced, repetitive content (the
July 2025 update) is not an AI voice but videos that look like copies of each other. Three checks against the
channel's last videos (`repeticion.compare`, 10):

1. Title: the same skeleton with new nouns («Por qué X es el país más Y del mundo» again and again). The skeleton keeps
   the little words and punctuation and blanks the rest; two or more of the last titles with the same skeleton → ⚠️.
2. Thumbnail: the same layout every time (the same blocks of light and dark in the same places, whatever the photo).
   A coarse picture of the composition is compared with the channel's last thumbnails (YouTube's, for uploaded ones).
3. Visuals: the same footage under a fresh script — shots whose clip (the same source and moment, or the same
   picture) already appeared in an earlier video of the channel. More than `max_reused` (20 %) → ⚠️.

The studio shows it on each finished video; the autopilot's ideas get the recent titles so they do not repeat them.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

STOP = set("""el la los las un una unos unas de del al a en y e o u que por qué porque para con sin sobre como cómo cuando
cuándo donde dónde quien quién cual cuál cuánto cuanto es son fue era eran ser está están más menos muy tan tu tus su sus mi
mis lo le les se no sí ya hasta desde entre este esta estos estas ese esa eso esto nadie nunca todo todos the a an of to in
on and or why how what who when where is are was were your my his her their this that for with without from vs it nobody
never every all one""".split())


def skeleton(title: str) -> list[str]:
    """The title's shape: little words and punctuation kept, numbers as #, any other word as _."""

    out = []
    for token in re.findall(r"\w+|[¿?¡!:|]", title.lower()):
        out.append(token if token in STOP or not token.isalnum() else "#" if token.isdigit() else "_")
    return out


def title_check(title: str, earlier: list[str]) -> dict[str, Any]:
    shape = skeleton(title)
    same = [t for t in earlier if len(shape) >= 4 and SequenceMatcher(None, shape, skeleton(t)).ratio() >= 0.8]
    if len(same) >= 2:
        return {"name": "Título", "status": "warn", "text": f"mismo esqueleto que {len(same)} de tus últimos {len(earlier)} títulos: "
                + "; ".join(f"«{t}»" for t in same[:3]) + ". Cambia la estructura, no solo los nombres."}
    return {"name": "Título", "status": "ok", "text": f"estructura distinta de tus últimos {len(earlier)} títulos"
            + (f" (se parece a «{same[0]}»)" if same else "")}


def layout(image: Any) -> Any:
    """The composition of a thumbnail: a heavily blurred 16x9 grey picture, normalised (the photo itself does not matter)."""

    import cv2
    import numpy as np

    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    small = cv2.resize(cv2.GaussianBlur(cv2.resize(grey, (160, 90)), (0, 0), 6), (16, 9), interpolation=cv2.INTER_AREA)
    small = small.astype(np.float32)
    return (small - small.mean()) / (small.std() + 1e-6)


def same_layout(a: Any, b: Any) -> bool:
    import numpy as np

    return float(np.mean(a * b)) >= 0.8               # correlation of the two compositions


def thumbnail_check(mine: list[Any], earlier: list[Any]) -> dict[str, Any]:
    if not mine:
        return {"name": "Miniatura", "status": "skip", "text": "sin miniatura en out/<vídeo>/miniaturas/ para comparar"}
    if not earlier:
        return {"name": "Miniatura", "status": "ok", "text": "aún no hay miniaturas anteriores del canal para comparar"}
    best = min(sum(same_layout(m, e) for e in earlier) for m in mine)     # the most different of your options
    if best >= 3:
        return {"name": "Miniatura", "status": "warn", "text": f"misma composición que {best} de tus últimas {len(earlier)} "
                "miniaturas: cambia dónde van la cara, el objeto y el texto"}
    return {"name": "Miniatura", "status": "ok", "text": f"composición distinta de tus últimas {len(earlier)} miniaturas"
            + (f" (se parece a {best})" if best else "")}


def _hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def visuals_check(shots: list[dict[str, Any]], earlier: list[dict[str, Any]], max_reused: float = 0.2) -> dict[str, Any]:
    media = [s for s in shots if s.get("media") and not s.get("coldOpen")]
    if not media:
        return {"name": "Imágenes", "status": "ok", "text": "sin metraje de terceros (vídeo dibujado o de gráficos)"}
    reused = []
    for s in media:
        for e in earlier:
            same_clip = (s.get("candidateId") and s.get("candidateId") == e.get("candidateId")
                         and s.get("sourceStart") is not None and e.get("sourceStart") is not None
                         and abs(float(s["sourceStart"]) - float(e["sourceStart"])) < 4)
            same_picture = s.get("phash") and e.get("phash") and _hamming(s["phash"], e["phash"]) <= 6
            if same_clip or same_picture:
                reused.append(s)
                break
    share = len(reused) / len(media)
    if share > max_reused:
        return {"name": "Imágenes", "status": "warn", "text": f"{len(reused)} de {len(media)} planos ({share:.0%}) repiten clips de "
                "vídeos anteriores del canal: el mismo metraje con otro guion es lo que YouTube castiga"}
    return {"name": "Imágenes", "status": "ok", "text": f"{len(reused)} de {len(media)} planos ({share:.0%}) ya salieron en vídeos anteriores"}


# --- for one video of the studio --------------------------------------------------------------------------------

def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _images(paths: list[Path]) -> list[Any]:
    import cv2

    out = []
    for path in paths:
        image = cv2.imread(str(path))
        if image is not None:
            out.append(layout(image))
    return out


def _youtube_thumbnail(root: Path, url: str) -> Path | None:
    import hashlib

    import requests

    target = root / "cache" / "miniaturas" / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.jpg"
    if not target.is_file():
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
        except Exception:
            return None
    return target


def _proposed_title(root: Path, slug: str) -> str:
    """Before titulo.txt: the first title the package proposed in youtube.txt."""

    from .organizar import youtube_sections

    try:
        block = youtube_sections((root / "out" / slug / "youtube.txt").read_text("utf-8")).get("TÍTULO", "")
    except OSError:
        return ""
    first = next((line.strip() for line in block.splitlines() if line.strip()), "")
    return re.sub(r"^\s*(?:\d+[.)]|[-•*])\s*", "", first).strip("«»\" ")


def check(root: Path, slug: str) -> dict[str, Any]:
    from . import agenda
    from .context import RunContext

    videos = agenda.videos(root)
    me = next((v for v in videos if v["slug"] == slug), None)
    if me is None:
        raise FileNotFoundError(slug)
    try:
        cfg = RunContext.create("_repeticion", root=root).section("repeticion")
    except Exception:
        cfg = {}
    count = int(cfg.get("compare", 10))
    earlier = [v for v in videos if v["channel"] == me["channel"] and v["slug"] != slug and v["status"] in ("hecho", "subido")]
    earlier.sort(key=lambda v: str(v.get("published") or ""), reverse=True)
    earlier = earlier[:count]
    title = me.get("title") or _proposed_title(root, slug)
    checks = [title_check(title, [v["title"] for v in earlier if v.get("title")]) if title else
              {"name": "Título", "status": "skip", "text": "sin título todavía"}]

    def thumbs(s: str) -> list[Path]:
        folder = root / "out" / s
        return sorted([*folder.glob("miniaturas/*.jpg"), *folder.glob("miniaturas/*.png"), *folder.glob("miniatura*.jpg"),
                       *folder.glob("miniatura*.png")])

    stats = (_read(root / "out" / "_estadisticas.json") or {}).get("videos", {})
    previous = []
    for v in earlier:
        vid = agenda._video_id(v.get("url") or "")
        uploaded = (stats.get(vid) or {}).get("thumbnail") if vid else None
        path = _youtube_thumbnail(root, uploaded) if uploaded else None
        previous += [path] if path else thumbs(v["slug"])[:1]
    checks.append(thumbnail_check(_images(thumbs(slug)), _images(previous)))
    manifest = _read(root / "out" / slug / "manifest.json") or {}
    before = [s for v in earlier for s in (_read(root / "out" / v["slug"] / "manifest.json") or {}).get("shots", [])]
    checks.append(visuals_check(manifest.get("shots", []), before, float(cfg.get("max_reused", 0.2))))
    warns = sum(c["status"] == "warn" for c in checks)
    return {"slug": slug, "checks": checks, "risk": "alto" if warns >= 2 else "medio" if warns else "bajo",
            "compared": len(earlier)}


def recent_titles(root: Path, channel: str, count: int = 10) -> list[str]:
    from . import agenda

    videos = [v for v in agenda.videos(root) if v["channel"] == channel and v.get("title")]
    videos.sort(key=lambda v: str(v.get("published") or ""), reverse=True)
    return [v["title"] for v in videos[:count]]
