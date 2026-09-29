"""Graphics made from the movement of the athlete inside a clip: a stroboscopic sequence (every
position of a jump in one image, like the federation's photos) and a replay with a speed ramp
(normal → slow motion at the key moment → normal) with the athlete ringed and their path drawn.

The athlete is found in each sampled frame with the same person segmenter as the athlete cards
(rembg); the biggest person is followed. A stroboscope needs a still camera: the background is the
median of the frames, and a clip whose background moves is rejected.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .context import RunContext

DIR = "motion"
SAMPLE_FPS = 10
MASK_SIDE = 640          # masks are computed small (rembg works at 320 px anyway) and scaled back up
W, H = 1920, 1080


def frames(clip: Path, fps: float = SAMPLE_FPS) -> list[tuple[float, np.ndarray]]:
    """(time, 1920x1080 BGR frame) every 1/fps seconds."""

    import cv2

    capture = cv2.VideoCapture(str(clip))
    native = capture.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(native / fps))
    out: list[tuple[float, np.ndarray]] = []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % step == 0:
            if frame.shape[:2] != (H, W):
                scale = max(W / frame.shape[1], H / frame.shape[0])
                frame = cv2.resize(frame, (round(frame.shape[1] * scale), round(frame.shape[0] * scale)))
                y, x = (frame.shape[0] - H) // 2, (frame.shape[1] - W) // 2
                frame = frame[y:y + H, x:x + W]
            out.append((index / native, frame))
        index += 1
    capture.release()
    return out


def person_mask(frame: np.ndarray, session: Any) -> np.ndarray | None:
    """Full-size soft mask (0-255) of the biggest person, or None when nobody clear is there."""

    import cv2
    from rembg import remove

    small = cv2.resize(frame, (MASK_SIDE, round(MASK_SIDE * H / W)))
    alpha = np.array(remove(cv2.cvtColor(small, cv2.COLOR_BGR2RGB), session=session, only_mask=True))
    if alpha.ndim == 3:
        alpha = alpha[..., 0]
    hard = (alpha > 128).astype(np.uint8)
    coverage = float(hard.mean())
    if not 0.004 <= coverage <= 0.45:
        return None
    count, labels, stats, _ = cv2.connectedComponentsWithStats(hard)
    if count < 2:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[biggest, cv2.CC_STAT_AREA] < 0.6 * hard.sum():
        return None                                        # several people of similar size
    alpha = np.where(labels == biggest, alpha, 0).astype(np.uint8)
    return cv2.resize(alpha, (W, H), interpolation=cv2.INTER_LINEAR)


def box(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask > 128)
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min()), int(ys.max() - ys.min())


def track(sampled: list[tuple[float, np.ndarray]], session: Any) -> list[tuple[float, np.ndarray | None]]:
    return [(t, person_mask(frame, session)) for t, frame in sampled]


def align(sampled: list[tuple[float, np.ndarray]], masks: list[np.ndarray | None],
          ref: int) -> tuple[list[np.ndarray], list[np.ndarray | None]] | None:
    """Warp every frame (and its athlete mask) onto frame `ref`, so a panning or zooming camera
    looks still: ORB features on the background (the athlete masked out) and a RANSAC homography.
    None when some frame cannot be matched (a cut, a blur, a crowd filling the frame)."""

    import cv2

    orb = cv2.ORB_create(3000)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    def features(i: int):
        grey = cv2.cvtColor(sampled[i][1], cv2.COLOR_BGR2GRAY)
        keep = None
        if masks[i] is not None:
            keep = (cv2.dilate(masks[i], np.ones((31, 31), np.uint8)) < 20).astype(np.uint8) * 255
        return orb.detectAndCompute(grey, keep)

    ref_kp, ref_des = features(ref)
    if ref_des is None:
        return None
    frames_out, masks_out = [], []
    for i, (_, frame) in enumerate(sampled):
        if i == ref:
            frames_out.append(frame)
            masks_out.append(masks[i])
            continue
        kp, des = features(i)
        if des is None:
            return None
        matches = sorted(matcher.match(des, ref_des), key=lambda m: m.distance)[:600]
        if len(matches) < 40:
            return None
        src = np.float32([kp[m.queryIdx].pt for m in matches])
        dst = np.float32([ref_kp[m.trainIdx].pt for m in matches])
        homography, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        if homography is None or int(inliers.sum()) < 30:
            return None
        frames_out.append(cv2.warpPerspective(frame, homography, (W, H), borderMode=cv2.BORDER_CONSTANT))
        masks_out.append(None if masks[i] is None else cv2.warpPerspective(masks[i], homography, (W, H)))
    return frames_out, masks_out


def still_camera(sampled: list[tuple[float, np.ndarray]], masks: list[np.ndarray | None], background: np.ndarray) -> bool:
    """The background barely changes outside the athlete (no pan, zoom or cut)."""

    import cv2

    for (_, frame), mask in zip(sampled, masks):
        keep = np.ones((H, W), bool) if mask is None else cv2.dilate(mask, np.ones((41, 41), np.uint8)) < 20
        keep &= frame.sum(axis=2) > 0                      # outside the warped frame
        diff = np.abs(frame.astype(np.int16) - background.astype(np.int16)).mean(axis=2)
        if float(diff[keep].mean()) > 14:
            return False
    return True


def strobe(ctx: RunContext, clip: Path, name: str, session: Any, count: int = 7) -> dict[str, Any] | None:
    """{"background": media, "ghosts": [{"src", "x", "y"}…]}: the athlete's positions over a clean
    background (median of the frames), spread along the movement; None if it cannot be done well."""

    import cv2

    sampled = frames(clip)
    if len(sampled) < 8:
        return None
    masks = [m for _, m in track(sampled, session)]
    found = [(i, m) for i, m in enumerate(masks) if m is not None]
    if len(found) < 0.7 * len(sampled):
        return None
    aligned = align(sampled, masks, len(sampled) // 2)
    if aligned is None:
        return None
    images, masks = aligned
    sampled = [(t, image) for (t, _), image in zip(sampled, images)]
    stack = np.stack([f for _, f in sampled[:: max(1, len(sampled) // 15)]]).astype(np.float32)
    valid = stack.sum(axis=3, keepdims=True) > 0             # warped borders are black: not background
    counts = valid.sum(axis=0)
    stack = np.where(valid, stack, np.nan)
    background = np.nan_to_num(np.nanmedian(stack, axis=0), nan=0.0).astype(np.uint8)
    if float((counts == 0).mean()) > 0.02 or not still_camera(sampled, masks, background):
        return None
    found = [(i, m) for i, m in enumerate(masks) if m is not None and (m > 128).any()]
    boxes = {i: box(m) for i, m in found}
    centres = {i: (b[0] + b[2] / 2, b[1] + b[3] / 2) for i, b in boxes.items()}
    size = float(np.median([b[2] for b in boxes.values()]))
    # positions far enough apart to read as separate figures, along the whole movement
    chosen = [found[0][0]]
    for i, _ in found[1:]:
        (x0, y0), (x1, y1) = centres[chosen[-1]], centres[i]
        if ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 >= 0.55 * size:
            chosen.append(i)
    if len(chosen) < 4:
        return None                                        # the athlete hardly moves: nothing to show
    if len(chosen) > count:
        chosen = [chosen[round(k * (len(chosen) - 1) / (count - 1))] for k in range(count)]
    out = ctx.work_dir / DIR
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{name}-strobe"
    cv2.imwrite(str(out / f"{stem}-bg.jpg"), background, [cv2.IMWRITE_JPEG_QUALITY, 92])
    ghosts = []
    for k, i in enumerate(chosen):
        x, y, w, h = boxes[i]
        pad = 12
        x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
        rgba = np.dstack([sampled[i][1][y0:y1, x0:x1], masks[i][y0:y1, x0:x1]])
        path = out / f"{stem}-{k}.png"
        cv2.imwrite(str(path), rgba)
        ghosts.append({"src": str(path.relative_to(ctx.work_dir)), "kind": "image", "source": "youtube",
                       "x": round(x0 / W * 100, 2), "y": round(y0 / H * 100, 2),
                       "w": round((x1 - x0) / W * 100, 2), "h": round((y1 - y0) / H * 100, 2)})
    return {"background": {"src": str((out / f"{stem}-bg.jpg").relative_to(ctx.work_dir)), "kind": "image",
                           "source": "youtube"}, "ghosts": ghosts}


def ramp_map(peak: float, length: float, slow: float, half: float) -> list[tuple[float, float, float]]:
    """[(source start, source end, speed)] of the ramp: 1x, `slow` around the peak, 1x."""

    a, b = max(0.0, peak - half), min(length, peak + half)
    parts = [(0.0, a, 1.0), (a, b, slow), (b, length, 1.0)]
    return [p for p in parts if p[1] - p[0] > 0.05]


def ramp_time(t: float, parts: list[tuple[float, float, float]]) -> float:
    """Where source time t lands in the ramped clip."""

    out = 0.0
    for start, end, speed in parts:
        if t <= end:
            return out + (max(t, start) - start) / speed
        out += (end - start) / speed
    return out


def replay(ctx: RunContext, clip: Path, name: str, session: Any, slow: float = 0.35, half: float = 0.5) -> dict[str, Any] | None:
    """The clip with a speed ramp around the key moment (the athlete's highest point; the middle if
    they are not tracked), plus their track in ramped time: {"video", "track": [[t, x, y, w, h]…] in
    % of the frame, "peak": s}."""

    sampled = frames(clip)
    if len(sampled) < 6:
        return None
    length = sampled[-1][0] + 1 / SAMPLE_FPS
    tracked = [(t, box(m)) for t, m in track(sampled, session) if m is not None]
    usable = len(tracked) >= 0.6 * len(sampled)
    peak = min(tracked, key=lambda p: p[1][1])[0] if usable else length / 2
    peak = min(max(peak, half), length - half) if length > 2 * half else length / 2
    parts = ramp_map(peak, length, slow, half)
    out = ctx.work_dir / DIR
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{name}-replay.mp4"
    chains, labels = [], []
    for k, (start, end, speed) in enumerate(parts):
        slowdown = f",setpts={1 / speed:.4f}*PTS,minterpolate=fps=30:mi_mode=blend" if speed < 1 else ""
        chains.append(f"[0:v]trim={start:.3f}:{end:.3f},setpts=PTS-STARTPTS{slowdown}[p{k}]")
        labels.append(f"[p{k}]")
    graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(parts)}:v=1:a=0,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[v]"
    result = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-filter_complex", graph, "-map", "[v]", "-an",
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(target)],
                            capture_output=True, text=True)
    if result.returncode != 0 or not target.is_file():
        return None
    seconds = ramp_time(length, parts)
    track_out = [[round(ramp_time(t, parts), 3), round(x / W * 100, 2), round(y / H * 100, 2),
                  round(w / W * 100, 2), round(h / H * 100, 2)] for t, (x, y, w, h) in tracked] if usable else []
    return {"video": {"src": str(target.relative_to(ctx.work_dir)), "kind": "video", "source": "youtube",
                      "seconds": round(seconds, 3)},
            "track": track_out, "peak": round(ramp_time(peak, parts), 3), "seconds": round(seconds, 3)}
