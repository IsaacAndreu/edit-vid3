"""Stage 4 — local analysis and scoring (no paid APIs).

Coarse pass (every candidate):
  YouTube storyboard thumbnails and image candidates are embedded with CLIP and compared
  with the shot's prompts. The first/last 5 % of each video, blank tiles and near-duplicate
  consecutive thumbnails are skipped; per video at most `max_frames_per_video` are encoded.
Fine pass (only the best `fine_windows` moments per shot):
  a ~10 s 360p window around each moment is downloaded, cut into sub-shots with
  PySceneDetect, sampled every `fine_sample_seconds`, and the best ≤5 s span inside one
  sub-shot is scored: CLIP + entity mention in the source transcript + sharpness + motion.
  Black, frozen, text-heavy and talking-head spans are discarded.

Writes work/<slug>/scores/<shot_id>.json (+ _summary.json). De-duplication across shots
(pHash / timestamp overlap) happens when a clip is actually assigned, in stage 5.
"""

from __future__ import annotations

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import ValidationError

from ..context import RunContext
from ..schemas import MAX_THIRD_PARTY_SECONDS, Candidate, Option, OptionScores, Shot, ShotCandidates, ShotScores, ShotsFile
from ..sourcing import needs_footage, youtube_source
from ..sourcing.common import SourceUnavailable, key, tokens
from ..sourcing.youtube import YouTubeSource
from . import detectors as det
from .clip import ClipScorer


STAGE = "analysis"
OUTPUT = "scores"
VERSION = 5  # bump when the scoring logic changes: invalidates per-shot results
SUMMARY = "_summary.json"


# --- coarse: storyboard thumbnails ------------------------------------------------------


def storyboard_frames(candidate: Candidate, root: Path, cfg: dict[str, Any]) -> tuple[list[float], list[np.ndarray]]:
    board = candidate.storyboard
    assert board is not None
    duration = float(candidate.durationSeconds or board.frames * board.interval)
    margin = duration * float(cfg.get("edge_margin", 0.05))
    sheets: dict[int, np.ndarray | None] = {}
    times: list[float] = []
    tiles: list[np.ndarray] = []
    previous: np.ndarray | None = None
    for index in range(board.frames):
        t = index * board.interval
        if t < margin or t + board.interval > duration - margin:
            continue
        sheet_index, x, y = board.locate(index)
        if sheet_index not in sheets:
            sheets[sheet_index] = cv2.imread(str(root / board.sheets[sheet_index])) if sheet_index < len(board.sheets) else None
        sheet = sheets[sheet_index]
        if sheet is None or y + board.tileHeight > sheet.shape[0] or x + board.tileWidth > sheet.shape[1]:
            continue
        tile = sheet[y : y + board.tileHeight, x : x + board.tileWidth]
        if det.detail(tile) < 8 or det.luma(tile) < 18:  # blank, black or fade
            continue
        if previous is not None and det.difference(tile, previous) < float(cfg.get("dedupe_difference", 4)):
            continue
        previous = tile
        times.append(t)
        tiles.append(tile)
    limit = int(cfg.get("max_frames_per_video", 40))
    if len(tiles) > limit:
        keep = np.linspace(0, len(tiles) - 1, limit).round().astype(int)
        times = [times[i] for i in keep]
        tiles = [tiles[i] for i in keep]
    return times, tiles


def coarse_moments(times: np.ndarray, sims: np.ndarray, interval: float, per_video: int) -> list[tuple[float, float]]:
    """Best (time, similarity) moments of one video, at least 3 thumbnails apart."""

    picked: list[tuple[float, float]] = []
    for i in np.argsort(-sims):
        t = float(times[i])
        if all(abs(t - p) >= 3 * interval for p, _ in picked):
            picked.append((t, float(sims[i])))
        if len(picked) >= per_video:
            break
    return picked


# --- per-source cached features (also precomputed during sourcing) ---------------------


def frames_key(candidate_id: str, cfg: dict[str, Any]) -> str:
    settings = (cfg.get("edge_margin", 0.05), cfg.get("max_frames_per_video", 40), cfg.get("dedupe_difference", 4))
    return f"{candidate_id.replace(':', '_')}-{key(*settings)[:8]}"


def video_features(clip: ClipScorer, candidate: Candidate, root: Path, cfg: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """(times, CLIP vectors) of a video's storyboard thumbnails — cached globally."""

    return clip.cached(frames_key(candidate.id, cfg), lambda: storyboard_frames(candidate, root, cfg))


def image_features(
    clip: ClipScorer, detectors: det.Detectors, candidate: Candidate, root: Path
) -> tuple[np.ndarray, dict[str, Any]] | None:
    """(CLIP vector, checks) of an image candidate — cached globally."""

    from ..sourcing.common import cached_json

    if not candidate.imagePath:
        return None
    image_key = f"img_{key(candidate.imagePath)}"
    picture = None

    def load():
        nonlocal picture
        if picture is None:
            picture = cv2.imread(str(root / candidate.imagePath))
        return picture

    if load() is None and not (clip.cache_dir / f"{image_key}.npz").is_file():
        return None
    _, vectors = clip.cached(image_key, lambda: ([0.0], [load()]))
    checks = cached_json(
        clip.cache_dir / f"{image_key}.checks-v2.json",
        lambda: {"sharpness": det.sharpness(load()), "textArea": detectors.text_area(load()), "phash": det.phash(load())},
    )
    return vectors[0].astype(np.float32), checks


# --- fine: 360p window ------------------------------------------------------------------


def read_frames(path: Path, offsets: list[float]) -> list[tuple[float, np.ndarray]]:
    capture = cv2.VideoCapture(str(path))
    frames = []
    for offset in offsets:
        capture.set(cv2.CAP_PROP_POS_MSEC, offset * 1000)
        ok, frame = capture.read()
        if ok:
            frames.append((offset, frame))
    capture.release()
    return frames


def video_length(path: Path) -> float:
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    capture.release()
    return float(count / fps) if fps else 0.0


def scene_spans(path: Path, lo: float, hi: float, threshold: float) -> list[tuple[float, float]]:
    """Sub-shots of path between file offsets lo and hi (seconds)."""

    import logging

    from scenedetect import ContentDetector, detect

    logging.getLogger("pyscenedetect").setLevel(logging.WARNING)
    try:
        scenes = detect(str(path), ContentDetector(threshold=threshold), start_time=lo, end_time=hi)
    except Exception:
        scenes = []
    spans = [(max(lo, s.get_seconds()), min(hi, e.get_seconds())) for s, e in scenes]
    return [(a, b) for a, b in spans if b > a] or [(lo, hi)]


def file_start(path: Path) -> float:
    """Source second at which a cached a360_<start>_<end>.mp4 file begins."""

    try:
        return float(path.stem.split("_")[1])
    except (IndexError, ValueError):
        return 0.0


def fine_options(
    *,
    window_path: Path,
    window: tuple[float, float],
    needed: float,
    shot_vector: np.ndarray,
    clip: ClipScorer,
    detectors: det.Detectors,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """Best span per sub-shot of `window` (source seconds) inside a downloaded file.

    The file may cover more than the window (a cached longer download is reused).
    Returned start/end are source seconds.
    """

    offset = file_start(window_path)
    length = video_length(window_path)
    lo, hi = max(0.0, window[0] - offset), min(length, window[1] - offset)
    if hi - lo <= 0:
        return []
    step = float(cfg.get("fine_sample_seconds", 1.0))
    samples = read_frames(window_path, [round(t, 2) for t in np.arange(lo + 0.1, max(lo + 0.2, hi - 0.1), step)])
    if not samples:
        return []
    sims = clip.embed_images([f for _, f in samples]) @ shot_vector
    results = []
    for scene_start, scene_end in scene_spans(window_path, lo, hi, float(cfg.get("scene_threshold", 27))):
        span = min(needed, scene_end - scene_start)
        if span < min(needed, float(cfg.get("min_span_seconds", 1.2))):
            continue
        best: tuple[float, float] | None = None
        for start in np.arange(scene_start, scene_end - span + 1e-6, 0.5):
            inside = [s for (t, _), s in zip(samples, sims) if start <= t <= start + span]
            if inside and (best is None or float(np.mean(inside)) > best[1]):
                best = (float(start), float(np.mean(inside)))
        if best is None:
            continue
        start, clip_score = best
        frames = [f for _, f in read_frames(window_path, [start + span * q for q in (0.2, 0.5, 0.8)])]
        if len(frames) < 2:
            continue
        middle = frames[len(frames) // 2]
        text_area = detectors.text_area(middle)
        faces = [detectors.face_area(f) for f in frames]
        big_centred = [a for a, cx in faces if a >= float(cfg.get("talking_head_face_area", 0.05)) and 0.2 <= cx <= 0.8]
        motion = det.difference(frames[0], frames[-1])
        discarded = None
        if det.luma(middle) < 20:
            discarded = "fotograma negro"
        elif motion < float(cfg.get("frozen_difference", 0.5)):
            discarded = "imagen congelada"
        elif text_area > float(cfg.get("max_text_area", 0.08)):
            discarded = f"texto en pantalla ({text_area:.0%})"
        elif len(big_centred) >= 2:
            discarded = "presentador hablando a cámara"
        results.append({
            "start": offset + start,
            "end": offset + start + span,
            "scores": {
                "clip": round(clip_score, 4),
                "sharpness": round(float(np.mean([det.sharpness(f) for f in frames])), 3),
                "motion": round(min(1.0, motion / 20.0), 3),
                "textArea": round(text_area, 4),
                "faceArea": round(max(a for a, _ in faces), 4),
            },
            "discarded": discarded,
            "phash": det.phash(middle),
        })
    return results


def entity_match(text: str, entities: list[str]) -> float:
    """1.0 if `text` names the shot's primary entity, 0.5 if it names a secondary one, else 0.

    "Names" = at least 75 % of the entity's words (≥4 letters): "Gran Casino de Ciudad Real"
    does not name "Gran Casino de Madrid" just because it shares "gran" and "casino".
    """

    found = tokens(text)
    for rank, entity in enumerate(entities):
        words = {t for t in tokens(entity) if len(t) >= 4}
        if words and len(words & found) >= math.ceil(0.75 * len(words)):
            return 1.0 if rank == 0 else 0.5
    return 0.0


def entity_score(captions: list[tuple[float, float, str]], title: str, entities: list[str], start: float, end: float) -> float:
    """Spec: bonus when the source's transcript (around the fragment) names the shot's entities."""

    near = " ".join(text for a, b, text in captions if b >= start - 10 and a <= end + 10)
    return max(entity_match(near, entities), 0.5 * entity_match(title, entities))


def total_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    return round(
        float(weights.get("clip", 1.0)) * scores.get("clip", 0.0)
        + float(weights.get("entity", 0.10)) * scores.get("entity", 0.0)
        + float(weights.get("sharpness", 0.02)) * scores.get("sharpness", 0.0)
        + float(weights.get("motion", 0.01)) * scores.get("motion", 0.0),
        4,
    )


# --- stage ------------------------------------------------------------------------------


def make_models(ctx: RunContext) -> tuple[ClipScorer, det.Detectors]:
    cfg = ctx.section("analysis")
    clip = ClipScorer(
        cache_dir=ctx.cache_dir,
        model=str(cfg.get("model", "ViT-B-32")),
        pretrained=str(cfg.get("pretrained", "laion2b_s34b_b79k")),
        batch_size=int(cfg.get("batch_size", 64)),
    )
    return clip, det.Detectors(cache_dir=ctx.cache_dir, ocr_side=int(cfg.get("ocr_side", 480)))


def prompts_for(shot: Shot) -> list[str]:
    assert shot.broll is not None
    return list(dict.fromkeys([shot.broll.visualIntent, *shot.broll.queries]))


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "shots.json", ctx.work_dir / "candidates"]


def run(ctx: RunContext) -> None:
    analyse(ctx)


def analyse(ctx: RunContext, only: set[str] | None = None) -> None:
    """Score every footage shot (or just `only`, for quick experiments)."""

    cfg = ctx.section("analysis")
    weights = cfg.get("weights", {})
    started = time.monotonic()
    shots = [
        s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots
        if needs_footage(s) and (only is None or s.id in only)
    ]
    candidates = {
        s.id: ShotCandidates.model_validate_json((ctx.work_dir / "candidates" / f"{s.id}.json").read_text(encoding="utf-8"))
        for s in shots
    }
    out_dir = ctx.work_dir / OUTPUT
    out_dir.mkdir(parents=True, exist_ok=True)

    config_key = key(cfg, VERSION)
    todo: list[Shot] = []
    shot_hash: dict[str, str] = {}
    for shot in shots:
        shot_hash[shot.id] = key(shot.model_dump(), candidates[shot.id].model_dump(), config_key)
        path = out_dir / f"{shot.id}.json"
        if path.is_file():
            try:
                if ShotScores.model_validate_json(path.read_text(encoding="utf-8")).inputsHash == shot_hash[shot.id]:
                    continue
            except (ValidationError, ValueError):
                pass
        todo.append(shot)
    print(f"   {len(shots) - len(todo)} planos ya analizados; {len(todo)} pendientes")
    if not todo:
        _write_summary(ctx, shots)
        return

    clip, detectors = make_models(ctx)
    shot_vectors = {s.id: clip.shot_vector(prompts_for(s)) for s in todo}

    # 1. Coarse embeddings, once per source (cached globally).
    videos: dict[str, Candidate] = {}
    images: dict[str, Candidate] = {}
    for shot in todo:
        for c in candidates[shot.id].candidates:
            (videos if c.kind == "video" else images)[c.id] = c
    frame_index: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for number, (cid, c) in enumerate(videos.items(), start=1):
        frame_index[cid] = video_features(clip, c, ctx.root, cfg)
        if number % 50 == 0:
            print(f"   miniaturas: {number}/{len(videos)} vídeos ({time.monotonic() - started:.0f} s)")
    image_vectors: dict[str, np.ndarray] = {}
    image_checks: dict[str, dict[str, Any]] = {}
    for cid, c in images.items():
        features = image_features(clip, detectors, c, ctx.root)
        if features is not None:
            image_vectors[cid], image_checks[cid] = features
    print(f"   Pasada gruesa: {len(videos)} vídeos, {len(image_vectors)} imágenes ({time.monotonic() - started:.0f} s)")

    # 2. Coarse options per shot and the fine windows worth downloading.
    per_video = int(cfg.get("moments_per_video", 2))
    fine_windows = int(cfg.get("fine_windows", 2))
    pad = float(cfg.get("window_padding", 2.0))
    coarse: dict[str, list[dict[str, Any]]] = {}
    jobs: dict[tuple[str, float, float], list[str]] = {}
    for shot in todo:
        vector = shot_vectors[shot.id]
        needed = min(shot.duration, MAX_THIRD_PARTY_SECONDS)
        options: list[dict[str, Any]] = []
        for c in candidates[shot.id].candidates:
            if c.kind == "video" and c.id in frame_index:
                times, vectors = frame_index[c.id]
                if len(times) == 0:
                    continue
                sims = vectors.astype(np.float32) @ vector
                title_entity = 0.5 * entity_match(c.title, shot.broll.entities)
                for t, sim in coarse_moments(times, sims, c.storyboard.interval, per_video):
                    options.append({"candidate": c, "t": t, "clip": sim, "entity": title_entity})
            elif c.kind == "image" and c.id in image_vectors:
                options.append({"candidate": c, "t": None, "clip": float(image_vectors[c.id] @ vector),
                                "entity": entity_match(c.title, shot.broll.entities)})
        entity_weight = float(weights.get("entity", 0.10))
        options.sort(key=lambda o: -(o["clip"] + entity_weight * o["entity"]))
        coarse[shot.id] = options
        chosen_videos: list[str] = []
        # Named places/people are where CLIP is weakest: give the fine pass (and the judge) more to see.
        windows_for_shot = fine_windows + (int(cfg.get("extra_windows_with_entities", 1)) if shot.broll.entities else 0)
        for option in options:
            c = option["candidate"]
            if c.kind != "video" or c.id in chosen_videos:  # the best moments of different videos
                continue
            duration = float(c.durationSeconds or 0)
            margin = duration * float(cfg.get("edge_margin", 0.05))
            a = max(margin, option["t"] - pad)
            b = min(duration - margin, option["t"] + c.storyboard.interval + pad)
            if b - a < needed:
                continue
            jobs.setdefault((c.id, round(a, 2), round(b, 2)), []).append(shot.id)
            option["window"] = (round(a, 2), round(b, 2))
            chosen_videos.append(c.id)
            if len(chosen_videos) >= windows_for_shot:
                break

    # 3. Fine pass: downloads in threads, analysis in this thread as they arrive.
    yt_cfg = ctx.section("sourcing").get("youtube", {})
    youtube = youtube_source(ctx)
    fine: dict[tuple[str, float, float], list[dict[str, Any]]] = {}
    notes: dict[str, list[str]] = {s.id: [] for s in todo}
    print(f"   Pasada fina: {len(jobs)} ventanas de ~{2 * pad + 5:.0f} s a 360p")

    # A video with several windows comes down once, whole at 360p, and the windows are cut from it.
    by_video: dict[str, list[tuple[str, float, float]]] = {}
    for job in jobs:
        by_video.setdefault(job[0], []).append(job)
    whole_from = int(cfg.get("whole_video_windows", 3))   # 3+ windows: one 360p download pays off

    def download(video: str) -> list[tuple[tuple[str, float, float], Path | Exception]]:
        its = by_video[video]
        if len(its) >= whole_from:
            try:
                youtube.prefetch_sections(video.removeprefix("yt:"))
            except Exception:
                pass
        out: list[tuple[tuple[str, float, float], Path | Exception]] = []
        for job in its:
            try:
                out.append((job, youtube.download_section(video.removeprefix("yt:"), job[1], job[2])))
            except (SourceUnavailable, Exception) as error:
                out.append((job, error))
        return out

    done = 0
    with ThreadPoolExecutor(max_workers=max(int(yt_cfg.get("concurrency", 3)), getattr(youtube, "concurrency", 0))) as pool:
        futures = [pool.submit(download, video) for video in by_video]
        arrived = ((job, result) for future in as_completed(futures) for job, result in future.result())
        for job, result in arrived:
            done += 1
            if isinstance(result, Exception):
                for sid in jobs[job]:
                    notes[sid].append(f"{job[0]} {job[1]}-{job[2]}: {str(result)[:120]}")
                continue
            path = result
            for sid in jobs[job]:
                shot = next(s for s in todo if s.id == sid)
                fine[(sid, *job)] = [
                    {**o, "path": path}
                    for o in fine_options(
                        window_path=path,
                        window=(job[1], job[2]),
                        needed=min(shot.duration, MAX_THIRD_PARTY_SECONDS),
                        shot_vector=shot_vectors[sid],
                        clip=clip,
                        detectors=detectors,
                        cfg=cfg,
                    )
                ]
            if done % 50 == 0:
                print(f"   ventanas: {done}/{len(jobs)} ({time.monotonic() - started:.0f} s)")

    # 4. Assemble per-shot results.
    for shot in todo:
        needed = min(shot.duration, MAX_THIRD_PARTY_SECONDS)
        entities = shot.broll.entities if shot.broll else []
        options: list[Option] = []
        for option in coarse[shot.id]:
            c: Candidate = option["candidate"]
            if c.kind == "image":
                checks = image_checks[c.id]
                scores = {"clip": round(option["clip"], 4), "sharpness": round(checks["sharpness"], 3),
                          "textArea": round(checks["textArea"], 4)}
                if entities and entity_match(c.title, entities):
                    scores["entity"] = entity_match(c.title, entities)
                too_much_text = checks["textArea"] > float(cfg.get("max_text_area_image", 0.12))
                options.append(Option.model_validate({
                    "candidateId": c.id, "source": c.source, "kind": "image", "pass": "fine",
                    "analysisPath": c.imagePath, "scores": scores, "total": total_score(scores, weights),
                    "discarded": f"texto en pantalla ({checks['textArea']:.0%})" if too_much_text else None,
                    "phash": checks["phash"],
                }))
                continue
            window = option.get("window")
            refined = fine.get((shot.id, c.id, *window)) if window else None
            if refined:
                captions = youtube.captions(c.id.removeprefix("yt:")) if entities else []
                for item in refined:
                    scores = {**item["scores"], "entity": entity_score(captions, c.title, entities, item["start"], item["end"])}
                    options.append(Option.model_validate({
                        "candidateId": c.id, "source": c.source, "kind": "video", "pass": "fine",
                        "start": round(item["start"], 3), "end": round(item["end"], 3),
                        "analysisPath": str(Path(item["path"]).relative_to(ctx.root)),
                        "scores": scores, "total": total_score(scores, weights),
                        "discarded": item["discarded"], "phash": item["phash"],
                    }))
            else:
                # Not refined (outside the top windows or download failed): keep the thumbnail estimate.
                start = option["t"]
                scores = {"clip": round(option["clip"], 4), "entity": option["entity"]}
                options.append(Option.model_validate({
                    "candidateId": c.id, "source": c.source, "kind": "video", "pass": "coarse",
                    "start": round(start, 3), "end": round(start + needed, 3),
                    "scores": scores, "total": total_score(scores, weights),
                }))
        min_clip = float(cfg.get("min_clip", 0.20))
        min_clip_entity = float(cfg.get("min_clip_entity", 0.15))  # the source names the place/person
        options = [
            o if o.discarded or o.scores.clip >= (min_clip_entity if o.scores.entity >= 0.5 else min_clip)
            else o.model_copy(update={"discarded": f"poco relevante (CLIP {o.scores.clip:.2f})"})
            for o in options
        ]
        options.sort(key=lambda o: (o.discarded is not None, o.pass_ != "fine", -o.total))
        result = ShotScores(
            shotId=shot.id, inputsHash=shot_hash[shot.id], needed=round(needed, 3),
            prompts=prompts_for(shot), options=options, notes=notes[shot.id],
        )
        ctx.write_json(f"{OUTPUT}/{shot.id}.json", result.model_dump(by_alias=True, exclude_none=True))
    youtube.close()
    _write_summary(ctx, shots)
    print(f"   Análisis completo en {time.monotonic() - started:.0f} s")


def _write_summary(ctx: RunContext, shots: list[Shot]) -> None:
    usable_fine = no_usable = 0
    discards: dict[str, int] = {}
    for shot in shots:
        scores = ShotScores.model_validate_json((ctx.work_dir / OUTPUT / f"{shot.id}.json").read_text(encoding="utf-8"))
        usable = [o for o in scores.options if o.discarded is None]
        usable_fine += any(o.pass_ == "fine" and o.kind == "video" for o in usable)
        no_usable += not usable
        for option in scores.options:
            if option.discarded:
                reason = option.discarded.split(" (")[0]
                discards[reason] = discards.get(reason, 0) + 1
    summary = {"shots": len(shots), "shotsWithCheckedVideo": usable_fine, "shotsWithoutUsableOption": no_usable,
               "discardReasons": discards}
    ctx.write_json(f"{OUTPUT}/{SUMMARY}", summary)
    print(f"   Planos con fragmento de vídeo verificado: {usable_fine}/{len(shots)} · sin ninguna opción: {no_usable}")
    if discards:
        print("   Descartes: " + ", ".join(f"{k} {v}" for k, v in sorted(discards.items(), key=lambda kv: -kv[1])))


def validate(ctx: RunContext) -> bool:
    shots = [s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots if needs_footage(s)]
    for shot in shots:
        ShotScores.model_validate_json((ctx.work_dir / OUTPUT / f"{shot.id}.json").read_text(encoding="utf-8"))
    json.loads((ctx.work_dir / OUTPUT / SUMMARY).read_text(encoding="utf-8"))
    return True
