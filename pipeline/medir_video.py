"""Any video measured with the figures of the reference videos (objetivo-videos-referencia.md).

    python -m pipeline.medir_video <vídeo o archivo.mp4> [--referencia <vídeo o archivo.mp4>] [--receta persona]
    python -m pipeline.medir_video --referencias        (mide los mp4 de referencias/canales/<canal>/ y los guarda)

Five figures, the ones the recipes are written in: seconds per cut, second of the first picture, share of the video
in text or blank, share in a card over the background, labels per minute.

- One of OUR videos (a slug with work/<vídeo>/timeline.json): exact, from the edit.
- Any mp4 (a reference, a competitor's video): by frames, 4 per second at 160x90 — a cut where the picture changes
  at once, «blank» a frame with nearly no detail, «background» a frame whose border is one flat colour (the brand
  canvas) and, inside it, a card when the middle has a picture, text otherwise. Approximate, as measured by hand for
  the recipes; labels are not counted (that needs OCR).

The references are kept in referencias/canales/<canal>/ (any mp4); their figures are cached next to them
(<archivo>.medidas.json) and the «Puntería» page shows them beside each channel's videos.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

STEP = 0.25                     # seconds between frames read
SIZE = (160, 90)
CUT = 0.55                      # histogram correlation below this between two frames: a cut
FIELDS = (("cutSeconds", "Segundos por corte", "s"), ("firstImage", "1.ª imagen", "s"),
          ("textShare", "Texto o vacío", "%"), ("cardShare", "En tarjeta sobre fondo", "%"),
          ("labelsPerMinute", "Rótulos por minuto", ""))
REFERENCES = Path("referencias") / "canales"
LABEL_TYPES = {"datacard", "stat", "label", "lower", "lugar", "nombre"}


def from_timeline(timeline: dict[str, Any]) -> dict[str, Any]:
    """Exact figures of one of our videos, from its edit."""

    from .revisor import screen_measures

    fps = float(timeline.get("fps") or 30)
    shots = sorted(timeline.get("shots") or [], key=lambda s: int(s.get("from") or 0))
    total = int(timeline.get("durationInFrames") or 0) or max(
        (int(s.get("from") or 0) + int(s.get("durationInFrames") or 0) for s in shots), default=0)
    seconds = total / fps if fps else 0.0
    cuts = sum(1 for a, b in zip(shots, shots[1:])
               if (a.get("media") or {}).get("src") != (b.get("media") or {}).get("src") or not a.get("media"))
    card = sum(int(s.get("durationInFrames") or 0) for s in shots
               if (s.get("media") or {}).get("layout") in ("card", "parallax", "person"))
    labels = sum(1 for g in timeline.get("groups") or []
                 if g.get("kind") in ("datacard", "stat") or str((g.get("graphic") or {}).get("type")) in LABEL_TYPES)
    screen = screen_measures(timeline)
    # «material primero» (prompts/modo-material-primero-prompt.md): the hook, long shots, the other people's voices
    first = next((i for i, s in enumerate(shots) if not s.get("coldOpen")), len(shots))   # the hook: the opening cuts
    hook = sum(int(s.get("durationInFrames") or 0) for s in shots[:first])
    rest = [s for s in shots[first:] if s.get("type") == "broll"]
    voices = sum(int(s.get("durationInFrames") or 0) for s in rest if s.get("coldOpen"))
    material = {"hookSeconds": round(hook / fps, 1) if fps else 0.0,
                "meanShotSeconds": round(sum(int(s.get("durationInFrames") or 0) for s in rest) / len(rest) / fps, 1)
                if rest and fps else None,
                "otherVoiceShare": round(100 * voices / total, 1) if total else 0.0,
                "sources": len({(s.get("media") or {}).get("credit") for s in shots if (s.get("media") or {}).get("credit")})}
    return {**material, "seconds": round(seconds, 1), "cutSeconds": round(seconds / (cuts + 1), 2) if seconds else None,
            "firstImage": screen["firstImage"], "textShare": screen["textShare"],
            "cardShare": round(100 * card / total, 1) if total else 0.0,
            "labelsPerMinute": round(labels / (seconds / 60), 2) if seconds else None, "how": "montaje"}


def classify(frame: np.ndarray) -> str:
    """«blank», «text» (flat background, nothing pictured in the middle), «card» (flat background around a picture)
    or «full» (footage)."""

    gray = frame.mean(axis=2)
    if gray.std() < 6:
        return "blank"
    h, w = gray.shape
    ring = np.concatenate([frame[: h // 8].reshape(-1, 3), frame[-h // 8:].reshape(-1, 3),
                           frame[:, : w // 10].reshape(-1, 3), frame[:, -w // 10:].reshape(-1, 3)]).astype(int)
    colour = np.median(ring, axis=0)
    flat = (np.abs(ring - colour).max(axis=1) <= 18).mean()
    if flat < 0.85:
        return "full"
    middle = frame[h // 5: -h // 5, w // 5: -w // 5].reshape(-1, 3).astype(int)
    away = (np.abs(middle - colour).max(axis=1) > 18)
    pictured = away.mean() > 0.45 and middle[away].std() > 30
    return "card" if pictured else "text"


def _hist(frame: np.ndarray) -> np.ndarray:
    h = np.concatenate([np.histogram(frame[..., c], bins=16, range=(0, 256))[0] for c in range(3)]).astype(float)
    return (h - h.mean()) / (h.std() or 1.0)


def from_frames(frames: list[np.ndarray], step: float = STEP) -> dict[str, Any]:
    """The figures from frames read every `step` seconds."""

    if not frames:
        return {"seconds": 0.0, "cutSeconds": None, "firstImage": None, "textShare": 0.0, "cardShare": 0.0,
                "labelsPerMinute": None, "how": "fotogramas"}
    kinds = [classify(f) for f in frames]
    hists = [_hist(f) for f in frames]
    cuts = sum(1 for a, b in zip(hists, hists[1:]) if float(np.dot(a, b) / len(a)) < CUT)
    seconds = len(frames) * step
    first = next((i * step for i, k in enumerate(kinds) if k in ("full", "card")), None)
    return {"seconds": round(seconds, 1), "cutSeconds": round(seconds / (cuts + 1), 2),
            "firstImage": round(first, 1) if first is not None else None,
            "textShare": round(100 * sum(k in ("text", "blank") for k in kinds) / len(kinds), 1),
            "cardShare": round(100 * kinds.count("card") / len(kinds), 1), "labelsPerMinute": None, "how": "fotogramas"}


def read_frames(path: Path, step: float = STEP) -> list[np.ndarray]:
    w, h = SIZE
    done = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
                           "-vf", f"fps={1 / step:g},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, timeout=1800)
    if done.returncode != 0:
        raise RuntimeError(f"ffmpeg no pudo leer {path.name}: {done.stderr.decode(errors='replace')[-200:]}")
    raw = np.frombuffer(done.stdout, dtype=np.uint8)
    count = raw.size // (w * h * 3)
    return list(raw[: count * w * h * 3].reshape(count, h, w, 3))


def from_file(path: Path) -> dict[str, Any]:
    """Figures of an mp4, cached next to it (<archivo>.medidas.json, by size and date)."""

    cache = path.with_name(path.name + ".medidas.json")
    stamp = f"{path.stat().st_size}:{int(path.stat().st_mtime)}"
    try:
        data = json.loads(cache.read_text("utf-8"))
        if data.get("stamp") == stamp:
            return data["measures"]
    except (OSError, ValueError, KeyError):
        pass
    measures = from_frames(read_frames(path))
    try:
        cache.write_text(json.dumps({"stamp": stamp, "measures": measures}, indent=1), encoding="utf-8")
    except OSError:
        pass
    return measures


def measure(root: Path, what: str) -> dict[str, Any]:
    """A slug of ours (its edit) or a path to a video file."""

    timeline = root / "work" / what / "timeline.json"
    if timeline.is_file():
        return from_timeline(json.loads(timeline.read_text("utf-8")))
    path = Path(what) if Path(what).is_absolute() else root / what
    if path.is_file():
        return from_file(path)
    raise FileNotFoundError(f"«{what}» no es un vídeo montado (work/<vídeo>/timeline.json) ni un archivo")


def channel_reference(root: Path, channel: str) -> dict[str, Any] | None:
    """The cached figures of the channel's reference (referencias/canales/<canal>/*.mp4), never measured here."""

    folder = root / REFERENCES / channel
    for path in sorted(folder.glob("*.mp4")) if folder.is_dir() else []:
        try:
            data = json.loads(path.with_name(path.name + ".medidas.json").read_text("utf-8"))
            return {"file": path.name, **data["measures"]}
        except (OSError, ValueError, KeyError):
            continue
    return None


def table(rows: list[tuple[str, dict[str, Any]]], targets: dict[str, float] | None = None) -> str:
    head = ["Cifra", *[name for name, _ in rows], *(["Objetivo de la receta"] if targets else [])]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    target_keys = {"cutSeconds": "cut_seconds", "firstImage": "first_image", "textShare": "text_share",
                   "cardShare": "card_share"}
    for key, label, unit in FIELDS:
        cells = []
        for _, m in rows:
            value = m.get(key)
            cells.append("—" if value is None else f"{value}{' ' + unit if unit else ''}")
        if targets:
            goal = targets.get(target_keys.get(key, ""))
            if goal is not None and unit == "%":
                goal = round(100 * goal, 1)
            cells.append("—" if goal is None else f"{goal}{' ' + unit if unit else ''}")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append(f"| Duración | " + " | ".join(f"{m.get('seconds')} s" for _, m in rows) + (" | |" if targets else " |"))
    lines.append(f"| Cómo | " + " | ".join(str(m.get("how")) for _, m in rows) + (" | |" if targets else " |"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from .config import PROJECT_ROOT
    from .recetas import TARGETS

    parser = argparse.ArgumentParser(prog="python -m pipeline.medir_video", description=__doc__.splitlines()[0])
    parser.add_argument("video", nargs="?")
    parser.add_argument("--referencia")
    parser.add_argument("--receta", choices=sorted(TARGETS))
    parser.add_argument("--referencias", action="store_true")
    args = parser.parse_args(argv)
    root = PROJECT_ROOT
    if args.referencias:
        found = sorted((root / REFERENCES).glob("*/*.mp4")) if (root / REFERENCES).is_dir() else []
        if not found:
            print(f"No hay referencias: guarda los mp4 en {REFERENCES}/<canal>/")
        for path in found:
            print(f"{path.parent.name}/{path.name}: {from_file(path)}")
        return 0
    if not args.video:
        parser.error("falta el vídeo")
    rows = [(args.video, measure(root, args.video))]
    if args.referencia:
        rows.append((f"{args.referencia} (referencia)", measure(root, args.referencia)))
    print(table(rows, TARGETS.get(args.receta) if args.receta else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
