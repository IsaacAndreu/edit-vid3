"""Cheap frame checks: blackness, freezes, on-screen text, talking heads, sharpness, motion, pHash."""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np


YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)


def luma(frame: np.ndarray) -> float:
    return float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())


def detail(frame: np.ndarray) -> float:
    """Grey-level standard deviation: ~0 for flat/blank frames."""

    return float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).std())


def sharpness(frame: np.ndarray) -> float:
    """0-1: Laplacian variance at 360p height (≥ 500 counts as fully sharp)."""

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if gray.shape[0] != 360:
        gray = cv2.resize(gray, (round(gray.shape[1] * 360 / gray.shape[0]), 360))
    return float(min(1.0, cv2.Laplacian(gray, cv2.CV_64F).var() / 500.0))


def difference(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute grey difference (0-255) at a small common size."""

    small = (64, 36)
    ga = cv2.cvtColor(cv2.resize(a, small, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(cv2.resize(b, small, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(ga - gb).mean())


def phash(frame: np.ndarray) -> str:
    gray = cv2.cvtColor(cv2.resize(frame, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    dct = cv2.dct(np.float32(gray))[:8, :8]
    bits = (dct > np.median(dct)).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


class Detectors:
    def __init__(self, *, cache_dir: Path, ocr_side: int = 480) -> None:
        self.cache_dir = cache_dir
        self.ocr_side = ocr_side
        self._ocr = None
        self._faces: dict[tuple[int, int], object] = {}
        self._lock = threading.Lock()

    def _face_model(self) -> Path:
        path = self.cache_dir / "models" / "face_detection_yunet_2023mar.onnx"
        if not path.is_file() or path.stat().st_size < 10_000:  # a Git LFS pointer is ~400 bytes
            import requests

            path.parent.mkdir(parents=True, exist_ok=True)
            response = requests.get(YUNET_URL, timeout=60)
            response.raise_for_status()
            path.write_bytes(response.content)
        return path

    def text_area(self, frame: np.ndarray) -> float:
        """Fraction of the frame covered by detected text boxes."""

        with self._lock:
            if self._ocr is None:
                from rapidocr_onnxruntime import RapidOCR

                self._ocr = RapidOCR(det_limit_side_len=self.ocr_side, det_limit_type="max")
            boxes, _ = self._ocr(frame, use_det=True, use_cls=False, use_rec=False)
        if not boxes:
            return 0.0
        mask = np.zeros(frame.shape[:2], np.uint8)
        for box in boxes:
            points = np.array(box[0] if isinstance(box[0][0], (list, tuple, np.ndarray)) else box, np.int32).reshape(-1, 2)
            cv2.fillPoly(mask, [points], 1)
        return float(mask.mean())

    def face_area(self, frame: np.ndarray) -> tuple[float, float]:
        """(largest face area / frame area, its horizontal centre 0-1)."""

        h, w = frame.shape[:2]
        with self._lock:
            detector = self._faces.get((w, h))
            if detector is None:
                detector = cv2.FaceDetectorYN.create(str(self._face_model()), "", (w, h), 0.8)
                self._faces[(w, h)] = detector
            _, faces = detector.detect(frame)
        if faces is None or len(faces) == 0:
            return 0.0, 0.5
        best = max(faces, key=lambda f: f[2] * f[3])
        return float(best[2] * best[3] / (w * h)), float((best[0] + best[2] / 2) / w)
