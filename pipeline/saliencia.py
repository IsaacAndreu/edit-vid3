"""How well a picture works as a thumbnail when it is small (the phone feed): one score 0-100 and why.

Free and local (OpenCV + numpy, no model, no API). Four things, measured at feed size (320x180):
- focus (35): one clear spot draws the eye. Spectral-residual saliency (Hou & Zhang, 2007): the share of the
  saliency in the brightest tenth of the picture;
- contrast (25): spread of the brightness (a grey picture disappears in the feed);
- colour (20): colourfulness (Hasler & Süsstrunk, 2003);
- clean (20): not too many edges (a busy picture reads as noise when small).
A very dark or very washed-out picture loses up to 15 more.

Used by pipeline/package.py: the stills for your own thumbnail are renamed so fotograma-1 is the best one, and the
three automatic thumbnails are listed best first (puntuacion.md next to them, and in that order in the notice).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

FEED = (320, 180)
WEIGHTS = {"focus": 35, "contrast": 25, "colour": 20, "clean": 20}


def saliency(gray: np.ndarray) -> np.ndarray:
    """Spectral-residual saliency map of a grey picture, 0-1, at 64x64 (resized back by the caller if needed)."""

    small = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
    spectrum = np.fft.fft2(small)
    log_amplitude = np.log(np.abs(spectrum) + 1e-9)
    residual = log_amplitude - cv2.blur(log_amplitude, (3, 3))
    picture = np.abs(np.fft.ifft2(np.exp(residual + 1j * np.angle(spectrum)))) ** 2
    picture = cv2.GaussianBlur(picture.astype(np.float32), (0, 0), 2.5)
    span = picture.max() - picture.min()
    return (picture - picture.min()) / span if span > 0 else np.zeros_like(picture)


def _clip(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def measure(image: np.ndarray) -> dict[str, Any]:
    """Score of a BGR picture: {"score": 0-100, "focus"/"contrast"/"colour"/"clean": 0-1, "brightness": 0-1}."""

    small = cv2.resize(image, FEED, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    sal = saliency(gray).ravel()
    total = sal.sum()
    top = np.sort(sal)[-len(sal) // 10:].sum() / total if total > 0 else 0.1
    focus = _clip((top - 0.28) / 0.35)                   # 0.28 = spread everywhere · 0.63 = one clear spot
    luminance = gray.astype(np.float32) / 255
    contrast = _clip(float(luminance.std()) / 0.25)
    b, g, r = [c.astype(np.float32) for c in cv2.split(small)]
    rg, yb = r - g, 0.5 * (r + g) - b
    colourfulness = float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))
    colour = _clip(colourfulness / 80)                   # ≈ 80: «quite colourful» on Hasler's scale
    edges = float((cv2.Canny(gray, 80, 200) > 0).mean())
    clean = _clip(1 - (edges - 0.03) / 0.08)            # under 3 % edges: clean · over 11 %: noise
    brightness = float(luminance.mean())
    penalty = 15 * (_clip((0.22 - brightness) / 0.12) + _clip((brightness - 0.85) / 0.1))
    parts = {"focus": focus, "contrast": contrast, "colour": colour, "clean": clean}
    score = sum(WEIGHTS[k] * v for k, v in parts.items()) - penalty
    return {"score": round(max(0.0, score)), **{k: round(v, 2) for k, v in parts.items()},
            "brightness": round(brightness, 2)}


def score_file(path: Path) -> dict[str, Any] | None:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    return None if image is None else {"file": path.name, **measure(image)}


GOOD = {"focus": "foco claro", "contrast": "buen contraste", "colour": "color vivo", "clean": "limpia"}
WEAK = {"focus": "sin foco claro", "contrast": "poco contraste", "colour": "poco color", "clean": "recargada"}


def why(result: dict[str, Any]) -> str:
    """«foco claro, limpia, poco contraste»: the strongest and the weakest of the four."""

    parts = sorted(GOOD, key=lambda k: result[k])
    good = [GOOD[k] for k in reversed(parts) if result[k] >= 0.7][:2]
    weak = [WEAK[k] for k in parts if result[k] < 0.4][:2]
    text = ", ".join(good + weak)
    if result["brightness"] < 0.22:
        text += (", " if text else "") + "muy oscura"
    elif result["brightness"] > 0.85:
        text += (", " if text else "") + "muy clara"
    return text or "correcta"


def rank(paths: list[Path]) -> list[dict[str, Any]]:
    """The pictures that could be read, best first."""

    found = [r for r in (score_file(p) for p in paths) if r is not None]
    return sorted(found, key=lambda r: -r["score"])


def markdown(title: str, ranked: list[dict[str, Any]]) -> str:
    lines = [f"# {title}", "", "Puntuación 0-100 de cómo se ve en pequeño (el móvil): foco claro, contraste, color y "
                              "pocos detalles. Es una ayuda: la última palabra es tuya.", "",
             "| | Archivo | Puntos | Por qué |", "|---|---|---|---|"]
    lines += [f"| {n} | {r['file']} | {r['score']} | {why(r)} |" for n, r in enumerate(ranked, 1)]
    return "\n".join(lines) + "\n"


def order_stills(folder: Path, prefix: str = "fotograma") -> list[dict[str, Any]]:
    """Rename folder/<prefix>-N.jpg so <prefix>-1 is the best one; writes folder/puntuacion.md. The ranking."""

    stills = sorted(folder.glob(f"{prefix}-*.jpg"), key=lambda p: int(p.stem.rsplit("-", 1)[-1]) if p.stem.rsplit("-", 1)[-1].isdigit() else 0)
    ranked = rank(stills)
    if not ranked:
        return []
    temporary = []
    for n, r in enumerate(ranked, 1):
        moved = folder / f".orden-{n}.jpg"
        (folder / r["file"]).replace(moved)
        temporary.append((moved, folder / f"{prefix}-{n}.jpg", r))
    for moved, target, r in temporary:
        moved.replace(target)
        r["was"], r["file"] = r["file"], target.name
    (folder / "puntuacion.md").write_text(markdown("Fotogramas, del mejor al peor para la miniatura", ranked),
                                          encoding="utf-8")
    return ranked
