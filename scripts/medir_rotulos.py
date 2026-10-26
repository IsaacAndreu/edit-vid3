"""How many fragments discarded for «texto en pantalla» only had their text in the bottom band (a TV news chyron),
so a crop would have saved them. Read-only: python scripts/medir_rotulos.py <slug> [banda=0.28]."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import file_start, read_frames  # noqa: E402
from pipeline.analysis.detectors import Detectors  # noqa: E402


def text_mask(det: Detectors, frame: np.ndarray) -> np.ndarray:
    import re

    with det._lock:
        if det._ocr is None:
            from pipeline.analysis.detectors import _make_ocr

            det._ocr = _make_ocr(det.ocr_side)
        results, _ = det._ocr(frame, use_det=True, use_cls=False, use_rec=True)
    mask = np.zeros(frame.shape[:2], np.uint8)
    for box, text, score in results or []:
        if float(score) >= 0.7 and len(re.findall(r"[^\W\d_]", str(text))) >= 3:
            cv2.fillPoly(mask, [np.array(box, np.int32).reshape(-1, 2)], 1)
    return mask


def main() -> None:
    slug = sys.argv[1]
    band = float(sys.argv[2]) if len(sys.argv) > 2 else 0.28
    det = Detectors(cache_dir=ROOT / "cache", ocr_side=480)
    total = saved = 0
    examples: list[str] = []
    for path in sorted((ROOT / "work" / slug / "scores").glob("*.json")):
        for option in json.loads(path.read_text("utf-8")).get("options", []):
            if not str(option.get("discarded") or "").startswith("texto en pantalla") or option.get("kind") != "video":
                continue
            window = ROOT / str(option.get("analysisPath") or "")
            if not window.is_file():
                continue
            middle = (option["start"] + option["end"]) / 2 - file_start(window)
            frames = read_frames(window, [middle])
            if not frames:
                continue
            total += 1
            mask = text_mask(det, frames[0][1])
            cut = int(mask.shape[0] * (1 - band))
            top = float(mask[:cut].mean())                 # text left after cropping the bottom band
            if top <= 0.02:                                # barely a corner logo
                saved += 1
                if len(examples) < 8:
                    examples.append(f"{path.stem} {option['candidateId']} {option['start']:.0f}s")
            if total % 50 == 0:
                print(f"   {total} mirados…", flush=True)
    print(f"\n{slug}: {total} fragmentos descartados por texto (con ventana guardada)")
    print(f"   con el texto solo en la franja de abajo ({band:.0%}): {saved} ({saved / max(1, total):.0%})")
    print("   ejemplos: " + "; ".join(examples))


if __name__ == "__main__":
    main()
