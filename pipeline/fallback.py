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
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

from .analysis import detectors as det
from .analysis import make_models, prompts_for
from .context import RunContext
from .costs import record_cost
from .ingest import MANIFEST, Materialiser, find_lut, normalise_image, normalise_video, probe
from .judge import LETTERS, call_judge, contact_sheet, is_repeat, ranked
from .schemas import (
    MAX_THIRD_PARTY_SECONDS,
    FallbackFile,
    FallbackItem,
    IngestFile,
    Selection,
    SelectionFile,
    Shot,
    ShotCandidates,
    ShotScores,
    ShotsFile,
)
from .sourcing import needs_footage, youtube_source
from .sourcing.common import USER_AGENT, blocked_by_title, cached_json, http_get_json, key
from .sourcing.images import image_query


STAGE = "fallback"
OUTPUT = "fallback.json"
MEDIA_DIR = "media_fallback"
VERSION = 3  # bump when the fallback policy changes: invalidates per-shot results
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


def _thumbnail(http: requests.Session, url: str, cache: Path) -> np.ndarray | None:
    try:
        path = _download(http, url, cache / f"{key(url)}.jpg")
    except requests.RequestException:
        return None
    return cv2.imread(str(path))


# --- stage -------------------------------------------------------------------------------


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "selection.json", ctx.work_dir / "media" / MANIFEST, ctx.work_dir / "shots.json"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("fallback")
    started = time.monotonic()
    out_dir = ctx.work_dir / MEDIA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = {s.id: s for s in ShotsFile.model_validate(ctx.read_json("shots.json")).shots if needs_footage(s)}
    selections = {s.shotId: s for s in SelectionFile.model_validate(ctx.read_json("selection.json")).selections}
    ingest = IngestFile.model_validate_json((ctx.work_dir / "media" / MANIFEST).read_text("utf-8"))
    done = {m.shotId for m in ingest.media}

    pending: dict[str, str] = {}
    for shot_id in shots:
        if shot_id in done:
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
    max_hamming = int(ctx.section("judge").get("max_phash_distance", 6))
    # Hashes of everything on screen: the same stock clip is often re-uploaded to YouTube.
    on_screen: list[str] = [s.phash for s in used if s.phash]

    def looks_used(path: Path, kind: str) -> bool:
        h = _frame_hash(path, kind)
        return h is not None and any(det.hamming(h, other) <= max_hamming for other in on_screen)

    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    youtube = youtube_source(ctx)
    lut = find_lut(ctx)
    materialiser = Materialiser(ctx, ctx.section("ingest"), lut, youtube, http)
    clip = None
    items: list[FallbackItem] = []
    unresolved: dict[str, str] = {}

    for shot_id, reason in pending.items():
        shot = shots[shot_id]
        needed = min(shot.duration, MAX_THIRD_PARTY_SECONDS)
        digest = key(VERSION, reason, shot.model_dump(), cfg, lut.name if lut else None)
        old = previous.get(shot_id)
        # Reuse the cached result unless a shot earlier in this run has already taken that media.
        if (old and old.specHash == digest and (ctx.root / old.path).is_file() and old.candidateId not in pexels_used
                and not looks_used(ctx.root / old.path, old.kind)):
            items.append(old)
            pexels_used.add(old.candidateId)
            if h := _frame_hash(ctx.root / old.path, old.kind):
                on_screen.append(h)
            continue
        item: FallbackItem | None = None
        tried: list[str] = []

        # 1. The next option from stage 4 — only when the choice itself was fine but its download failed.
        if reason.startswith("descarga fallida"):
            failed_id = selections[shot_id].candidateId
            scores = ShotScores.model_validate_json((ctx.work_dir / "scores" / f"{shot_id}.json").read_text("utf-8"))
            candidates = {c.id: c for c in ShotCandidates.model_validate_json(
                (ctx.work_dir / "candidates" / f"{shot_id}.json").read_text("utf-8")).candidates}
            judge_cfg = ctx.section("judge")
            options = [
                o for total, o in ranked(scores.options, judge_cfg.get("source_bonus", {"youtube": 0.02}))
                if total >= float(judge_cfg.get("min_accept", 0.22)) and o.candidateId != failed_id
                and not blocked_by_title(candidates[o.candidateId].title, candidates[o.candidateId].channel,
                                         ctx.section("content").get("title_blocklist"))
                and not is_repeat(o, used, int(judge_cfg.get("max_phash_distance", 6)))
            ][: int(cfg.get("next_options", 3))]
            if options:
                # Nobody has looked at these yet: the vision judge vets them before anything is used.
                verdict = call_judge(ctx, shot, contact_sheet(options, candidates, ctx.root), LETTERS[: len(options)])
                by_letter = dict(zip(LETTERS, options))
                options = [by_letter[letter] for letter in verdict["ranking"] if letter in by_letter]
                if not options:
                    tried.append(f"juez rechazó las siguientes opciones: {verdict.get('reason', '')[:100]}")
            for option in options:
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
                    continue
                item = FallbackItem(
                    shotId=shot_id, reason=reason, method="next-option", kind=media.kind, path=media.path,
                    source=c.source, candidateId=c.id, url=c.url, start=media.start, end=media.end,
                    durationSeconds=media.durationSeconds, credit=c.credit, attribution=c.attribution,
                    specHash=digest,
                )
                used.append(selection)
                break

        # 2. Pexels (video, then photo), picked by CLIP.
        if item is None and cfg.get("pexels", True) and ctx.env("PEXELS_API_KEY", required=False):
            if clip is None:
                clip, _ = make_models(ctx)
            vector = clip.shot_vector(prompts_for(shot))
            queries = list(dict.fromkeys(image_query(q, 4) for q in shot.broll.queries[:2]))
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
                            scored.append((float(clip.embed_images([picture])[0] @ vector), result))
                scored.sort(key=lambda pair: -pair[0])
                good = [pair for pair in scored if pair[0] >= float(cfg.get("min_clip", 0.22))]
                if not good:
                    tried.append(f"pexels {kind}: nada con CLIP ≥ {cfg.get('min_clip', 0.22)}")
                    continue
                for similarity, best in good[:4]:
                    author = str((best.get("user") or {}).get("name") or best.get("photographer") or "Pexels")[:40]
                    rid = f"px{kind[0]}:{best['id']}"
                    try:
                        if kind == "video":
                            files = [f for f in best.get("video_files", []) if (f.get("width") or 0) <= 1920 and f.get("link")]
                            link = max(files, key=lambda f: f.get("width") or 0)["link"]
                            source = _download(http, link, ctx.cache_dir / "pexels" / f"{best['id']}.mp4")
                            offset = min(1.0, max(0.0, float(best.get("duration") or needed) - needed))
                            target = out_dir / f"{shot_id}.mp4"
                            normalise_video(source, target, offset=offset, duration=needed, lut=lut, cfg=ctx.section("ingest"))
                            info = probe(target)
                            extra = {"start": offset, "end": round(offset + info["duration"], 3), "durationSeconds": round(info["duration"], 3)}
                        else:
                            link = (best.get("src") or {}).get("large2x") or (best.get("src") or {}).get("original")
                            source = _download(http, link, ctx.cache_dir / "pexels" / f"{best['id']}.jpg")
                            target = out_dir / f"{shot_id}.jpg"
                            normalise_image(source, target, lut=lut)
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
                        clip=round(similarity, 4), specHash=digest, **extra,
                    )
                    pexels_used.add(rid)
                    break
                if item is not None:
                    break

        # 3. Generated image — the last resort.
        if item is None and cfg.get("generate", True):
            try:
                item = _generate(ctx, shot, reason, digest, out_dir, lut, cfg)
            except Exception as error:
                tried.append(f"generada: {str(error)[:120]}")

        if item is None:
            unresolved[shot_id] = "; ".join(tried)[:400] or "sin alternativas"
            continue
        items.append(item)
        pexels_used.add(item.candidateId)
        if h := _frame_hash(ctx.root / item.path, item.kind):
            on_screen.append(h)
        print(f"   {shot_id}: {item.method} ({item.source}){' — ' + item.credit if item.credit else ''}")

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
              cfg: dict[str, Any]) -> FallbackItem:
    from openai import OpenAI

    model = str(cfg.get("image_model", "gpt-image-2"))
    context = str(ctx.read_json("shots.json").get("context") or "")
    prompt = (
        "Photorealistic documentary b-roll still, 16:9 landscape, natural light, shallow depth of field. "
        f"{shot.broll.visualIntent}. Context: {context} "
        "No text, no letters, no numbers, no logos, no watermarks, no captions."
    )
    target_png = ctx.cache_dir / "generated" / f"{key(model, prompt, cfg.get('image_quality', 'medium'))}.png"
    usd = 0.0
    if not target_png.is_file():
        client = OpenAI(api_key=ctx.env("OPENAI_API_KEY"))
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
    normalise_image(target_png, target, lut=lut)
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
