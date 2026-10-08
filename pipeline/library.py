"""The library — cache/library/<entity>/library.json: the good sources of every person AND topic, across videos.

Every finished video (after QA) remembers, for each person or topic its shots are about (the planner's entities:
«Booking.com», «CNMC», «París 2024», the protagonist…), the YouTube videos and photos that worked for it:
- the ones on screen (used), and
- the ones analysed as good for a shot but not used (approved: a strong option that lost to a better one).
A source goes to an entity when its title/channel/link names it; one used for a shot about a single entity goes to
that entity anyway (the judge saw it fit). Your «Errores» labels count too: «Correcta» raises a source, a source
marked wrong as a whole (cartoon, watermark) or from a channel you taught it to block never comes back.

The next video naming that person or topic gets the best of them as extra candidates (the event of the shot and how
often they worked rank them): faster sourcing, fewer YouTube searches. The same fragment is never repeated across
videos (judge.used_elsewhere), so what comes back is *other moments* of sources already known to be good.

The analysis thumbnails of each source (its storyboard) are copied into cache/library/_media/, out of reach of the
cache cleanup (cleanup.cache_days), so library sources stay usable for months; the clip itself is downloaded again
only for the new moment. The studio's «Biblioteca» page lists everything and removes what you do not want.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Any

from .context import RunContext
from .schemas import BrollSpec, Candidate, ShotCandidates, ShotsFile
from .sourcing.common import tokens

LIB_DIR = "library"
MEDIA = "_media"                 # cache/library/_media/<source>/: storyboards and photos kept for the library
MAX_SOURCES = 250                # per entity and kind: the least useful go first
APPROVED_PER_SHOT = 2
CLIPS = "_clips"                 # cache/library/_clips/: the clips that went on screen, 720p without sound (~1-2 MB)


def person_key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name.casefold()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "persona"


def _base(root_or_ctx: Any) -> Path:
    if hasattr(root_or_ctx, "cache_dir"):
        return root_or_ctx.cache_dir / LIB_DIR
    root = Path(root_or_ctx)
    try:                                       # the studio: the same cache the videos use (paths.cache)
        return RunContext.create("_biblioteca", root=root).cache_dir / LIB_DIR
    except Exception:
        return root / "cache" / LIB_DIR


def folder(ctx: RunContext, person: str) -> Path:
    return _base(ctx) / person_key(person)


def _load_path(path: Path, name: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    return {**data, "name": data.get("name") or name, "videos": data.get("videos", {}), "photos": data.get("photos", {}),
            "stats": data.get("stats", {}), "kind": data.get("kind") or ("person" if data.get("cutout") else "topic")}


def load(ctx: RunContext, person: str) -> dict[str, Any]:
    return _load_path(folder(ctx, person) / "library.json", person)


def save(ctx: RunContext, person: str, data: dict[str, Any]) -> None:
    _save_path(folder(ctx, person), data)


def _save_path(target: Path, data: dict[str, Any]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / "library.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(target / "library.json")


def names_person(candidate: Candidate, person: str) -> bool:
    name = tokens(person)
    return bool(name) and name <= tokens(f"{candidate.title or ''} {candidate.channel or ''} {candidate.url or ''}")


# --- what a finished video teaches ----------------------------------------------------------------------------

def _keep_media(ctx: RunContext, candidate: Candidate) -> Candidate:
    """The candidate with its storyboard (or photo) copied under cache/library/_media/, safe from the cache cleanup."""

    safe = _base(ctx) / MEDIA / re.sub(r"[^A-Za-z0-9_-]+", "_", candidate.id)
    try:
        if candidate.storyboard is not None:
            sheets = []
            for sheet in candidate.storyboard.sheets:
                source = ctx.root / sheet
                target = safe / Path(sheet).name
                if not target.is_file():
                    if not source.is_file():
                        return candidate
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                sheets.append(str(target.relative_to(ctx.root)))
            return candidate.model_copy(update={"storyboard": candidate.storyboard.model_copy(update={"sheets": sheets})})
        if candidate.imagePath:
            source = ctx.root / candidate.imagePath
            target = safe / Path(candidate.imagePath).name
            if not target.is_file():
                if not source.is_file():
                    return candidate
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            return candidate.model_copy(update={"imagePath": str(target.relative_to(ctx.root))})
    except (OSError, ValueError):
        pass
    return candidate


def _keep_clip(ctx: RunContext, row: dict[str, Any]) -> str | None:
    """The clip of this shot as it went on screen, small (720p, no sound, ≤ 6 s), in cache/library/_clips/."""

    import subprocess

    if row.get("kind") != "video" or not row.get("media"):
        return None
    source = ctx.work_dir / str(row["media"])
    if not source.is_file():
        return None
    start = float(row.get("sourceStart") or 0)
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{row['candidateId']}_{start:.1f}") + ".mp4"
    target = _base(ctx) / CLIPS / name
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        done = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source), "-t", "6", "-an",
                               "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                               "-movflags", "+faststart", str(target)], capture_output=True, timeout=120)
        if done.returncode != 0 or not target.is_file():
            target.unlink(missing_ok=True)
            return None
    return name


def _trim_clips(ctx: RunContext) -> None:
    """library.clips_max_gb (15): above it, the oldest clips go (their sources stay in the library)."""

    folder = _base(ctx) / CLIPS
    if not folder.is_dir():
        return
    cap = float(ctx.section("library").get("clips_max_gb", 15)) * 1e9
    files = sorted(folder.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    for path in files:
        if total <= cap:
            break
        total -= path.stat().st_size
        path.unlink(missing_ok=True)


def _value(stats: dict[str, Any]) -> float:
    return float(stats.get("used", 0)) + 0.5 * float(stats.get("approved", 0)) + 2 * float(stats.get("right", 0))


def _trim(data: dict[str, Any]) -> None:
    for bucket in ("videos", "photos"):
        if len(data[bucket]) > MAX_SOURCES:
            ranked = sorted(data[bucket], key=lambda cid: (-_value(data["stats"].get(cid, {})),
                                                           str(data["stats"].get(cid, {}).get("last") or "")))
            for cid in ranked[MAX_SOURCES:]:
                data[bucket].pop(cid, None)
                data["stats"].pop(cid, None)


def _excluded(root: Path) -> tuple[set[str], set[str]]:
    """Sources marked wrong as a whole, and channels blocked by your labels (pipeline/feedback.py)."""

    try:
        from . import feedback

        whole = {cid for cid, spans in feedback.wrong_fragments(root).items() if (None, None) in spans}
        channels = {name.casefold() for name in feedback.blocked_channels(root)}
        return whole, channels
    except Exception:
        return set(), set()


def remember(ctx: RunContext, rows: list[dict[str, Any]]) -> None:
    """After QA: this video's good sources go to the library of each person or topic they show."""

    story = ShotsFile.model_validate(ctx.read_json("shots.json"))
    person = story.subject.split("·")[0].strip()
    known: dict[str, Candidate] = {}
    for path in (ctx.work_dir / "candidates").glob("s*.json"):
        for c in ShotCandidates.model_validate_json(path.read_text("utf-8")).candidates:
            known[c.id] = c
    used_by_shot: dict[str, set[str]] = {}
    on_screen: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("candidateId") and row.get("decidedBy") not in ("people", "coldopen"):
            base_id = str(row["shotId"]).split("-")[0]
            used_by_shot.setdefault(base_id, set()).add(row["candidateId"])
            on_screen.setdefault((base_id, row["candidateId"]), []).append(row)
    keep_clips = bool(ctx.section("library").get("clips", True))
    clip_names: dict[tuple[str, str], list[str]] = {}

    def clips_of(shot_id: str, cid: str) -> list[str]:
        key = (shot_id, cid)
        if key not in clip_names:
            clip_names[key] = [n for n in (_keep_clip(ctx, r) for r in on_screen.get(key, [])) if n] if keep_clips else []
        return clip_names[key]
    min_score = float(ctx.section("library").get("min_score", 0.35))
    wrong, blocked = _excluded(ctx.root)
    learned: dict[str, dict[str, Any]] = {}            # entity name → its library, loaded once

    def add(entity: str, candidate: Candidate, how: str, clips: list[str] | None = None, text: str = "") -> None:
        if candidate.id in wrong or (candidate.channel or "").casefold() in blocked:
            return
        data = learned.get(entity)
        if data is None:
            data = learned[entity] = load(ctx, entity)
            if entity == person:
                data["kind"] = "person"
        if candidate.id in data.get("removed", []):            # you took it out in the studio
            return
        bucket = "videos" if candidate.source == "youtube" else "photos"
        if candidate.id not in data[bucket]:
            data[bucket][candidate.id] = _keep_media(ctx, candidate).model_dump(exclude_none=True)
        stats = data["stats"].setdefault(candidate.id, {"used": 0, "approved": 0, "right": 0, "videos": []})
        if ctx.slug not in stats["videos"]:
            stats["videos"].append(ctx.slug)
            stats[how] = stats.get(how, 0) + 1
        stats["last"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        for name in clips or []:
            if name not in {c["file"] for c in stats.setdefault("clips", [])}:
                stats["clips"].append({"file": name, "video": ctx.slug, "text": " ".join(text.split())[:160]})

    for shot in story.shots:
        if shot.broll is None:
            continue
        entities = [e for e in dict.fromkeys(shot.broll.entities) if e.strip()]
        if person and person not in entities:
            entities.append(person)
        used = used_by_shot.get(shot.id, set())
        approved: list[str] = []
        scores_path = ctx.work_dir / "scores" / f"{shot.id}.json"
        if scores_path.is_file():
            try:
                options = json.loads(scores_path.read_text("utf-8")).get("options", [])
            except (OSError, ValueError):
                options = []
            for option in options:
                cid = option.get("candidateId")
                if (option.get("discarded") is None and float(option.get("total") or 0) >= min_score and cid not in used
                        and cid not in approved):
                    approved.append(cid)
                if len(approved) >= APPROVED_PER_SHOT:
                    break
        for cid, how in [*((c, "used") for c in used), *((c, "approved") for c in approved)]:
            candidate = known.get(cid)
            if candidate is None or candidate.source == "generated":
                continue
            named = [e for e in entities if names_person(candidate, e)]
            if not named and how == "used" and len(shot.broll.entities) == 1 and shot.broll.entities[0] != person:
                named = list(shot.broll.entities)              # the judge put it on a shot about that topic alone
            clips = clips_of(shot.id, cid) if how == "used" and named else []
            for entity in named:
                add(entity, candidate, how, clips, shot.text)
    if keep_clips:
        _trim_clips(ctx)
    total = 0
    for entity, data in learned.items():
        _trim(data)
        save(ctx, entity, data)
        total += 1
    if learned:
        print(f"   Biblioteca: {total} persona(s)/tema(s) actualizados ("
              + ", ".join(f"{name} {len(d['videos'])}v/{len(d['photos'])}f" for name, d in list(learned.items())[:6])
              + ("…" if len(learned) > 6 else "") + ")")


# --- what the next video gets -----------------------------------------------------------------------------------

def candidates_for(ctx: RunContext, broll: BrollSpec, present: set[str], limit: int = 3) -> list[Candidate]:
    """Library videos of the people and topics a shot names, not already among its candidates. Only those whose
    storyboard is still on disk (analysis needs it); the shot's event, then how well they worked, rank them."""

    out: list[Candidate] = []
    event = tokens(broll.event or "")
    wrong, blocked = _excluded(ctx.root)
    for person in broll.entities:
        data = load(ctx, person)
        pool = []
        for cid, raw in data["videos"].items():
            if cid in present or cid in wrong:
                continue
            try:
                c = Candidate.model_validate(raw)
            except ValueError:
                continue
            if (c.channel or "").casefold() in blocked:
                continue
            if c.storyboard is None or not all((ctx.root / s).is_file() for s in c.storyboard.sheets):
                continue
            overlap = len((event - tokens(person)) & tokens(c.title or ""))
            # a narrated moment (a fall, tears on the podium) only takes a saved clip OF THAT EVENT: any other
            # clip of the person is exactly the «algo de esa persona» that replaced the moment (pati)
            if broll.moment and overlap < 2:
                continue
            pool.append((overlap, _value(data["stats"].get(cid, {})), c))
        pool.sort(key=lambda item: (-item[0], -item[1]))
        for _, _, c in pool[: limit - len(out)]:             # `limit` in all: more would only slow the analysis
            out.append(c.model_copy(update={"query": f"biblioteca: {person}"}))
            present.add(c.id)
        if len(out) >= limit:
            break
    return out


def protect(ctx: RunContext) -> int:
    """Before the cache cleanup: the media of every library source still in cache/videos or cache/images is copied
    to cache/library/_media/ (libraries made before this existed). How many sources it moved."""

    moved = 0
    base = _base(ctx)
    for path in base.glob("*/library.json") if base.is_dir() else []:
        if path.parent.name.startswith("_"):
            continue
        data = _load_path(path, path.parent.name)
        changed = False
        for bucket in ("videos", "photos"):
            for cid, raw in list(data[bucket].items()):
                try:
                    c = Candidate.model_validate(raw)
                except ValueError:
                    continue
                kept = _keep_media(ctx, c)
                if kept is not c and kept != c:
                    data[bucket][cid] = kept.model_dump(exclude_none=True)
                    changed = True
                    moved += 1
        if changed:
            _save_path(path.parent, data)
    return moved


# --- the studio's «Biblioteca» page ---------------------------------------------------------------------------

def overview(root: Path) -> list[dict[str, Any]]:
    """Every person and topic with how much it holds."""

    out = []
    base = _base(root)
    for path in sorted(base.glob("*/library.json")) if base.is_dir() else []:
        if path.parent.name.startswith("_"):
            continue
        data = _load_path(path, path.parent.name)
        stats = data["stats"].values()
        out.append({"key": path.parent.name, "name": data["name"], "kind": data["kind"], "videos": len(data["videos"]),
                    "photos": len(data["photos"]), "cutout": bool(data.get("cutout")),
                    "inVideos": len({v for s in stats for v in s.get("videos", [])}),
                    "last": max((str(s.get("last") or "") for s in stats), default="")})
    return sorted(out, key=lambda e: (-(e["videos"] + e["photos"]), e["name"].casefold()))


def entity(root: Path, key: str) -> dict[str, Any]:
    path = _base(root) / key / "library.json"
    if not path.is_file() or "/" in key or key.startswith((".", "_")):
        raise FileNotFoundError(key)
    data = _load_path(path, key)
    sources = []
    for bucket in ("videos", "photos"):
        for cid, raw in data[bucket].items():
            stats = data["stats"].get(cid, {})
            clip_dir = _base(root) / CLIPS
            clips = [c for c in stats.get("clips", []) if (clip_dir / c["file"]).is_file()]
            sources.append({"id": cid, "kind": bucket, "title": raw.get("title") or "", "channel": raw.get("channel") or "",
                            "clips": clips,
                            "url": raw.get("url") or "", "used": stats.get("used", 0), "approved": stats.get("approved", 0),
                            "right": stats.get("right", 0), "videos": stats.get("videos", []), "last": stats.get("last") or "",
                            "preview": bool((raw.get("storyboard") or {}).get("sheets") or raw.get("imagePath"))})
    sources.sort(key=lambda s: (-_value(s), s["title"]))
    return {"key": key, "name": data["name"], "kind": data["kind"], "sources": sources}


def preview(root: Path, key: str, cid: str) -> Path | None:
    data = _load_path(_base(root) / key / "library.json", key)
    raw = data["videos"].get(cid) or data["photos"].get(cid)
    if not raw:
        return None
    sheets = (raw.get("storyboard") or {}).get("sheets") or []
    path = root / (sheets[0] if sheets else raw.get("imagePath") or "")
    return path if path.is_file() else None


def clip_file(root: Path, name: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.mp4", name):
        return None
    path = _base(root) / CLIPS / name
    return path if path.is_file() else None


def remove(root: Path, key: str, cid: str | None = None) -> None:
    """One source out of a person/topic (never offered again for it), or the whole person/topic with cid None."""

    target = _base(root) / key
    if "/" in key or key.startswith((".", "_")) or not (target / "library.json").is_file():
        raise FileNotFoundError(key)
    if cid is None:
        shutil.rmtree(target)
        return
    data = _load_path(target / "library.json", key)
    for bucket in ("videos", "photos"):
        data[bucket].pop(cid, None)
    data["stats"].pop(cid, None)
    data.setdefault("removed", [])
    if cid not in data["removed"]:
        data["removed"].append(cid)
    _save_path(target, data)


def mark_right(root: Path, candidate_id: str) -> int:
    """«Correcta» in Errores: the source counts double in every person/topic that holds it. How many it touched."""

    touched = 0
    base = _base(root)
    for path in base.glob("*/library.json") if base.is_dir() else []:
        data = _load_path(path, path.parent.name)
        if candidate_id in data["videos"] or candidate_id in data["photos"]:
            stats = data["stats"].setdefault(candidate_id, {"used": 0, "approved": 0, "right": 0, "videos": []})
            stats["right"] = stats.get("right", 0) + 1
            _save_path(path.parent, data)
            touched += 1
    return touched
