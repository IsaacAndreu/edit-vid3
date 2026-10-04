"""Footage that has nothing to do with the script, whatever the search said: cartoons and broken video.

- Cartoons / animation (a children's cartoon in a documentary about a gymnast): CLIP finds the frame closer to
  "a cartoon, an animation, a drawing" than to "real footage, a photograph" in at least 2 frames. Allowed when
  the shot's own words talk about animation.
- Broken video (grey squares, a mosaic of blocks: a damaged upload or a bad cut): CLIP finds a single frame
  closer to "corrupted video, glitch, compression blocks" than to a clear frame. The damage often lasts half a
  second, so a clip is looked at 4 times per second.
Verdicts are cached in work/<slug>/content.json (by file name, size and time).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from .context import RunContext

VERSION = 1
CARTOON = ["a cartoon", "an animated cartoon scene", "a drawing, illustration, animation"]
REAL = ["a photograph", "real video footage of people", "a sports broadcast, real camera footage"]
BROKEN = ["corrupted digital video with blocky glitch artifacts", "pixelated datamosh glitch, broken video frame",
          "grey squares, compression artifacts, video decoding error"]
CLEAR = ["a clear video frame", "a black and white film still of people", "a photograph"]
ABOUT_ANIMATION = re.compile(r"\b(dibujos?|animaci[oó]n|animad[oa]s?|caricaturas?|cartoons?|anime|ilustraci[oó]n)\b",
                             re.IGNORECASE)


class ContentCheck:
    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.cfg = ctx.section("fallback")
        self.path = ctx.work_dir / "content.json"
        try:
            self.cache: dict[str, str] = json.loads(self.path.read_text("utf-8")) if self.path.is_file() else {}
        except ValueError:
            self.cache = {}
        self._clip: Any = None
        self._vectors: dict[str, np.ndarray] = {}

    def _model(self) -> Any:
        if self._clip is None:
            from .analysis.clip import ClipScorer

            cfg = self.ctx.section("analysis")
            self._clip = ClipScorer(cache_dir=self.ctx.cache_dir, model=str(cfg.get("model", "ViT-B-32")),
                                    pretrained=str(cfg.get("pretrained", "laion2b_s34b_b79k")))
            for name, prompts in (("cartoon", CARTOON), ("real", REAL), ("broken", BROKEN), ("clear", CLEAR)):
                self._vectors[name] = self._clip.shot_vector(prompts)
        return self._clip

    @staticmethod
    def frames(path: Path, kind: str, per_second: float = 4.0) -> list[np.ndarray]:
        import cv2

        if kind == "image":
            image = cv2.imread(str(path))
            return [image] if image is not None else []
        capture = cv2.VideoCapture(str(path))
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, int(round(fps / per_second)))
        out = []
        for index in range(0, count, step):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if ok:
                out.append(cv2.resize(frame, (320, int(320 * frame.shape[0] / max(1, frame.shape[1])))))
        capture.release()
        return out

    def judge(self, frames: list[np.ndarray], allow_cartoon: bool = False) -> str | None:
        """Why these frames do not belong in a documentary (None when they do)."""

        if not frames:
            return None
        clip = self._model()
        vectors = clip.embed_images(frames)
        v = self._vectors
        broken = vectors @ v["broken"] - vectors @ v["clear"]
        if float(broken.max()) > float(self.cfg.get("broken_margin", 0.05)):
            return "vídeo dañado (píxeles rotos)"
        if not allow_cartoon:
            cartoon = vectors @ v["cartoon"] - vectors @ v["real"]
            hits = int((cartoon > float(self.cfg.get("cartoon_margin", 0.02))).sum())
            if hits >= min(2, len(frames)):
                return "es un dibujo animado"
        return None

    def verdict(self, path: Path, kind: str, text: str = "") -> str | None:
        if not self.cfg.get("content_check", True) or not path.is_file():
            return None
        allow = bool(ABOUT_ANIMATION.search(text or ""))
        stat = path.stat()
        key = f"{VERSION}|{path.name}|{stat.st_size}|{int(stat.st_mtime)}|{int(allow)}"
        if key not in self.cache:
            try:
                self.cache[key] = self.judge(self.frames(path, kind), allow) or ""
            except Exception as error:      # never costs a clip on its own
                print(f"   comprobación de contenido no disponible: {str(error)[:100]}")
                return None
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")
        return self.cache[key] or None
