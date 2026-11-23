"""Stage 7 — cover the shots that still have no media: work/<slug>/fallback.json.

Pending shots are those the judge rejected everything for (selection status "fallback") and
those whose chosen clip could not be ingested (e.g. YouTube 403, Commons rate limit).
For each, in order:

1. next option (only after a failed download): the next usable, non-repeated option from
   stage 4's ranking — the shot's options were fine, only the download failed;
2. Pexels video, then Pexels photo — candidates scored with CLIP against the shot;
3. an image generated with GPT Image (last resort; cost logged).

Media goes to work/<slug>/media_fallback/ (stage 6 owns media/), and the timeline merges
selection + ingest + fallback. Each file has one writer, so re-running any stage is safe.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

from .analysis import detectors as det
from . import library
from .analysis import make_models, prompts_for
from .context import RunContext
from .costs import record_cost
from .ingest import MANIFEST, Materialiser, find_lut, normalise_image, normalise_video, probe
from . import feedback
from .material import chosen_material
from .judge import (LETTERS, call_judge, contact_sheet, is_repeat, overused, own_event, ranked, seen_elsewhere, source_cap,
                    source_lines,
                    surrounding, used_elsewhere)
from . import tope
from .schemas import (
    Candidate,
    FallbackFile,
    FallbackItem,
    IngestFile,
    Option,
    Selection,
    SelectionFile,
    Shot,
    ShotCandidates,
    ShotScores,
    ShotsFile,
)
from .content_check import ContentCheck
from .identity import Checker, IdentityCache, expected_people
from .sourcing.images import watermarked
from .sourcing import hypothetical, needs_footage, youtube_source
from .sourcing.common import USER_AGENT, blocked_by_title, cached_json, http_get_json, key, tokens
from .sourcing.images import ImageSources, image_query


STAGE = "fallback"
OUTPUT = "fallback.json"
MEDIA_DIR = "media_fallback"
VERSION = 7  # bump when the fallback policy changes: invalidates per-shot results
PEXELS = "https://api.pexels.com"


# --- Pexels ------------------------------------------------------------------------------


def pexels_search(ctx: RunContext, kind: str, query: str, http: requests.Session) -> list[dict[str, Any]]:
    path = "/videos/search" if kind == "video" else "/v1/search"
    params = {"query": query, "orientation": "landscape", "per_page": 12}
    payload = cached_json(
        ctx.cache_dir / "search" / f"pexels-{kind}" / f"{key(params)}.json",
        lambda: http_get_json(http, PEXELS + path, params=params, headers={"Authorization": ctx.env("PEXELS_API_KEY")}),
    )
    return payload.get("videos" if kind == "video" else "photos", [])


def _download(http: requests.Session, url: str, target: Path) -> Path:
    if not target.is_file():
        response = http.get(url, timeout=120)
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
    return target


def _judged_stock(ctx: RunContext, shot: Any, good: list[tuple[float, dict[str, Any]]], kind: str, story: Any,
                  tried: list[str]) -> list[tuple[float, dict[str, Any]]]:
    """The Pexels results CLIP liked, shown to the vision judge (their poster frames): only those it accepts, in its
    order. A judge error keeps nothing (the shot goes on to the next step), never CLIP's choice unseen."""

    options, candidates = [], {}
    for _, result in good:
        rid = f"px{kind[0]}:{result['id']}"
        if not result.get("_thumb"):
            continue
        # the judge sees its poster frame: that is the candidate's local image (without it the schema refused every
        # one — «1 validation error for Candidate» in 9 shots of newgym5, their stock never judged)
        candidates[rid] = Candidate(id=rid, source="pexels", kind="image", url=str(result.get("url") or "u"),
                                    title=str(result.get("alt") or result.get("url") or "Pexels"), channel="Pexels",
                                    license="pexels", credit="Fuente: Pexels", attribution="Pexels", query="pexels",
                                    rankScore=0.0, imagePath=str(result["_thumb"]))
        options.append(Option.model_validate({"candidateId": rid, "source": "pexels", "kind": "image", "pass": "coarse",
                                              "analysisPath": result.get("_thumb"), "scores": {"clip": 0.0}, "total": 0.0}))
    judge_cfg = ctx.section("judge")
    try:
        sheet = contact_sheet(options, candidates, ctx.root, frames=1, tile_width=int(judge_cfg.get("tile_width", 320)))
        verdict = call_judge(ctx, shot, sheet, LETTERS[: len(options)], story.context or story.title, False, story.subject,
                             source_lines(options, candidates), around=surrounding(story.shots, shot.id))
    except Exception as error:
        tried.append(f"pexels {kind}: el juez no respondió ({str(error)[:80]})")
        return []
    by_letter = dict(zip(LETTERS, good))
    accepted = [by_letter[letter] for letter in verdict.get("ranking") or [] if letter in by_letter]
    if not accepted:
        tried.append(f"pexels {kind}: el juez las rechazó ({str(verdict.get('reason', ''))[:100]})")
    return accepted


def _thumbnail(http: requests.Session, url: str, cache: Path) -> np.ndarray | None:
    try:
        path = _download(http, url, cache / f"{key(url)}.jpg")
    except requests.RequestException:
        return None
    return cv2.imread(str(path))


# --- stage -------------------------------------------------------------------------------


def inputs(ctx: RunContext) -> list:
    # people.json: the portraits the identity check compares faces with (the people stage runs first)
    # revision.json: the shots marked wrong in the studio («Errores»), replaced here
    revision = ctx.work_dir / feedback.REVISION
    auto = ctx.work_dir / feedback.REVISION_AUTO          # the automatic reviewer's (pipeline/revisor.py)
    return [ctx.work_dir / "selection.json", ctx.work_dir / "media" / MANIFEST, ctx.work_dir / "shots.json",
            ctx.work_dir / "people.json"] + [p for p in (revision, auto) if p.is_file()]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("fallback")
    started = time.monotonic()
    out_dir = ctx.work_dir / MEDIA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    story = ShotsFile.model_validate(ctx.read_json("shots.json"))
    shots = {s.id: s for s in story.shots if needs_footage(s)}
    # a story about real people — one protagonist, or several (a ranking of scandals: Chiles, Nemov, Hamm…): never
    # anonymous stock nor a generated picture of what happened; with nothing real left the shot becomes a card
    try:
        named = (json.loads((ctx.work_dir / "people.json").read_text("utf-8")) or {}).get("people") or []
    except (OSError, ValueError):
        named = []
    real_people = bool(story.subject) or bool(named)
    selections = {s.shotId: s for s in SelectionFile.model_validate(ctx.read_json("selection.json")).selections}
    ingest = IngestFile.model_validate_json((ctx.work_dir / "media" / MANIFEST).read_text("utf-8"))
    done = {m.shotId for m in ingest.media}
    max_hamming = int(ctx.section("judge").get("max_phash_distance", 6))
    # fallback.repeat_frames (off: the look-alikes it sends back are searched again): two frames of every clip, at 30 %
    # and 70 %, compared like the revisor does — the middle frame alone missed half of newgym3-ideas2's «Repetido»
    repeat_frames = bool(cfg.get("repeat_frames", False))
    frames = (lambda path, kind: det.clip_dhashes(str(path), kind)) if repeat_frames else (lambda path, kind: [])

    # The judge compares fragments before download; different uploads of the same broadcast can
    # still end up on screen twice. Check the downloaded media exactly like QA does (middle frame)
    # and send any later look-alike here for a replacement.
    pending: dict[str, str] = {}
    seen: list[tuple[str, str]] = []
    seen_frames: list[tuple[str, list[int]]] = []
    for media in sorted(ingest.media, key=lambda m: list(shots).index(m.shotId) if m.shotId in shots else 10**6):
        h = _frame_hash(ctx.root / media.path, media.kind) if (ctx.root / media.path).is_file() else None
        if h is None:
            continue
        mine = frames(ctx.root / media.path, media.kind)
        twin = next((sid for sid, other in seen if det.hamming(h, other) <= max_hamming), None) or next(
            (sid for sid, other in seen_frames if sid.split("-")[0] != media.shotId.split("-")[0]
             and det.near_frames(mine, other)), None)
        chosen_by_hand = getattr(selections.get(media.shotId), "decidedBy", None) == "editor"
        if twin and not chosen_by_hand:                  # what you pick in the editor stays, repeated or not
            done.discard(media.shotId)
            pending[media.shotId] = f"repite la imagen de {twin}"
        else:
            seen.append((media.shotId, h))
            seen_frames.append((media.shotId, mine))

    # Is the athlete on screen the one the script names? On-screen captions and, in clear cases, faces.
    people_file = ctx.read_json("people.json") if (ctx.work_dir / "people.json").is_file() else {}
    # named people without a photo too (no face to compare): with fallback.unknown_faces: reject, a big face in a shot
    # that names them cannot be verified and goes
    people = [*(people_file.get("people") or []), *({"name": n} for n in people_file.get("unseen") or [])]
    from .people import looks_like_person

    def a_person(name: str) -> bool:   # «AIFA» (mega17) is an airport: «a woman, not AIFA» threw good clips away
        return looks_like_person(name) and not (len(name.split()) == 1 and name.isupper())

    names = [n for n in ([p["name"] for p in people if p.get("name")]
                         or ([story.subject.split("·")[0].strip()] if story.subject else [])) if a_person(n)]
    checker = Checker(ctx, people) if names and (cfg.get("caption_check", True) or cfg.get("face_check", True)) else None
    identity_cache = IdentityCache(ctx)

    protagonist = story.subject.split("·")[0].strip() if story.subject else ""
    protagonist = protagonist if a_person(protagonist) else ""
    scope = str(cfg.get("identity_scope", "protagonist"))

    content = ContentCheck(ctx)

    def wrong_person(shot_id: str, path: Path, kind: str) -> str | None:
        """Why this media cannot go in this shot: a cartoon or broken video (whatever the shot), or another person."""

        if why := content.verdict(path, kind, shots[shot_id].text if shot_id in shots else ""):
            return why
        who = expected_people(shots[shot_id], names, protagonist, scope) if checker and shot_id in shots else []
        return identity_cache.get(checker, path, kind, who) if who else None

    from .decisions import approved_fragments

    approved = approved_fragments(ctx.root)
    marked_wrong = feedback.wrong_shots(ctx.work_dir)    # you said so in the studio: replace, whoever chose it
    # the clips marked wrong for this video (by you or by the reviewer): never chosen again for any of its shots
    from types import SimpleNamespace

    rejected = [SimpleNamespace(candidateId=v.get("candidateId"), start=v.get("start"), end=v.get("end"))
                for v in feedback.wrong_details(ctx.work_dir).values() if v.get("candidateId") and v.get("start") is not None]
    for shot_id, why in marked_wrong.items():
        if shot_id in shots and shot_id in done:
            done.discard(shot_id)
            pending[shot_id] = f"marcado como error en la revisión: {why}"
    for media in ingest.media:
        if media.shotId not in done or getattr(selections.get(media.shotId), "decidedBy", None) == "editor":
            continue
        chosen = selections.get(media.shotId)
        if media.kind == "image" and chosen and watermarked(f"{chosen.url or ''} {chosen.mediaUrl or ''} {chosen.credit or ''}"):
            done.discard(media.shotId)
            pending[media.shotId] = "foto de agencia con marca de agua"
            print(f"   {media.shotId}: foto de agencia con marca de agua ({(chosen.credit or '').removeprefix('Fuente: ')})")
            continue
        if chosen and chosen.candidateId and feedback.is_wrong(approved, chosen.candidateId, chosen.start, chosen.end):
            continue                                     # you said this clip is right («Decisiones del relleno»)
        why = wrong_person(media.shotId, ctx.root / media.path, media.kind)
        if why:
            done.discard(media.shotId)
            pending[media.shotId] = why
            print(f"   {media.shotId}: {why}")

    for shot_id in shots:
        if shot_id in done or shot_id in pending:
            continue
        selection = selections.get(shot_id)
        if selection is None or selection.status == "fallback":
            pending[shot_id] = "el juez no aceptó ninguna opción" if selection and selection.judge else "sin opciones utilizables"
        else:
            pending[shot_id] = f"descarga fallida: {ingest.failed.get(shot_id, '?')[:120]}"
    print(f"   {len(pending)} planos pendientes")

    previous: dict[str, FallbackItem] = {}
    if (ctx.work_dir / OUTPUT).is_file():
        try:
            previous = {i.shotId: i for i in FallbackFile.model_validate(ctx.read_json(OUTPUT)).items}
        except ValueError:
            previous = {}

    # Everything already on screen, so nothing is repeated.
    used: list[Selection] = [s for s in selections.values() if s.status == "selected" and s.shotId in done]
    pexels_used: set[str] = set()  # media taken by fallback items in this run (cached or new): never twice
    elsewhere = used_elsewhere(ctx)  # what other videos of the channel already showed
    # Hashes of everything on screen: the same stock clip is often re-uploaded to YouTube.
    on_screen: list[str] = [h for sid, h in seen if sid in done] + [s.phash for s in used if s.phash]

    frames_on_screen: list[int] = [x for sid, mine in seen_frames if sid in done for x in mine]

    def looks_used(path: Path, kind: str) -> bool:
        h = _frame_hash(path, kind)
        if h is not None and any(det.hamming(h, other) <= max_hamming for other in on_screen):
            return True
        return repeat_frames and det.near_frames(frames(path, kind), frames_on_screen)

    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    youtube = youtube_source(ctx)
    from . import sin_youtube

    offline = sin_youtube.active()
    lut = find_lut(ctx)
    materialiser = Materialiser(ctx, ctx.section("ingest"), lut, youtube, http)
    clip = None
    items: list[FallbackItem] = []
    unresolved: dict[str, str] = {}

    todo: list[tuple[str, str]] = []
    for shot_id, reason in pending.items():
        shot = shots[shot_id]
        usual = digest = key(VERSION, reason, shot.model_dump(), cfg, lut.name if lut else None)
        if offline:          # chosen without YouTube's options: its own result, looked at again once YouTube is back
            digest = key(usual, sin_youtube.NOTE)
        old = previous.get(shot_id)
        # Reuse the cached result unless a shot earlier in this run has already taken that media.
        if (old and old.specHash in (digest, usual) and (ctx.root / old.path).is_file() and old.candidateId not in pexels_used
                and shot_id not in marked_wrong and not feedback.is_wrong(elsewhere, old.candidateId, old.start, old.end)
                and not same_stretch(old.candidateId, old.start, old.end, used, tope.seconds(ctx))
                and not looks_used(ctx.root / old.path, old.kind)):
            items.append(old)
            # on screen like any other pick: newgym3-ideas2 had 5 pairs with the same seconds of one source, a kept
            # item and a shot searched again beside it (the middle-frame hash misses 0.1 s apart in a routine)
            used.append(reused_selection(old))
            pexels_used.add(old.candidateId)
            if h := _frame_hash(ctx.root / old.path, old.kind):
                on_screen.append(h)
            frames_on_screen.extend(frames(ctx.root / old.path, old.kind))
            continue
        todo.append((shot_id, reason))

    # The pending shots at once (`fallback.parallel`): almost all the time is waiting on YouTube, the web and the
    # vision judge. What must stay in order is guarded: taking a clip (nothing twice on screen) and the identity
    # check (face/CLIP models and identity.json, one at a time).
    claim = threading.Lock()
    identity_lock = threading.Lock()
    research_lock = threading.Lock()              # one second search at a time: it loads CLIP and downloads
    research_left = [int(cfg.get("research_max", 12))]
    # with YouTube slow (5 s a query, 0.09 MB/s) a second search took minutes and the other workers queued behind
    # it: mega2 spent 2.5 h here. Now a shot waits at most a minute for its turn, and none start after 20 min.
    research_until = time.monotonic() + 60 * float(cfg.get("research_minutes", 20))
    # one second search per story event: its finds serve every shot of that event (event_pool reads them), so the
    # twenty minutes reach more events instead of ten searches for ten shots of the same final
    researched: set[str] = set()
    judge_cfg = ctx.section("judge")              # research() reads it too (it was only defined inside resolve())

    def research(shot: Any, reason: str, tried: list[str]) -> tuple[list[Option], dict[str, Candidate]]:
        """New queries for a shot nothing fitted, searched, analysed in work/<slug>/research/ (never the stage
        files of sourcing/analysis) and ranked; the judge vets them in vet_and_materialise."""

        from .analysis import analyse
        from .llm import complete_json

        event = " ".join(sorted(tokens(shot.broll.event))) if shot.broll.event else ""
        if event and event in researched:      # a sibling searched already: what it found, minus what was rejected
            pool, pool_candidates = event_pool(ctx, story, shot, research=True)
            tried.append("segunda búsqueda: ya hecha en este tramo")
            return pool, pool_candidates
        if time.monotonic() > research_until or not research_lock.acquire(timeout=60):
            tried.append("segunda búsqueda: sin tiempo")
            return [], {}
        try:
            if event and event in researched:  # done while this one waited for its turn
                return event_pool(ctx, story, shot, research=True)
            if event:
                researched.add(event)
            if research_left[0] <= 0 or time.monotonic() > research_until:
                return [], {}
            research_left[0] -= 1
            try:
                old = ShotCandidates.model_validate_json((ctx.work_dir / "candidates" / f"{shot.id}.json").read_text("utf-8"))
                asked = sorted({q for qs in old.queries.values() for q in qs})
            except (OSError, ValueError):
                old, asked = None, list(shot.broll.queries)
            try:
                result = complete_json(
                    ctx, stage=STAGE, section="planner", max_tokens=400, system=RESEARCH_SYSTEM,
                    user=f"VÍDEO: {story.title} · {story.context}\nPROTAGONISTA: {story.subject or '—'}\n"
                         f"TRAMO: {shot.broll.event or '—'}\nFRASE: {shot.text}\nQUÉ DEBE VERSE: {shot.broll.visualIntent}\n"
                         + (f"MOMENTO EXACTO (tiene que verse esa acción): {shot.broll.moment}\n" if shot.broll.moment else "")
                         + f"BÚSQUEDAS YA HECHAS: {'; '.join(asked)}\nPOR QUÉ NO SIRVIÓ: {reason[:300]}")
            except Exception as error:
                tried.append(f"segunda búsqueda: {str(error)[:80]}")
                return [], {}
            queries = [str(q).strip() for q in (result.get("queries") or []) if str(q).strip() and str(q).strip() not in asked][:3]
            if not queries:
                return [], {}
            spec = shot.broll.model_copy(update={"queries": [*queries, *shot.broll.queries][:5], "queriesLocal": shot.broll.queriesLocal[:1]})
            notes: list[str] = []
            try:
                seen = {o.id for o in old.candidates} if old else set()
                found = [c for c in youtube.candidates(shot.broll.model_copy(update={"queries": queries, "queriesLocal": []}), notes)
                         if c.id not in seen]
            except Exception as error:
                tried.append(f"segunda búsqueda: {str(error)[:80]}")
                return [], {}
            if not found:
                tried.append(f"segunda búsqueda ({'; '.join(queries)}): nada nuevo")
                return [], {}
            folder = f"research/{shot.id}"
            ctx.write_json(f"{folder}/candidates/{shot.id}.json", ShotCandidates(
                shotId=shot.id, specHash=key(queries), queries={"youtube": queries}, candidates=found,
                notes=notes).model_dump(exclude_none=True))
            analyse(ctx, shots=[shot.model_copy(update={"broll": spec})], candidates_folder=f"{folder}/candidates",
                    folder=f"{folder}/scores")
            scores = ShotScores.model_validate_json((ctx.work_dir / folder / "scores" / f"{shot.id}.json").read_text("utf-8"))
            print(f"   {shot.id}: segunda búsqueda ({'; '.join(queries)}): {len(found)} vídeos nuevos")
            by_id = {c.id: c for c in found}
            options = [o for total, o in ranked(scores.options, judge_cfg.get("source_bonus", {"youtube": 0.02}))
                       if total >= float(judge_cfg.get("min_accept", 0.22)) and o.candidateId in by_id]
            return options, by_id
        finally:
            research_lock.release()
    models_lock = threading.Lock()
    committed: set[str] = set()
    # options that already failed in another shot (download error, picture already on screen): never sent to the
    # judge again — avion9 spent its three slots on the same broken photo in ten shots and lost the good ones
    dead: set[str] = set()
    # what the judge already turned down for a shot of the same story event: not shown to it again for the next
    # shot of that event (pati1.2 sent the same Midori Ito clips to the judge for fifteen Sochi shots)
    turned_down: dict[str, set[str]] = {}
    turned_lock = threading.Lock()
    # a source whose fragments keep failing the identity or content check (another athlete's name on screen, a man in a
    # woman's story): after `fallback.source_strikes` (2) such failures it is out for the rest of the video, before the
    # judge and the download (gym4.0 checked the same team-final video ~25 times: «GUYING, CHOU, not CHUSOVITINA»)
    strikes: dict[str, int] = {}
    max_strikes = int(cfg.get("source_strikes", 2))

    candidate_index: dict[str, Candidate] = {}

    def known_candidate(candidate_id: str) -> Candidate | None:
        """A candidate of any shot of this video (work/<slug>/candidates/), read once."""

        if not candidate_index:
            for path in sorted((ctx.work_dir / "candidates").glob("*.json")):
                try:
                    for c in ShotCandidates.model_validate_json(path.read_text("utf-8")).candidates:
                        candidate_index.setdefault(c.id, c)
                except (OSError, ValueError):
                    continue
        return candidate_index.get(candidate_id)

    def resolve(shot_id: str, reason: str) -> tuple[FallbackItem | None, list[str]]:
        nonlocal clip
        shot = shots[shot_id]
        event_key = " ".join(sorted(tokens(shot.broll.event))) if shot.broll and shot.broll.event else ""
        needed = min(shot.duration, tope.seconds(ctx))
        digest = key(VERSION, reason, shot.model_dump(), cfg, lut.name if lut else None)
        if offline:
            digest = key(digest, sin_youtube.NOTE)
        item: FallbackItem | None = None
        tried: list[str] = []
        idea_kind = shot.idea.kind if shot.idea is not None else None      # planner.ideas: literal / ambiente
        same_idea = {s.id for s in story.shots if shot.idea is not None and s.idea is not None
                     and s.idea.id == shot.idea.id}          # its own idea's uses of a source do not count
        # bloque 2.7: in the first seconds of a video planned by ideas nothing goes on screen unseen by the judge
        in_hook = idea_kind is not None and shot.start < float(judge_cfg.get("hook_seconds", 30))
        # bloque 2.4 (fallback.concept_stock, off): an ambient idea with no image of its own may take faceless concept
        # stock (hands, objects, places) written by the planner, always shown to the judge first
        concept = (shot.idea.concept if cfg.get("concept_stock", False) and idea_kind == "ambiente"
                   and shot.idea is not None else None)

        def vet_and_materialise(options: list[Option], candidates: dict[str, Candidate], method: str,
                                vet: bool = True, judged: bool | None = None, exempt: str | None = None) -> FallbackItem | None:
            """Nobody has looked at these yet: the vision judge vets them (unless `vet` is off), then the first
            that downloads (and passes the identity check) wins. `exempt`: the shot whose clip this one continues
            on purpose (its seconds touch, they never overlap): not counted as already on screen."""

            vet = vet or in_hook
            others = [u for u in used if u.shotId != exempt] if exempt else used
            # whatever pool they come from: never a blocked source, never a source already on screen too often
            per_source = source_cap(judge_cfg, len(story.shots) * 2 // 3)   # about the footage shots
            blocklist = ctx.section("content").get("title_blocklist")
            official = ctx.section("content").get("official_channels")
            options = [o for o in options
                       if not same_stretch(o.candidateId, o.start, o.end, others, needed)     # those seconds already on screen
                       and not same_stretch(o.candidateId, o.start, o.end, rejected, needed)   # marked wrong here
                       and not (offline and candidates[o.candidateId].source == "youtube")   # cannot come without YouTube
                       and (chosen_material(candidates[o.candidateId])
                            or not blocked_by_title(candidates[o.candidateId].title, candidates[o.candidateId].channel,
                                                    blocklist, official))
                       and not overused(o.candidateId, [u for u in used if u.shotId not in same_idea],
                                        per_source * (2 if own_event(candidates[o.candidateId].title, shot) else 1))
                       and f"{o.candidateId}@{o.start}" not in dead
                       and not (max_strikes and strikes.get(o.candidateId, 0) >= max_strikes)
                       and not (vet and event_key and f"{o.candidateId}@{o.start}" in turned_down.get(event_key, ()))]
            if not options:
                return None
            if vet:
                sheet = contact_sheet(options, candidates, ctx.root, frames=int(judge_cfg.get("frames_per_candidate", 3)),
                                      tile_width=int(judge_cfg.get("tile_width", 320)))
                verdict = call_judge(ctx, shot, sheet, LETTERS[: len(options)],
                                     story.context or story.title, False, story.subject, source_lines(options, candidates),
                                     around=surrounding(story.shots, shot.id))
                by_letter = dict(zip(LETTERS, options))
                accepted = [by_letter[letter] for letter in verdict["ranking"] if letter in by_letter]
                if event_key:
                    with turned_lock:
                        turned_down.setdefault(event_key, set()).update(
                            f"{o.candidateId}@{o.start}" for o in options if o not in accepted)
            else:
                accepted = list(options)
            if not accepted:
                tried.append(f"{method}: el juez las rechazó ({verdict.get('reason', '')[:100]})")
            for option in accepted:
                c = candidates[option.candidateId]
                selection = Selection(
                    shotId=shot_id, status="selected", decidedBy="score", candidateId=c.id, source=c.source,
                    kind=option.kind, start=option.start, end=option.end, mediaUrl=c.mediaUrl, url=c.url,
                    title=c.title, channel=c.channel, license=c.license, credit=c.credit,
                    attribution=c.attribution, score=option.total, phash=option.phash,
                )
                try:
                    media = materialiser.materialise(selection, shot, out_dir, digest)
                except Exception as error:
                    tried.append(f"{c.id}: {str(error)[-80:]}")
                    dead.add(f"{c.id}@{option.start}")
                    continue
                if looks_used(ctx.root / media.path, media.kind):
                    tried.append(f"{c.id}: ya está en pantalla")
                    dead.add(f"{c.id}@{option.start}")
                    continue
                with identity_lock:
                    why = wrong_person(shot_id, ctx.root / media.path, media.kind)
                if why:
                    tried.append(f"{c.id}: {why}")
                    with turned_lock:
                        strikes[c.id] = strikes.get(c.id, 0) + 1
                        if max_strikes and strikes[c.id] == max_strikes:
                            print(f"   {c.id}: descartado para el resto del vídeo ({why[:80]})")
                    continue
                with claim:                    # another shot may have taken the same picture meanwhile
                    if looks_used(ctx.root / media.path, media.kind):
                        tried.append(f"{c.id}: ya está en pantalla")
                        continue
                    # …or the same seconds of the same source, chosen at the same time by another thread (newgym3: the
                    # same 2 s of one training video in seven shots, all picked while none was claimed yet)
                    if same_stretch(c.id, media.start, media.end,
                                    [u for u in used if u.shotId != exempt] if exempt else used, needed):
                        tried.append(f"{c.id}: ese tramo ya está en pantalla")
                        dead.add(f"{c.id}@{option.start}")
                        continue
                    used.append(selection)
                    pexels_used.add(c.id)
                    if h := _frame_hash(ctx.root / media.path, media.kind):
                        on_screen.append(h)
                    frames_on_screen.extend(frames(ctx.root / media.path, media.kind))
                    committed.add(shot_id)
                return FallbackItem(
                    shotId=shot_id, reason=reason, method=method, kind=media.kind, path=media.path,
                    source=c.source, candidateId=c.id, url=c.url, start=media.start, end=media.end,
                    durationSeconds=media.durationSeconds, credit=c.credit, attribution=c.attribution,
                    specHash=digest, sourceHeight=media.sourceHeight, year=media.year,
                    judged=vet if judged is None else judged,
                )
            return None

        if hypothetical(shot) and cfg.get("hypothetical_images", True):
            try:
                item = _generate(ctx, shot, reason, digest, out_dir, lut, cfg, illustration=True)
            except Exception as error:
                tried.append(f"recreación: {str(error)[:120]}")

        limit = int(cfg.get("next_options", 3))

        # 1. The next option from stage 4 — only when the choice itself was fine but its download failed.
        if item is None and reason.startswith("descarga fallida"):
            failed_id = selections[shot_id].candidateId
            scores = ShotScores.model_validate_json((ctx.work_dir / "scores" / f"{shot_id}.json").read_text("utf-8"))
            candidates = {c.id: c for c in ShotCandidates.model_validate_json(
                (ctx.work_dir / "candidates" / f"{shot_id}.json").read_text("utf-8")).candidates}
            # 1a. what the judge already accepted for this shot (its 2nd and 3rd), in its order: no new call, and
            # never reordered by CLIP before (39 % of the HD downloads failed: each one used to lose the judge's work)
            accepted = []
            for cid, start, _ in selections[shot_id].alternatives:
                match = next((o for o in scores.options if o.candidateId == cid and o.start is not None and start is not None
                              and abs(o.start - start) < 0.05), None)
                if match is not None and cid != failed_id and cid in candidates \
                        and not is_repeat(match, used, int(judge_cfg.get("max_phash_distance", 6))) \
                        and not seen_elsewhere(match, elsewhere):
                    accepted.append(match)
            if accepted:
                item = vet_and_materialise(accepted, candidates, "next-option", vet=False, judged=True)
        if item is None and reason.startswith("descarga fallida"):
            options = [
                o for total, o in ranked(scores.options, judge_cfg.get("source_bonus", {"youtube": 0.02}))
                if total >= float(judge_cfg.get("min_accept", 0.22)) and o.candidateId != failed_id
                and (chosen_material(candidates[o.candidateId])
                     or not blocked_by_title(candidates[o.candidateId].title, candidates[o.candidateId].channel,
                                             ctx.section("content").get("title_blocklist"),
                                             ctx.section("content").get("official_channels")))
                and not is_repeat(o, used, int(judge_cfg.get("max_phash_distance", 6)))
                and not seen_elsewhere(o, elsewhere)
            ][:limit]
            item = vet_and_materialise(options, candidates, "next-option")

        # 1a'. An ambient idea (planner.ideas, bloque 2.3): the clip of the shot next to it in the same idea runs on
        # (its following seconds, after a short jump so the two never make one excerpt over 5 s) — the same moment,
        # chosen by the judge for this very idea — before any other source.
        if item is None and idea_kind == "ambiente":
            options, neighbour_candidates, continued = neighbour_option(story.shots, shot, used, needed, known_candidate,
                                                                        cap=tope.seconds(ctx))
            item = vet_and_materialise(options, neighbour_candidates, "neighbour", vet=False, judged=True,
                                       exempt=continued)

        # 1b. Protagonist first: any other fragment of the protagonist found for the whole video,
        # preferring the shot's own event, before any stock footage.
        who = person_for(story, shot)
        if item is None and who and shot.broll:
            pool, pool_candidates = protagonist_pool(ctx, story, who)
            event_words = tokens(shot.broll.event or "")
            options = sorted(
                (o for o in pool if not is_repeat(o, used, int(judge_cfg.get("max_phash_distance", 6)))
                 and not seen_elsewhere(o, elsewhere)),
                key=lambda o: (-len(event_words & tokens(pool_candidates[o.candidateId].title or "")), -o.total),
            )[:limit]
            item = vet_and_materialise(options, pool_candidates, "protagonist")

        # 1b'. Footage already analysed for the neighbouring shots of the same story event (the same casino,
        # the same final, the same factory…): real footage of the topic before any stock. Vetted by the judge.
        if item is None and shot.broll:
            pool, pool_candidates = event_pool(ctx, story, shot, research=True)   # with the second searches so far
            options = [o for o in pool if not is_repeat(o, used, int(judge_cfg.get("max_phash_distance", 6)))
                       and not seen_elsewhere(o, elsewhere)
                       and not any(u.candidateId == o.candidateId and u.start is not None and o.start is not None
                                   and abs(u.start - o.start) < 4 for u in used)][:limit]
            item = vet_and_materialise(options, pool_candidates, "event-footage")

        # 1b''. A second search: new YouTube queries written from why the judge said no (another accident, another
        # athlete, a re-edit…), scored like the first ones and vetted by the judge — real footage before photos/stock.
        if item is None and shot.broll and cfg.get("research", True) and offline:
            tried.append(f"segunda búsqueda: {sin_youtube.NOTE}")      # its queries are YouTube's: not even the LLM
        elif item is None and shot.broll and cfg.get("research", True) and idea_kind == "ambiente":
            tried.append("segunda búsqueda: idea de ambiente, sin imagen propia que buscar")   # bloque 2.3
        elif item is None and shot.broll and cfg.get("research", True):
            options, research_candidates = research(shot, reason, tried)
            options = [o for o in options if not is_repeat(o, used, int(judge_cfg.get("max_phash_distance", 6)))
                       and not seen_elsewhere(o, elsewhere)][:limit]
            item = vet_and_materialise(options, research_candidates, "re-search")

        # 1c. A web photo of whoever/whatever the shot names (then of the protagonist), in a card —
        # what sports channels do when there is no footage. Vetted by the judge like the rest.
        if item is None and shot.broll:
            person = who
            # the people/places named → the event itself → the protagonist's photos kept in the library
            # from earlier videos → any web photo of the protagonist; stock only after all of this.
            attempts = [("web", shot.broll.entities), ("web", [shot.broll.event] if shot.broll.event else []),
                        ("library", [person] if person else []), ("web", [person] if person else [])]
            for kind, entities in attempts:
                if item is not None or not entities:
                    continue
                if kind == "library":
                    candidates = library_photos(ctx, person)
                else:
                    candidates = web_photos(ctx, shot.broll.model_copy(update={"entities": entities[:2]}), tried)
                options = [photo_option(c) for c in candidates.values()
                           if c.id not in pexels_used and not any(u.candidateId == c.id for u in used)
                           and c.id not in elsewhere][:limit]
                item = vet_and_materialise(options, candidates, "library-photo" if kind == "library" else "web-photo")

        # 2. Pexels (video, then photo), picked by CLIP — for a video about a person only when nothing of
        # them is left at all: anonymous stock is exactly what that format avoids.
        if (item is None and cfg.get("pexels", True) and ctx.env("PEXELS_API_KEY", required=False)
                and not (in_hook and not cfg.get("judge_pexels", False) and not concept)   # unjudged stock: never in the hook
                and (not real_people or cfg.get("pexels_for_person", True) or concept)):
            with models_lock:
                if clip is None:
                    clip, _ = make_models(ctx)
            vector = clip.shot_vector(prompts_for(shot))
            queries = [concept] if concept else list(dict.fromkeys(image_query(q, 4) for q in shot.broll.queries[:2]))
            for kind in ("video", "photo"):
                scored: list[tuple[float, dict[str, Any]]] = []
                for query in queries:
                    try:
                        results = pexels_search(ctx, kind, query, http)
                    except Exception as error:
                        tried.append(f"pexels {kind} {query!r}: {str(error)[:80]}")
                        continue
                    for result in results:
                        rid = f"px{kind[0]}:{result['id']}"
                        if rid in pexels_used or (kind == "video" and float(result.get("duration") or 0) < needed):
                            continue
                        thumb_url = result.get("image") if kind == "video" else (result.get("src") or {}).get("medium")
                        picture = _thumbnail(http, thumb_url, ctx.cache_dir / "pexels" / "thumbs") if thumb_url else None
                        if picture is not None:
                            result = {**result, "_thumb": str((ctx.cache_dir / "pexels" / "thumbs" / f"{key(thumb_url)}.jpg")
                                                              .relative_to(ctx.root))}
                            scored.append((float(clip.embed_images([picture])[0] @ vector), result))
                scored.sort(key=lambda pair: -pair[0])
                good = [pair for pair in scored if pair[0] >= float(cfg.get("min_clip", 0.22))]
                if not good:
                    tried.append(f"pexels {kind}: nada con CLIP ≥ {cfg.get('min_clip', 0.22)}")
                    continue
                if cfg.get("judge_pexels", False) or concept:
                    # fallback.judge_pexels (off: one judge call per such shot): stock footage chosen by CLIP alone was a
                    # third of guiadelmapa; the judge sees its best ones first and only what it accepts is used
                    good = _judged_stock(ctx, shot, good[:3], kind, story, tried)
                    if not good:
                        continue
                for similarity, best in good[:4]:
                    author = str((best.get("user") or {}).get("name") or best.get("photographer") or "Pexels")[:40]
                    rid = f"px{kind[0]}:{best['id']}"
                    try:
                        if kind == "video":
                            files = [f for f in (best.get("video_files") or []) if (f.get("width") or 0) <= 1920 and f.get("link")]
                            link = max(files, key=lambda f: f.get("width") or 0)["link"]
                            source = _download(http, link, ctx.cache_dir / "pexels" / f"{best['id']}.mp4")
                            offset = min(1.0, max(0.0, float(best.get("duration") or needed) - needed))
                            target = out_dir / f"{shot_id}.mp4"
                            normalise_video(source, target, offset=offset, duration=needed, lut=lut, cfg=ctx.section("ingest"),
                                            grade=ctx.section("grade"))
                            info = probe(target)
                            extra = {"start": offset, "end": round(offset + info["duration"], 3), "durationSeconds": round(info["duration"], 3)}
                        else:
                            link = (best.get("src") or {}).get("large2x") or (best.get("src") or {}).get("original")
                            source = _download(http, link, ctx.cache_dir / "pexels" / f"{best['id']}.jpg")
                            target = out_dir / f"{shot_id}.jpg"
                            normalise_image(source, target, lut=lut, grade=ctx.section("grade"))
                            extra = {}
                    except Exception as error:
                        tried.append(f"{rid}: {str(error)[:80]}")
                        continue
                    if looks_used(target, "video" if kind == "video" else "image"):
                        tried.append(f"{rid}: ya está en pantalla (misma imagen en otra fuente)")
                        continue
                    item = FallbackItem(
                        shotId=shot_id, reason=reason, method=f"pexels-{kind}", kind="video" if kind == "video" else "image",
                        path=str(target.relative_to(ctx.root)), source="pexels", candidateId=rid, url=best.get("url"),
                        credit=f"Fuente: {author} / Pexels", attribution=f"{author} — Pexels: {best.get('url')}",
                        clip=round(similarity, 4), specHash=digest, judged=bool(cfg.get("judge_pexels", False)), **extra,
                    )
                    pexels_used.add(rid)
                    break
                if item is not None:
                    break

        # 2b. Still nothing for what this line describes exactly (an interview nobody filmed, a 2018 report…):
        # another unused moment of the protagonist's own footage, as documentary channels do over narration,
        # rather than a text card. The identity check still applies; the judge does not (it would want the
        # exact scene again).
        literal = shot.idea is not None and shot.idea.kind == "literal"

        def photo_of(person: str) -> FallbackItem | None:
            found = None
            era = (shot.idea.era if shot.idea is not None else None) or None
            # with the idea's time (her adolescence, Río 2016) the web search asks for THAT time first, before the
            # library's photos of the person, which may be of any age (newideas 2:24, 3:08: adult photos for a girl)
            for kind in (("web", "library") if era else ("library", "web")):
                if found is not None:
                    break
                candidates = library_photos(ctx, person) if kind == "library" else \
                    web_photos(ctx, photo_broll(shot.broll, person, era), tried)
                options = [photo_option(c) for c in candidates.values()
                           if c.id not in pexels_used and not any(u.candidateId == c.id for u in used)
                           and c.id not in elsewhere][: limit * 2]
                found = vet_and_materialise(options, candidates, "protagonist-photo", vet=False)
            return found

        # planner.ideas: a literal idea without its clip — a photo of the person first, then a clip of them that the
        # judge accepts; never a clip of something else, and a board only at the end (ideas-pantallas-de-texto.md:
        # «that very thing or nothing» made newideas half text). fallback.literal_ambient: false brings back the old rule
        literal_ambient = literal and photo_first(shot.idea, cfg)
        ambient_photo = not literal and photo_first(shot.idea, cfg)
        if item is None and (literal_ambient or ambient_photo) and who and shot.broll and cfg.get("photo_for_moments", True):
            item = photo_of(who)
        if item is None and who and shot.broll and cfg.get("protagonist_filler", True) and (not literal or literal_ambient):
            pool, pool_candidates = protagonist_pool(ctx, story, who)
            options = sorted((o for o in pool if o.kind == "video"
                              and not is_repeat(o, used, int(judge_cfg.get("max_phash_distance", 6)))
                              and not seen_elsewhere(o, elsewhere)
                              and not any(u.candidateId == o.candidateId and u.start is not None and o.start is not None
                                          and abs(u.start - o.start) < 6 for u in used)),
                             key=lambda o: -o.total)[: limit * 2]
            # a narrated moment (a fall, tears on the podium) is never filled with any other moment of the person
            # fallback.judge_filler (off: one judge call more per such shot): the judge vets any filler, not only moments
            item = vet_and_materialise(options, pool_candidates, "protagonist-filler",
                                       vet=literal or bool(shot.broll.moment) or bool(cfg.get("judge_filler", False)))

        # 2c. A narrated moment nobody filmed (Yulo dejected after fourth place, the Manila parade, a press conference):
        # a photo of the protagonist instead of an empty shot, as sports channels do. Without the judge (it would
        # want the exact scene again: gymyulo, 54 % empty), with the identity check — a photo of the person is never
        # a lie about the moment, another moment's footage could be. `fallback.photo_for_moments` (on).
        if item is None and who and shot.broll and cfg.get("photo_for_moments", True) and not (literal_ambient or ambient_photo):
            item = photo_of(who)

        # 3. Generated image — the last resort, never for a video about a real person.
        if item is None and cfg.get("generate", True) and not real_people:
            try:
                item = _generate(ctx, shot, reason, digest, out_dir, lut, cfg)
            except Exception as error:
                tried.append(f"generada: {str(error)[:120]}")

        if item is not None and shot_id not in committed:      # Pexels / generated: taken here
            with claim:
                pexels_used.add(item.candidateId)
                if h := _frame_hash(ctx.root / item.path, item.kind):
                    on_screen.append(h)
                frames_on_screen.extend(frames(ctx.root / item.path, item.kind))
        if item is not None:
            print(f"   {shot_id}: {item.method} ({item.source}){' — ' + item.credit if item.credit else ''}")
        return item, tried

    from .budget import BudgetReached, VideoOverBudget, guard

    def safely(job: tuple[str, str]) -> tuple[FallbackItem | None, list[str]]:
        try:
            guard(ctx)                     # the daily and per-video caps before each shot's paid calls (judge, images)
            return resolve(*job)
        except (BudgetReached, VideoOverBudget):
            raise                          # a cap is the run's problem, never one shot's: the stage stops here
        except Exception as error:         # one shot's trouble never stops the others
            return None, [f"error: {str(error)[:160]}"]

    # `speed.fallback_parallel`, outside the `fallback` section: changing it never makes the stage (or its cached
    # shots) run again. Most of each shot is waiting on downloads and the vision judge, so 8 fits an 8-core server.
    workers = int(ctx.section("speed").get("fallback_parallel", cfg.get("parallel", 8)))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(safely, todo))
    from .budget import dead_key

    dead = next((t for _, tried in results for t in tried if dead_key(t)), None)
    if dead:                                  # no key: nothing was really tried; the stage fails, the queue waits
        raise RuntimeError(dead)
    for (shot_id, _), (item, tried) in zip(todo, results):
        if item is None:
            unresolved[shot_id] = "; ".join(tried)[:400] or "sin alternativas"
        else:
            items.append(item)
    order = list(pending)
    items.sort(key=lambda i: order.index(i.shotId) if i.shotId in order else len(order))

    youtube.close()
    ctx.write_json(OUTPUT, FallbackFile(slug=ctx.slug, items=items, unresolved=unresolved).model_dump(exclude_none=True))
    methods: dict[str, int] = {}
    for item in items:
        methods[item.method] = methods.get(item.method, 0) + 1
    spent = sum(i.costUsd for i in items)
    print(f"   Resueltos: {len(items)} ({', '.join(f'{k} {v}' for k, v in methods.items()) or '—'}) · "
          f"sin resolver: {len(unresolved)} · coste {spent:.3f} $ · {time.monotonic() - started:.0f} s")
    for shot_id, why in unresolved.items():
        print(f"   AVISO {shot_id}: {why[:200]}")
    # Most of the video without a picture is a slideshow of chalkboards (negocio2-4: 80-95 % of the shots): stop
    # here, before the render, instead of making it. qa.max_empty_share (0.6) of the footage shots, at most.
    limit = float(ctx.section("qa").get("max_empty_share", 0.6))
    if shots and len(unresolved) / len(shots) > limit:
        # the setting that really stands in the way (atletismo22 was told «pexels: true», already on)
        person = bool(story.subject) and not cfg.get("pexels_for_person", False)
        hint = ("permite el stock en vídeos de una persona en su config.yaml (fallback: pexels_for_person: true)"
                if person else "permite el stock como último recurso en el canal (fallback: pexels: true)")
        raise RuntimeError(
            f"{len(unresolved)} de {len(shots)} planos sin ninguna imagen ({len(unresolved) / len(shots):.0%}): no se "
            f"monta, saldría un vídeo de pizarras de texto. Revisa «Decisiones del relleno» (el juez rechazó casi todo) "
            f"o {hint}.")


def photo_broll(broll: Any, person: str, era: str | None = None) -> Any:
    """The shot's search, for photos of `person`: with the idea's time, «person + time» goes first (the web search
    tries the event before the bare name, and every result must still name the person)."""

    update: dict[str, Any] = {"entities": [person]}
    if era:
        update["event"] = f"{person} {era}"[:160]
    return broll.model_copy(update=update)


def photo_first(idea: Any, cfg: dict[str, Any]) -> bool:
    """Whether a shot without its clip tries a photo of the person BEFORE another clip of them: a literal idea, yes
    (fallback.literal_ambient, on); an ambient idea only with fallback.ambient_photo_first (off; revision-22-11.md
    point 2, measured by the «huecos tapados» of revisor --base); a shot planned without ideas, no."""

    kind = getattr(idea, "kind", None)
    if kind == "literal":
        return bool(cfg.get("literal_ambient", True))
    if kind == "ambiente":
        return bool(cfg.get("ambient_photo_first", False))
    return False


def web_photos(ctx: RunContext, broll: Any, notes: list[str]) -> dict[str, Candidate]:
    """Web photos (Google Images via Serper, or DuckDuckGo) of the broll's entities only."""

    images_cfg = ctx.section("sourcing").get("images", {})
    if not images_cfg.get("web", {}).get("enabled", True):
        return {}
    only_web = {**images_cfg, "wikimedia": {"enabled": False}, "openverse": {"enabled": False},
                "pixabay": {"enabled": False}}
    source = ImageSources(root=ctx.root, cache_dir=ctx.cache_dir, config=only_web,
                          serper_key=ctx.env("SERPER_API_KEY", required=False))
    _, found = source.search(broll, notes)
    return {c.id: c for c in found}


def library_photos(ctx: RunContext, person: str) -> dict[str, Candidate]:
    """Photos of the person that earlier videos already used (athlete library), still on disk."""

    out: dict[str, Candidate] = {}
    for cid, raw in library.load(ctx, person).get("photos", {}).items():
        try:
            c = Candidate.model_validate(raw)
        except ValueError:
            continue
        if c.imagePath and (ctx.root / c.imagePath).is_file():
            out[cid] = c
    return out


def photo_option(candidate: Candidate) -> Option:
    return Option.model_validate({
        "candidateId": candidate.id, "source": candidate.source, "kind": "image", "pass": "coarse",
        "analysisPath": candidate.imagePath, "scores": {"clip": candidate.rankScore}, "total": candidate.rankScore,
    })


_POOL: dict[str, tuple[list[Option], dict[str, Candidate]]] = {}


RESEARCH_SYSTEM = """
Eres documentalista de vídeo. Un plano de un documental no encontró metraje válido con las búsquedas que se hicieron
(te digo por qué no sirvió lo que salió). Propón 3 búsquedas NUEVAS de YouTube EN INGLÉS, distintas de las ya hechas,
que traigan metraje REAL de lo que dice la frase en su contexto exacto (persona, lugar, fecha, empresa, evento):
nombres propios + qué se ve + año/lugar; evita lo que causó el rechazo (otro accidente, otra persona, recreaciones,
vídeos de otros creadores). Si la frase es abstracta, busca la imagen concreta del tema que mejor la representa.
Devuelve SOLO JSON: {"queries": ["…", "…", "…"]}
""".strip()


def person_for(story: ShotsFile, shot: Any) -> str:
    """Whom a shot is about: the video's protagonist, or in a video without one (a list of cases, a
    ranking) the person named in the shot's story event, among the names the planner put on screen."""

    if story.subject:
        return story.subject.split("·")[0].strip()
    event = tokens(getattr(shot.broll, "event", None) or "") if shot.broll else set()
    from .people import looks_like_person

    names = [s.label.text for s in story.shots if s.label and s.label.kind == "name" and looks_like_person(s.label.text)]
    found = next((n for n in names if tokens(n) and tokens(n) <= event), "")
    if found:
        return found.title() if found.isupper() else found
    # the planner writes each event as "Name Surname + what + where": two capitalised words first
    words = (getattr(shot.broll, "event", None) or "").split() if shot.broll else []
    lead = [w for w in words[:2] if w[:1].isupper() and w.isalpha() and not w.isupper()]
    return " ".join(lead) if len(lead) == 2 else ""


def event_pool(ctx: RunContext, story: ShotsFile, shot: Any, reach: int = 4,
               research: bool = False) -> tuple[list[Option], dict[str, Candidate]]:
    """Scored fragments of the other shots telling the same story event (or, without events, of the
    shots next to it), best first: footage about the same place/company/fact the shot is part of. With `research`,
    also what their second searches found. Never a neighbour's footage of another person this shot does not name."""

    ordered = [s for s in story.shots if needs_footage(s)]
    index = next((i for i, s in enumerate(ordered) if s.id == shot.id), None)
    if index is None:
        return [], {}
    event = shot.broll.event if shot.broll else None
    if event:
        group = [s for s in ordered if s.id != shot.id and s.broll and s.broll.event == event]
    else:
        group = [s for s in ordered[max(0, index - reach): index + reach + 1] if s.id != shot.id]
    judge_cfg = ctx.section("judge")
    blocklist = ctx.section("content").get("title_blocklist")
    official = ctx.section("content").get("official_channels")
    options: dict[tuple[str, float | None], Option] = {}
    candidates: dict[str, Candidate] = {}
    # a neighbour's footage of someone this shot does not name is not this shot's footage: the script mentions
    # Midori Ito beside Mao Asada's Sochi skate, and Ito's Albertville videos are not Sochi
    from .people import looks_like_person

    own = tokens(" ".join([*(shot.broll.entities if shot.broll else []), person_for(story, shot)]))
    mine = [tokens(n) for n in [*(shot.broll.entities if shot.broll else []), person_for(story, shot)]
            if n and looks_like_person(n) and tokens(n)]                       # the people this shot is about
    others = [tokens(e) for o in group for e in (o.broll.entities if o.broll else [])
              if looks_like_person(e) and tokens(e) and not tokens(e) <= own] if mine else []
    places = [(o, "candidates", "scores") for o in group]
    if research:
        places += [(o, f"research/{o.id}/candidates", f"research/{o.id}/scores") for o in group]
    for other, cand_dir, score_dir in places:
        cand_path = ctx.work_dir / cand_dir / f"{other.id}.json"
        scores_path = ctx.work_dir / score_dir / f"{other.id}.json"
        if not cand_path.is_file() or not scores_path.is_file():
            continue
        found = {c.id: c for c in ShotCandidates.model_validate_json(cand_path.read_text("utf-8")).candidates}
        for total, option in ranked(ShotScores.model_validate_json(scores_path.read_text("utf-8")).options,
                                    judge_cfg.get("source_bonus", {"youtube": 0.02})):
            c = found.get(option.candidateId)
            if c is None or option.kind != "video" or total < float(judge_cfg.get("min_accept", 0.22)) \
                    or blocked_by_title(c.title, c.channel, blocklist, official):
                continue
            title = tokens(f"{c.title or ''} {c.channel or ''}")
            if any(name <= title for name in others) and not any(name & title for name in mine):
                continue
            candidates[c.id] = c
            options.setdefault((option.candidateId, option.start), option)
    return sorted(options.values(), key=lambda o: -o.total), candidates


JUMP = 1.5                   # s skipped between a shot's clip and the next one taken from the same source and moment


def neighbour_option(story_shots: list[Shot], shot: Shot, used: list[Any], needed: float,
                     lookup: Any, cap: float = 5.0) -> tuple[list[Option], dict[str, Candidate], str | None]:
    """The seconds right after (or before) the video clip of the shot next to this one in its idea (planner.ideas):
    the same source and moment. When both together fit the video's cap (content.max_third_party_seconds) they run on
    with no gap — one clip cut in two, the idea held on one source; past it, after a JUMP so neither excerpt runs over.
    `lookup(id)` gives a candidate of this video. Also returns the shot it continues (None when it is not seamless)."""

    if shot.idea is None:
        return [], {}, None
    members = [s.id for s in story_shots if s.idea is not None and s.idea.id == shot.idea.id]
    if shot.id not in members:
        return [], {}, None
    at = members.index(shot.id)
    sides = ([(members[at - 1], True)] if at > 0 else []) + ([(members[at + 1], False)] if at + 1 < len(members) else [])
    for other, after in sides:
        chosen = next((u for u in reversed(used) if u.shotId == other and u.kind == "video" and u.start is not None), None)
        if chosen is None:
            continue
        candidate = lookup(chosen.candidateId)
        if candidate is None or candidate.kind != "video":
            continue
        span = (chosen.end if chosen.end is not None else chosen.start + needed) - chosen.start
        seamless = span + needed <= cap + 1e-6
        jump = 0.0 if seamless else JUMP
        start = ((chosen.end if chosen.end is not None else chosen.start + needed) + jump) if after \
            else chosen.start - jump - needed
        if start < 0 or (candidate.durationSeconds and start + needed > candidate.durationSeconds):
            continue
        option = Option.model_validate({"candidateId": candidate.id, "source": candidate.source, "kind": "video",
                                        "pass": "coarse", "start": round(start, 3), "end": round(start + needed, 3),
                                        "scores": {"clip": 0.0}, "total": 0.0})
        return [option], {candidate.id: candidate}, (other if seamless else None)
    return [], {}, None


def reused_selection(item: FallbackItem) -> Selection:
    """A fallback item kept from an earlier run, as the selection the repeat checks of this run compare against. Not
    validated: a generated image has no page or credit, and it only ever meets same_stretch / is_repeat / overused."""

    return Selection.model_construct(shotId=item.shotId, status="selected", decidedBy="fallback", candidateId=item.candidateId,
                     source=item.source, kind=item.kind, start=item.start, end=item.end, url=item.url,
                     credit=item.credit)


def same_stretch(candidate_id: str, start: float | None, end: float | None, used: list[Any], needed: float = 3.0,
                 pad: float = 1.0) -> bool:
    """These seconds of this source (± `pad`) are already on screen in another shot. A window without an end is taken
    as `needed` seconds long. Photos (no start) are never a stretch."""

    if start is None:
        return False
    stop = end if end is not None else start + needed
    for other in used:
        if getattr(other, "candidateId", None) != candidate_id or getattr(other, "start", None) is None:
            continue
        other_stop = other.end if getattr(other, "end", None) is not None else other.start + needed
        if start < other_stop + pad and other.start < stop + pad:
            return True
    return False


def protagonist_pool(ctx: RunContext, story: ShotsFile, person: str | None = None) -> tuple[list[Option], dict[str, Candidate]]:
    """Every scored fragment, across all shots, from a source whose title or channel names the protagonist
    (or `person`, in videos without a single protagonist)."""

    person = person or story.subject.split("·")[0].strip()
    cache_key = f"{ctx.work_dir}:{person}"
    if cache_key in _POOL:
        return _POOL[cache_key]
    name = tokens(person)                     # the full name: the surname alone also matches relatives
    judge_cfg = ctx.section("judge")
    blocklist = ctx.section("content").get("title_blocklist")
    official = ctx.section("content").get("official_channels")
    options: dict[tuple[str, float | None], Option] = {}
    candidates: dict[str, Candidate] = {}
    for path in sorted((ctx.work_dir / "candidates").glob("s*.json")):   # per-shot files, not the stage summary
        scores_path = ctx.work_dir / "scores" / path.name
        if not scores_path.is_file() or not name:
            continue
        found = {c.id: c for c in ShotCandidates.model_validate_json(path.read_text("utf-8")).candidates}
        for total, option in ranked(ShotScores.model_validate_json(scores_path.read_text("utf-8")).options,
                                    judge_cfg.get("source_bonus", {"youtube": 0.02})):
            c = found.get(option.candidateId)
            if (c is None or total < float(judge_cfg.get("min_accept", 0.22))
                    or not name <= tokens(f"{c.title or ''} {c.channel or ''}")
                    or blocked_by_title(c.title, c.channel, blocklist, official)):
                continue
            candidates[c.id] = c
            options.setdefault((option.candidateId, option.start), option)
    _POOL[cache_key] = (sorted(options.values(), key=lambda o: -o.total), candidates)
    return _POOL[cache_key]


def _frame_hash(path: Path, kind: str) -> str | None:
    """pHash of the middle frame of a materialised clip (or of the still)."""

    if kind == "image":
        frame = cv2.imread(str(path))
    else:
        capture = cv2.VideoCapture(str(path))
        capture.set(cv2.CAP_PROP_POS_FRAMES, (capture.get(cv2.CAP_PROP_FRAME_COUNT) or 1) // 2)
        ok, frame = capture.read()
        capture.release()
        frame = frame if ok else None
    return det.phash(frame) if frame is not None else None


def _generate(ctx: RunContext, shot: Shot, reason: str, digest: str, out_dir: Path, lut: Path | None,
              cfg: dict[str, Any], illustration: bool = False) -> FallbackItem:
    """A generated still. `illustration`: a scene that never happened ("¿y si…?"), drawn as cinematic concept
    art — never a fake photo — and with no recognisable real person."""

    from openai import OpenAI

    model = str(cfg.get("image_model", "gpt-image-2"))
    context = str(ctx.read_json("shots.json").get("context") or "")
    if illustration:
        scene = (shot.broll.event or "").strip()
        scene = scene[len("WHAT IF"):].strip(" :,-") if scene.upper().startswith("WHAT IF") else scene
        prompt = (
            "Cinematic digital illustration, painterly concept art with visible brushwork, dramatic lighting, "
            f"16:9 landscape, of a hypothetical scenario: {scene}. {shot.broll.visualIntent}. Context: {context} "
            "Clearly an illustration, not a photograph. No recognizable real people (faceless or distant figures "
            "only), no text, no letters, no numbers, no logos, no watermarks."
        )
    elif str(cfg.get("image_style") or "photo") == "illustration":
        # the channel draws its story scenes (Jet Crumbs): a hand-made look that never passes for a real photo
        prompt = (
            "Hand-drawn pencil and watercolor illustration, documentary storyboard style, loose ink lines, muted warm "
            f"palette on textured paper, 16:9 landscape. {shot.broll.visualIntent}. Context: {context} "
            "People drawn loosely with no recognisable faces. No text, no letters, no numbers, no logos, no watermarks."
        )
    else:
        prompt = (
            "Photorealistic documentary b-roll still, 16:9 landscape, natural light, shallow depth of field. "
            f"{shot.broll.visualIntent}. Context: {context} "
            "No text, no letters, no numbers, no logos, no watermarks, no captions."
        )
    target_png = ctx.cache_dir / "generated" / f"{key(model, prompt, cfg.get('image_quality', 'medium'))}.png"
    usd = 0.0
    if not target_png.is_file():
        client = OpenAI(api_key=ctx.env("OPENAI_API_KEY"), timeout=300, max_retries=1)
        response = client.images.generate(model=model, prompt=prompt, size="1536x1024",
                                          quality=str(cfg.get("image_quality", "medium")), n=1)
        target_png.parent.mkdir(parents=True, exist_ok=True)
        target_png.write_bytes(base64.b64decode(response.data[0].b64_json))
        usage = getattr(response, "usage", None)
        prices = cfg.get("image_usd_per_mtok", {"text_input": 5.0, "image_output": 40.0})
        if usage is not None:
            usd = (getattr(usage, "input_tokens", 0) * float(prices.get("text_input", 5.0))
                   + getattr(usage, "output_tokens", 0) * float(prices.get("image_output", 40.0))) / 1e6
        else:
            usd = float(cfg.get("image_usd_estimate", 0.06))
        record_cost(ctx, stage=STAGE, provider="openai", operation=model, usd=usd,
                    details={"shot": shot.id, "estimated": True,
                             "tokens": [getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)]})
    target = out_dir / f"{shot.id}.jpg"
    normalise_image(target_png, target, lut=lut, grade=ctx.section("grade"))
    return FallbackItem(
        shotId=shot.id, reason=reason, method="generated", kind="image", path=str(target.relative_to(ctx.root)),
        source="generated", candidateId=f"gen:{target_png.stem}", attribution=f"Imagen generada con {model}",
        costUsd=round(usd, 4), specHash=digest,
    )


def validate(ctx: RunContext) -> bool:
    for item in FallbackFile.model_validate(ctx.read_json(OUTPUT)).items:
        if not (ctx.root / item.path).is_file():
            raise FileNotFoundError(item.path)
    return True
