"""People cards — work/<slug>/people.json + people/<person>.png.

For the protagonist and the other people the narration names (lower-third names), find a photo
(web photos, the athlete library, Wikimedia) — or, failing that, a frame of the person's own videos —
that shows exactly one face, remove the background (rembg) and keep the cutout in the athlete library. The timeline then turns the shot
where the voice first names each person into a presentation card: the cutout over the channel
grid with the name, like sports channels introduce their protagonists.

Optional: without the `rembg` package (or without a usable photo) there are simply no cards.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

from . import library
from .analysis.detectors import Detectors
from .context import RunContext
from .ingest import fetch_image
from .schemas import BrollSpec, Candidate, ShotsFile
from .sourcing.common import USER_AGENT, key
from .sourcing.images import ImageSources

STAGE = "people"
OUTPUT = "people.json"
CARD_DIR = "people"


def people_to_introduce(story: ShotsFile, limit: int) -> list[str]:
    names: list[str] = []
    person = story.subject.split("·")[0].strip()
    if person:
        names.append(person)
    for shot in story.shots:
        if shot.label and shot.label.kind == "name" and shot.label.text not in names:
            names.append(shot.label.text)
    return names[:limit]


def photo_candidates(ctx: RunContext, person: str, notes: list[str]) -> list[Candidate]:
    """Web photos (Google Images/DuckDuckGo) and Commons photos naming the person, plus library ones."""

    from .fallback import web_photos   # late import: fallback imports a lot

    broll = BrollSpec(visualIntent=f"portrait of {person}", queries=[person, person, person],
                      queriesLocal=[person], entities=[person])
    found = list(web_photos(ctx, broll, notes).values())
    images_cfg = ctx.section("sourcing").get("images", {})
    commons = ImageSources(root=ctx.root, cache_dir=ctx.cache_dir, serper_key="",
                           config={**images_cfg, "min_aspect": 0.5, "min_width": 600, "web": {"enabled": False},
                                   "openverse": {"enabled": False}, "pixabay": {"enabled": False}})
    found += [c for c in commons.search(broll, notes)[1] if library.names_person(c, person)]
    for raw in library.load(ctx, person)["photos"].values():
        try:
            found.append(Candidate.model_validate(raw))
        except ValueError:
            continue
    seen: set[str] = set()
    return [c for c in found if c.mediaUrl and not (c.id in seen or seen.add(c.id))]


def video_frames(ctx: RunContext, person: str, detectors: Detectors, limit: int = 6) -> list[tuple[np.ndarray, dict[str, Any]]]:
    """Plan B when no photo works: frames of the person's own videos (library, already downloaded in
    HD) where exactly one clear face is visible, biggest face first."""

    found: list[tuple[float, np.ndarray, dict[str, Any]]] = []
    for cid, raw in library.load(ctx, person)["videos"].items():
        for clip in sorted((ctx.cache_dir / "videos" / cid.removeprefix("yt:")).glob("hd*.mp4"))[:3]:
            capture = cv2.VideoCapture(str(clip))
            count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            for step in range(1, 5):
                capture.set(cv2.CAP_PROP_POS_FRAMES, count * step // 5)
                ok, frame = capture.read()
                if not ok:
                    continue
                faces = detectors.faces(frame, min_area=0.004)
                if len(faces) == 1 and faces[0] >= 0.012:
                    found.append((faces[0], frame, {"credit": raw.get("credit", ""), "url": raw.get("url", ""),
                                                    "candidateId": cid, "source": "youtube"}))
            capture.release()
    found.sort(key=lambda item: -item[0])
    return [(frame, meta) for _, frame, meta in found[:limit]]


CUTOUT_VERSION = 3   # 2: best-scored upright portrait among the candidates (1: the first that worked)


def upright(face: dict) -> bool:
    """Eyes level (roll < 30°) and above the nose, the nose above the mouth: not upside down or lying."""

    (rex, rey), (lex, ley), (nx, ny), (rmx, rmy), (lmx, lmy) = face["landmarks"]
    roll = abs(math.degrees(math.atan2(ley - rey, lex - rex)))
    roll = min(roll, 180 - roll) if lex < rex else roll       # mirrored landmarks
    eyes, mouth = (rey + ley) / 2, (rmy + lmy) / 2
    return roll < 30 and eyes < ny < mouth


def portrait_score(image: np.ndarray, detectors: Detectors, box: tuple[int, int, int, int] | None) -> float | None:
    """How good a photo is for an athlete card; None if unusable. Rewards one clear upright face,
    big, at the top of a standing figure, in a sharp enough photo."""

    faces = detectors.face_details(image)
    if len(faces) != 1 or faces[0]["area"] < 0.004 or not upright(faces[0]):
        return None
    face = faces[0]
    score = min(face["area"] / 0.04, 1.0)                     # face size, up to 4 % of the photo
    score += 0.3 * min(image.shape[0] / 900, 1.0)             # resolution
    if box is not None:
        top, bottom, left, right = box
        fx, fy, fw, fh = face["box"]
        head = (fy + fh / 2 - top) / max(1, bottom - top)      # 0 = top of the figure
        # The face detector reads landmarks as upright even on a flipping gymnast: the figure decides.
        if head > 0.45 or (right - left) > 1.3 * (bottom - top):
            return None                                      # head not at the top, or lying / mid-flip
        score += 0.6 if head <= 0.35 else max(0.0, 0.6 - (head - 0.35) * 2)
        score += 0.3 if (bottom - top) >= 1.1 * (right - left) else 0.0   # standing
    return score


def cutout(image: np.ndarray, session: Any) -> np.ndarray | None:
    """RGBA cutout cropped to the person, or None if the mask is implausible."""

    found = cutout_with_box(image, session)
    return found[0] if found else None


def cutout_with_box(image: np.ndarray, session: Any) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    """(RGBA cutout cropped to the person, its box top/bottom/left/right in the image)."""

    from rembg import remove

    rgba = remove(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), session=session)
    alpha = rgba[..., 3]
    coverage = float((alpha > 128).mean())
    if not 0.06 <= coverage <= 0.85:
        return None
    ys, xs = np.nonzero(alpha > 32)
    top, bottom, left, right = ys.min(), ys.max(), xs.min(), xs.max()
    crop = rgba[top : bottom + 1, left : right + 1]
    scale = min(1.0, 1100 / crop.shape[0])
    if scale < 1.0:
        crop = cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(crop, cv2.COLOR_RGBA2BGRA), (int(top), int(bottom), int(left), int(right))


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "shots.json"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("people")
    story = ShotsFile.model_validate(ctx.read_json("shots.json"))
    people: list[dict[str, Any]] = []
    names = people_to_introduce(story, int(cfg.get("max", 4))) if cfg.get("enabled", True) else []
    try:
        from rembg import new_session
    except ImportError:
        names = []
        print("   Sin tarjetas de personas: instala 'rembg[cpu]' para recortar a los atletas")
    session = new_session(str(cfg.get("model", "u2net_human_seg"))) if names else None
    detectors = Detectors(cache_dir=ctx.cache_dir)
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    out_dir = ctx.work_dir / CARD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    for person in names:
        lib_dir = library.folder(ctx, person)
        meta = library.load(ctx, person).get("cutout")
        stored = lib_dir / "cutout.png"
        if not (stored.is_file() and isinstance(meta, dict) and meta.get("v", 1) >= CUTOUT_VERSION):
            meta = None
            notes: list[str] = []
            best: tuple[float, np.ndarray, dict[str, Any]] | None = None
            for candidate in photo_candidates(ctx, person, notes)[: int(cfg.get("tries", 8))]:
                original = ctx.cache_dir / "images" / "original" / f"{key(candidate.mediaUrl)}{Path(candidate.mediaUrl.split('?')[0]).suffix or '.jpg'}"
                try:
                    if not original.is_file():
                        fetch_image(http, candidate.mediaUrl, original)
                    image = cv2.imread(str(original))
                    if image is None or portrait_score(image, detectors, None) is None:
                        continue                          # no single upright face: not worth cutting out
                    found = cutout_with_box(image, session)
                except Exception as error:  # one bad photo: try the next
                    notes.append(f"{candidate.id}: {str(error)[:80]}")
                    continue
                if found is None:
                    continue
                score = portrait_score(image, detectors, found[1])
                if score is None:
                    continue
                if best is None or score > best[0]:
                    best = (score, found[0], {"credit": candidate.credit, "url": candidate.url,
                                              "candidateId": candidate.id, "source": candidate.source})
            if best is None:
                for frame, frame_meta in video_frames(ctx, person, detectors):
                    found = cutout_with_box(frame, session)
                    if found is not None and portrait_score(frame, detectors, found[1]) is not None:
                        best = (0.0, found[0], frame_meta)
                        break
            if best is not None:
                lib_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(stored), best[1])
                meta = {**best[2], "v": CUTOUT_VERSION}
            if meta is not None:
                full = library.load(ctx, person)
                full["cutout"] = meta
                library.save(ctx, person, full)
        if meta is None:
            print(f"   {person}: sin foto recortable (se queda sin tarjeta)")
            continue
        target = out_dir / f"{library.person_key(person)}.png"
        shutil.copy2(stored, target)
        people.append({"name": person, "image": str(target.relative_to(ctx.work_dir)).replace("\\", "/"), **meta})
        print(f"   {person}: tarjeta con recorte · {meta['credit']}")
    ctx.write_json(OUTPUT, {"slug": ctx.slug, "people": people})


def validate(ctx: RunContext) -> bool:
    data = ctx.read_json(OUTPUT)
    return all((ctx.work_dir / p["image"]).is_file() for p in data.get("people", []))
