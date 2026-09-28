"""Per-athlete library — cache/library/<person>/library.json (+ cutout.png).

Every finished video remembers, for each person it was about, the YouTube videos and photos of
that person it used (the full Candidate, storyboard included) and the person's cutout. The next
video about the same person gets those sources as extra candidates, so it finds good footage
faster and more reliably — and, because the cross-video registry (judge.used_elsewhere) forbids
reusing the same fragments, it draws *other moments* of them.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .context import RunContext
from .schemas import BrollSpec, Candidate, ShotCandidates, ShotsFile
from .sourcing.common import tokens

LIB_DIR = "library"


def person_key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name.casefold()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "persona"


def folder(ctx: RunContext, person: str) -> Path:
    return ctx.cache_dir / LIB_DIR / person_key(person)


def load(ctx: RunContext, person: str) -> dict[str, Any]:
    path = folder(ctx, person) / "library.json"
    try:
        data = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    return {"name": person, "videos": data.get("videos", {}), "photos": data.get("photos", {}),
            **({"cutout": data["cutout"]} if data.get("cutout") else {})}


def save(ctx: RunContext, person: str, data: dict[str, Any]) -> None:
    target = folder(ctx, person)
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / "library.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(target / "library.json")


def names_person(candidate: Candidate, person: str) -> bool:
    name = tokens(person)
    return bool(name) and name <= tokens(f"{candidate.title or ''} {candidate.channel or ''} {candidate.url or ''}")


def remember(ctx: RunContext, rows: list[dict[str, Any]]) -> None:
    """After QA: add this video's on-screen sources that name the protagonist to their library."""

    story = ShotsFile.model_validate(ctx.read_json("shots.json"))
    person = story.subject.split("·")[0].strip()
    if not person:
        return
    known: dict[str, Candidate] = {}
    for path in (ctx.work_dir / "candidates").glob("s*.json"):
        for c in ShotCandidates.model_validate_json(path.read_text("utf-8")).candidates:
            known[c.id] = c
    used = {r["candidateId"] for r in rows if r.get("candidateId")}
    data = load(ctx, person)
    added = 0
    for cid in used:
        c = known.get(cid)
        if c is None or not names_person(c, person):
            continue
        bucket = "videos" if c.source == "youtube" else "photos"
        if cid not in data[bucket]:
            data[bucket][cid] = c.model_dump(exclude_none=True)
            added += 1
    if added:
        save(ctx, person, data)
        print(f"   Biblioteca de {person}: +{added} fuentes ({len(data['videos'])} vídeos, {len(data['photos'])} fotos)")


def candidates_for(ctx: RunContext, broll: BrollSpec, present: set[str], limit: int = 3) -> list[Candidate]:
    """Library videos of the people a shot names, not already among its candidates. Only those whose
    storyboard is still on disk (analysis needs it); the event of the shot ranks them."""

    out: list[Candidate] = []
    event = tokens(broll.event or "")
    for person in broll.entities:
        data = load(ctx, person)
        pool = []
        for cid, raw in data["videos"].items():
            if cid in present:
                continue
            try:
                c = Candidate.model_validate(raw)
            except ValueError:
                continue
            if c.storyboard is None or not all((ctx.root / s).is_file() for s in c.storyboard.sheets):
                continue
            pool.append((len(event & tokens(c.title or "")), c))
        pool.sort(key=lambda pair: -pair[0])
        for _, c in pool[:limit]:
            out.append(c.model_copy(update={"query": f"biblioteca: {person}"}))
            present.add(c.id)
    return out
