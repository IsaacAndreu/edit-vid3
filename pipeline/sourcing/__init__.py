"""Stage 3 — find candidate footage and images for every shot that shows footage.

Writes work/<slug>/candidates/<shot_id>.json (+ _summary.json). Per-shot files are
reused when the shot's search spec and the sourcing config are unchanged, so an
interrupted run resumes where it stopped.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import ValidationError

from ..context import RunContext
from ..schemas import Shot, ShotCandidates, ShotsFile
from .common import SourceUnavailable, key
from .images import ImageSources
from .youtube import YouTubeSource


STAGE = "sourcing"
OUTPUT = "candidates"
SUMMARY = "_summary.json"


def needs_footage(shot: Shot) -> bool:
    return shot.broll is not None and shot.type in ("broll", "chapter", "split", "stat")


def _spec_hash(shot: Shot, cfg: dict[str, Any]) -> str:
    return key(shot.broll.model_dump() if shot.broll else None, cfg)


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "shots.json"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("sourcing")
    shots = [s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots if needs_footage(s)]
    out_dir = ctx.work_dir / OUTPUT
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = {f"{s.id}.json" for s in shots} | {SUMMARY}
    for stale in out_dir.glob("*.json"):
        if stale.name not in wanted:
            stale.unlink()

    yt_cfg = cfg.get("youtube", {})
    youtube = YouTubeSource(root=ctx.root, cache_dir=ctx.cache_dir, config=yt_cfg) if yt_cfg.get("enabled", True) else None
    images = ImageSources(
        root=ctx.root,
        cache_dir=ctx.cache_dir,
        config=cfg.get("images", {}),
        pixabay_key=ctx.env("PIXABAY_API_KEY", required=False),
    )

    def process(shot: Shot) -> ShotCandidates:
        spec_hash = _spec_hash(shot, cfg)
        path = out_dir / f"{shot.id}.json"
        if path.is_file():
            try:
                existing = ShotCandidates.model_validate_json(path.read_text(encoding="utf-8"))
                if existing.specHash == spec_hash and not any("bloquea" in n for n in existing.notes):
                    return existing
            except (ValidationError, ValueError):
                pass
        notes: list[str] = []
        queries: dict[str, list[str]] = {}
        candidates = []
        if youtube is not None:
            queries["youtube"] = youtube.queries_for(shot.broll)
            try:
                candidates += youtube.candidates(shot.broll, notes)
            except SourceUnavailable as error:
                notes.append(str(error))
        image_queries, image_candidates = images.search(shot.broll, notes)
        queries.update(image_queries)
        candidates += image_candidates
        result = ShotCandidates(shotId=shot.id, specHash=spec_hash, queries=queries, candidates=candidates, notes=notes)
        ctx.write_json(f"{OUTPUT}/{shot.id}.json", result.model_dump(exclude_none=True))
        counts = {}
        for c in candidates:
            counts[c.source] = counts.get(c.source, 0) + 1
        print(f"   {shot.id}: " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "sin candidatos"))
        return result

    with ThreadPoolExecutor(max_workers=int(cfg.get("parallel", 3))) as pool:
        results = list(pool.map(process, shots))

    by_source: dict[str, int] = {}
    empty = []
    for result in results:
        if not result.candidates:
            empty.append(result.shotId)
        for candidate in result.candidates:
            by_source[candidate.source] = by_source.get(candidate.source, 0) + 1
    notes = sorted({n for r in results for n in r.notes if "bloquea" in n or "desactivado" in n})
    summary = {
        "shots": len(results),
        "candidatesBySource": by_source,
        "shotsWithYouTube": sum(any(c.source == "youtube" for c in r.candidates) for r in results),
        "shotsWithoutCandidates": empty,
        "warnings": notes,
    }
    ctx.write_json(f"{OUTPUT}/{SUMMARY}", summary)
    print(f"   {len(results)} planos con metraje · candidatos: {json.dumps(by_source)}")
    print(f"   Planos con YouTube: {summary['shotsWithYouTube']} · sin ningún candidato: {len(empty)}")
    for warning in notes:
        print(f"   AVISO: {warning}")


def validate(ctx: RunContext) -> bool:
    shots = [s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots if needs_footage(s)]
    for shot in shots:
        ShotCandidates.model_validate_json((ctx.work_dir / OUTPUT / f"{shot.id}.json").read_text(encoding="utf-8"))
    json.loads((ctx.work_dir / OUTPUT / SUMMARY).read_text(encoding="utf-8"))
    return True


def retry_if(ctx: RunContext) -> bool:
    """Re-run automatically while YouTube was blocked (e.g. when the project later runs locally)."""

    if not ctx.section("sourcing").get("youtube", {}).get("enabled", True):
        return False
    summary = json.loads((ctx.work_dir / OUTPUT / SUMMARY).read_text(encoding="utf-8"))
    return any("bloquea" in warning for warning in summary.get("warnings", []))
