"""Is the athlete on screen the one the script names? Two careful checks before a clip reaches the video.

1. On-screen captions (the strong one). Sports broadcasts label athletes as "SURNAME" next to a country
   code ("JARMAN … 134GBR"). If, in at least 2 of 3 frames, a caption names someone next to a country
   code while the named athlete's surname appears nowhere, the clip shows somebody else.
2. Faces (only clear cases). With a good reference portrait (people.json, face ≥ 90 px), a clip is
   rejected only when at least 2 frames show a large frontal face and none of them looks like the
   person. Sports faces are often small, turned or strained mid-skill, so anything less is kept.

A rejected clip goes back to the fallback stage like a repeated one, which finds another.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import numpy as np

from .context import RunContext

IOC = ("USA CHN JPN RUS ROC GBR BRA ITA FRA GER NED BEL SUI ESP POR ROU UKR KOR PRK CAN AUS MEX ARG COL PHI TUR "
       "ISR HUN CZE SLO CRO SRB GRE CYP ARM AZE KAZ UZB BLR IRL NOR SWE FIN DEN AUT POL LTU LAT EST EGY RSA ALG TUN "
       "VIE TPE HKG SGP MAS THA IND IRI JOR CUB VEN CHI PER PAN GUA DOM PUR JAM NZL BUL SVK ISL LUX KOS GEO MGL "
       "AIN MDA MNE MKD BIH ALB QAT KSA UAE KUW").split()
CODE = re.compile(r"(?<![A-Z])(" + "|".join(IOC) + r")(?![A-Z])")
# words that are on screen in competitions but are not athletes
STOP = set("""PARIS TOKYO LONDON RIO BEIJING ATHENS SYDNEY OLYMPIC OLYMPICS OLYMPIQUES GAMES JEUX WORLD CHAMPIONSHIPS
CHAMPIONSHIP CHAMPIONNATS FINAL FINALS FINALE QUALIFICATION QUALIFYING SEMI TEAM TEAMS FLOOR VAULT RINGS BARS BEAM
POMMEL HORSE PARALLEL HORIZONTAL UNEVEN MENS WOMENS MEN WOMEN ARTISTIC GYMNASTICS GYMNASTIQUE RHYTHMIC TRAMPOLINE
SCORE SCORES TOTAL RANK RANKING DIFFICULTY EXECUTION PENALTY LIVE REPLAY AROUND APPARATUS EVENT ROUND ROTATION
START VALUE OMEGA LONGINES SEIKO FUJITSU CANON TOYOTA GYMNOVA SPIETH JANSSEN FRITSCH SWISS TIMING BRIDGESTONE
SAMSUNG COCA COLA VISA ALIBABA INTEL AIRBNB ATOS PANASONIC TISSOT ADIDAS NIKE PUMA MIZUNO ASICS OLYMP MEDAL MEDALS
GOLD SILVER BRONZE CEREMONY RESULTS RESULT STANDING STANDINGS NEXT LEADER HIGHLIGHTS NATIONAL CUP ASIAN EUROPEAN
PACIFIC COMMONWEALTH UNIVERSIADE ANNEAU ANNEAUX BARRES CHEVAL ARCONS POUTRE SAUT GYMNASTIQUE FEMININ MASCULIN
EQUIPE EQUIPES CONCOURS GENERAL INDIVIDUEL SUELO ANILLAS SALTO BARRA ARZONES PARALELAS ASIMETRICAS FEMENINO
MASCULINO EQUIPO BODEN RINGE SPRUNG RECK BARREN PAUSCHENPFERD SCHWEBEBALKEN STUFENBARREN TURNEN""".split())
FACE_MODELS = {
    "yunet": ("face_detection_yunet_2023mar.onnx",
              ["https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
               "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"]),
    "sface": ("face_recognition_sface_2021dec.onnx",
              ["https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
               "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"]),
}


def ascii_upper(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).upper()


def surname(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ]+", name) if len(w) >= 3]
    return ascii_upper(words[-1]) if words else ""


def named_in(shot: Any, names: list[str]) -> list[str]:
    """The people (from `names`) a shot is about: their surname in its entities or its text."""

    said = ascii_upper(" ".join([*(shot.broll.entities if shot.broll else []), shot.text]))
    return [n for n in names if surname(n) and re.search(rf"\b{re.escape(surname(n))}\b", said)]


def _stop(word: str) -> bool:
    """A venue, sponsor or competition word — also as OCR misreads it ('QOMEGA', 'PARlS')."""

    return word in STOP or any(SequenceMatcher(None, word, s).ratio() >= 0.8 for s in STOP if abs(len(s) - len(word)) <= 2)


Box = tuple[float, float, float, float]          # x0, y0, x1, y1 of an OCR line
SURNAME_FIRST = re.compile(r"^([A-ZÀ-Ý][A-ZÀ-Ý'\-]{2,})\s+[A-ZÀ-Ý][a-zà-ÿ]+")


def _near(a: Box, b: Box) -> bool:
    """Same caption block: on the same line or stacked right above/below, side by side."""

    height = max(a[3] - a[1], b[3] - b[1], 1)
    vertical = abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
    horizontal = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    return vertical <= 2.5 * height and horizontal <= 200


def caption_verdict(frames: list[list[tuple[str, Box]]], names: list[str]) -> str | None:
    """None when the captions agree (or name nobody); else who they name instead. A word is a name when it
    sits in the same caption block as a country code ('JARMAN' under '134 GBR') or reads 'SURNAME Firstname'."""

    wanted = [surname(n) for n in names if surname(n)]
    seen = [w for lines in frames for text, _ in lines for w in re.findall(r"[A-Z]{3,}", ascii_upper(text))]
    if any(s in w or SequenceMatcher(None, w, s).ratio() >= 0.8 for w in seen for s in wanted):
        return None                                          # the named athlete is on the caption ('PHIYULO' too)
    counts: Counter = Counter()
    for lines in frames:
        codes = [box for text, box in lines if CODE.search(ascii_upper(text))]
        found: set[str] = set()
        for text, box in lines:
            if match := SURNAME_FIRST.match(text.strip()):
                found.add(ascii_upper(match.group(1)))
            if any(_near(box, c) for c in codes):
                found |= set(re.findall(r"[A-Z]{4,}", ascii_upper(text)))
        counts.update(w for w in found if not CODE.fullmatch(w) and not _stop(w))
    repeated = [w for w, c in counts.most_common() if c >= 2]
    if not repeated:
        return None
    return f"el rótulo en pantalla dice {', '.join(repeated[:2])}, no {' / '.join(wanted)}"


def model_path(ctx: RunContext, name: str) -> Path | None:
    import requests

    filename, urls = FACE_MODELS[name]
    path = ctx.cache_dir / "models" / filename
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    for url in urls:
        try:
            response = requests.get(url, timeout=120)
            if response.ok and len(response.content) > 100_000:
                path.write_bytes(response.content)
                return path
        except requests.RequestException:
            continue
    return None


class Checker:
    """Loaded once per stage; OCR and face models only when first needed."""

    def __init__(self, ctx: RunContext, people: list[dict[str, Any]]):
        self.ctx, self.cfg = ctx, ctx.section("fallback")
        self.people = {p["name"]: p for p in people if p.get("name")}
        self._ocr: Any = None
        self._faces: Any = None
        self._refs: dict[str, Any] = {}

    # --- frames ---------------------------------------------------------------------------------
    @staticmethod
    def frames(path: Path, kind: str) -> list[np.ndarray]:
        import cv2

        if kind == "image":
            image = cv2.imread(str(path))
            return [image] if image is not None else []
        capture = cv2.VideoCapture(str(path))
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        out = []
        for at in (0.2, 0.5, 0.8):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(count * at))
            ok, frame = capture.read()
            if ok:
                out.append(frame)
        capture.release()
        return out

    # --- captions -------------------------------------------------------------------------------
    def texts(self, frame: np.ndarray) -> list[tuple[str, Box]]:
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        result, _ = self._ocr(frame)
        out = []
        for box, text, _ in result or []:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            out.append((str(text), (min(xs), min(ys), max(xs), max(ys))))
        return out

    # --- faces ----------------------------------------------------------------------------------
    def _face_models(self) -> Any:
        if self._faces is None:
            import cv2

            det, rec = model_path(self.ctx, "yunet"), model_path(self.ctx, "sface")
            if not det or not rec:
                print("   Verificación de caras no disponible (no se pudieron bajar los modelos)")
                self._faces = False
            else:
                self._faces = (cv2.FaceDetectorYN.create(str(det), "", (320, 320), 0.85),
                               cv2.FaceRecognizerSF.create(str(rec), ""))
        return self._faces

    def faces(self, image: np.ndarray, min_size: int = 48) -> list[tuple[np.ndarray, int, bool]]:
        models = self._face_models()
        if not models:
            return []
        detector, recognizer = models
        h, w = image.shape[:2]
        detector.setInputSize((w, h))
        _, found = detector.detect(image)
        out = []
        for f in found if found is not None else []:
            if f[2] < min_size:
                continue
            eyes = abs(f[6] - f[4]) + 1e-6
            frontal = abs(f[8] - (f[4] + f[6]) / 2) / eyes < 0.35
            out.append((recognizer.feature(recognizer.alignCrop(image, f)).copy(), int(f[2]), bool(frontal)))
        return out

    def reference(self, name: str) -> Any:
        """The face of the person's portrait, only if it is big enough to trust."""

        import cv2

        if name in self._refs:
            return self._refs[name]
        ref = None
        person = self.people.get(name) or {}
        path = self.ctx.work_dir / str(person.get("image") or "")
        if person.get("image") and path.is_file():
            image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image is not None and image.ndim == 3 and image.shape[2] == 4:
                alpha = image[..., 3:] / 255.0
                image = (image[..., :3] * alpha + 128 * (1 - alpha)).astype(np.uint8)
            found = self.faces(image, int(self.cfg.get("face_reference_min", 90))) if image is not None else []
            ref = max(found, key=lambda f: f[1])[0] if found else None
        self._refs[name] = ref
        return ref

    def face_verdict(self, frames: list[np.ndarray], names: list[str]) -> str | None:
        import cv2

        refs = [self.reference(n) for n in names]
        if not refs or any(r is None for r in refs):
            return None                                      # someone named has no reliable portrait: cannot tell
        recognizer = self._face_models()[1]
        big_frames, best = 0, -1.0
        size = int(self.cfg.get("face_min_size", 120))
        for frame in frames:
            found = self.faces(frame)
            for feature, _, _ in found:
                best = max(best, *(recognizer.match(feature, r, cv2.FaceRecognizerSF_FR_COSINE) for r in refs))
            big_frames += any(s >= size and frontal for _, s, frontal in found)
        if big_frames >= 2 and best < float(self.cfg.get("face_reject", 0.15)):
            return f"la cara no es la de {' / '.join(names)} (parecido {best:.2f})"
        return None

    # --- both -----------------------------------------------------------------------------------
    def check(self, path: Path, kind: str, names: list[str]) -> str | None:
        """Why this clip does not show `names` (None when it does or it cannot be told)."""

        if not names or not path.is_file():
            return None
        frames = self.frames(path, kind)
        if not frames:
            return None
        if self.cfg.get("caption_check", True):
            why = caption_verdict([self.texts(f) for f in frames], names)
            if why:
                return why
        if self.cfg.get("face_check", True) and self.people:
            return self.face_verdict(frames, names)
        return None


class IdentityCache:
    """work/<slug>/identity.json: verdicts per media file (path + size + mtime + names), so reruns are free."""

    VERSION = 1

    def __init__(self, ctx: RunContext):
        self.path = ctx.work_dir / "identity.json"
        try:
            import json

            self.data: dict[str, Any] = json.loads(self.path.read_text("utf-8")) if self.path.is_file() else {}
        except ValueError:
            self.data = {}

    def get(self, checker: Checker | None, path: Path, kind: str, names: list[str]) -> str | None:
        import json

        if checker is None or not path.is_file():
            return None
        stat = path.stat()
        key = f"{self.VERSION}|{path.name}|{stat.st_size}|{int(stat.st_mtime)}|{'/'.join(sorted(names))}"
        if key not in self.data:
            self.data[key] = checker.check(path, kind, names) or ""
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=0), encoding="utf-8")
        return self.data[key] or None
