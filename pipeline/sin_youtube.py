"""The queue goes on while YouTube is paused (ytpause): a video that still needs YouTube is made without it, from
the sources that need no YouTube, and is only finished if that material is as good as the channel's usual.

`watch.continue_without_youtube` (off by default; per channel in canales/<canal>.yaml, or per video). With the
pause on, such a video runs in «modo sin YouTube» (EDITVID_SIN_YOUTUBE=1 for that run):

- not one request to YouTube: searches, details, storyboards, captions, 360p windows and HD clips all stop before the
  network (YouTubeSource.offline); what is already on disk (cache/videos/, cached searches) is still read. The
  quarantine, the probe and the ways out are not touched.
- nothing done is lost: shots already searched, analysed or ingested keep their files; a clip already in
  work/<slug>/media/ keeps its shot (the judge keeps that choice, the ingest deletes nothing).
- only the shots without material look elsewhere (library, images, archive, Pexels…), with the usual thresholds.
- before the edit (after coldopen) `gate` measures the coverage against the channel's finished videos: shots that
  ended in the fallback, shots nothing covered, the cold open. Worse than usual → the video waits for YouTube
  (`WaitingForYouTube`, work/<slug>/sin_youtube.json) and the queue goes on with the next one; it is not tried again
  while the pause lasts unless its materials change.
- when YouTube is back the video resumes: the stages done without YouTube are marked (withoutYouTube in .stages/)
  and run again, and inside them only the shots that missed YouTube are redone (sourcing notes, analysis hashes).

out/<slug>/sin_youtube.md: what was reused, what came from other sources, what is missing and why it waits.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ENV = "EDITVID_SIN_YOUTUBE"
NOTE = "modo sin YouTube"
REASON = f"YouTube en pausa: ninguna petición a YouTube en este vídeo ({NOTE})"
STATE = "sin_youtube.json"                          # work/<slug>/
REPORT = "sin_youtube.md"                           # out/<slug>/
STAGES = frozenset({"sourcing", "analysis", "judge", "ingest", "fallback", "coldopen"})   # what YouTube feeds


class WaitingForYouTube(RuntimeError):
    """Made without YouTube, the material is worse than the channel's usual: the video waits, the queue goes on."""


def active() -> bool:
    """This run is in «modo sin YouTube»."""

    return os.environ.get(ENV) == "1"


@contextmanager
def offline() -> Iterator[None]:
    before = os.environ.get(ENV)
    os.environ[ENV] = "1"
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = before


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def enabled(root: Path, slug: str) -> bool:
    from .context import RunContext

    try:
        return bool(RunContext.create(slug, root=root).section("watch").get("continue_without_youtube", False))
    except Exception:
        return False


def signature(root: Path, slug: str) -> float:
    """The newest file of the video's materials: a change there (a new library clip, a new script) tries again."""

    from .context import find_video

    try:
        folder = find_video(root, slug)
    except Exception:
        return 0.0
    files = [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []
    return max([p.stat().st_mtime for p in files] or [0.0])


def waiting(root: Path, slug: str) -> bool:
    """Made without YouTube already, found short, and nothing changed since: it waits for YouTube."""

    state = _read(root / "work" / slug / STATE) or {}
    return state.get("status") == "pendiente" and float(state.get("sig") or -1) == signature(root, slug)


def can_continue(root: Path, slug: str) -> bool:
    """While YouTube is paused: this video may go on without it."""

    return enabled(root, slug) and not waiting(root, slug)


def made_without(root: Path, slug: str) -> bool:
    """Some stage of the video was done without YouTube and has not been redone with it."""

    return any((_read(p) or {}).get("withoutYouTube") for p in (root / "work" / slug / ".stages").glob("*.json"))


# --- one run ----------------------------------------------------------------------------------------------------

def begin(ctx: Any) -> None:
    """At the start of a run without YouTube: the clips on disk now (they must all be there at the end)."""

    from .ingest import MANIFEST, OUTPUT

    state = _read(ctx.work_dir / STATE) or {}
    manifest = _read(ctx.work_dir / OUTPUT / MANIFEST) or {}
    before = {m["path"]: m.get("candidateId") for m in manifest.get("media") or []
              if m.get("path") and (ctx.root / m["path"]).is_file()}         # path → what it shows
    state.update(status="haciendo", startedAt=time.time(), mediaBefore=before)
    _write(ctx.work_dir / STATE, state)


def resumed(ctx: Any) -> None:
    """A run with YouTube of a video that waited for it."""

    state = _read(ctx.work_dir / STATE)
    if state and state.get("status") == "pendiente":
        state.update(status="reanudado", resumedAt=time.time())
        _write(ctx.work_dir / STATE, state)


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def kept(ctx: Any) -> dict[str, Any]:
    """shot → its previous Selection, for the shots whose YouTube clip is already in work/<slug>/media/: without
    YouTube the judge keeps exactly that choice (so the ingest keeps the file)."""

    from .ingest import MANIFEST, OUTPUT
    from .schemas import IngestFile, SelectionFile

    try:
        selections = SelectionFile.model_validate(ctx.read_json("selection.json")).selections
        media = {m.shotId: m for m in IngestFile.model_validate_json(
            (ctx.work_dir / OUTPUT / MANIFEST).read_text("utf-8")).media}
    except (OSError, ValueError):
        return {}
    out = {}
    for s in selections:
        m = media.get(s.shotId)
        if s.status == "selected" and s.source == "youtube" and m and m.candidateId == s.candidateId \
                and (ctx.root / m.path).is_file():
            out[s.shotId] = s
    return out


# --- coverage ---------------------------------------------------------------------------------------------------

def metrics(work: Path) -> dict[str, Any] | None:
    """Coverage of one video from its work files: shots, ended in the fallback, covered by nothing, cold open."""

    selection = _read(work / "selection.json")
    fallback = _read(work / "fallback.json")
    if not selection or fallback is None:
        return None
    shots = len(selection.get("selections") or [])
    if not shots:
        return None
    items = fallback.get("items") or []
    unresolved = fallback.get("unresolved") or {}
    coldopen = _read(work / "coldopen.json") or {}
    return {"shots": shots, "toFallback": round((len(items) + len(unresolved)) / shots, 3),
            "unfilled": round(len(unresolved) / shots, 3), "coldOpen": bool(coldopen.get("clips")),
            "moments": len(coldopen.get("moments") or [])}


def reference(root: Path, channel: str | None, exclude: str, count: int = 10, minimum: int = 3) -> dict[str, Any]:
    """The usual of the channel's last `count` finished videos made with YouTube (all channels when it has fewer
    than `minimum`): medians of the fallback and uncovered shares, and how many had a cold open."""

    from . import agenda
    from .housekeeping import is_done

    videos = [v for v in agenda.videos(root) if v["slug"] != exclude and is_done(root, v["slug"])
              and (_read(root / "work" / v["slug"] / STATE) or {}).get("status") != "hecho sin YouTube"]
    videos.sort(key=lambda v: (root / "work" / v["slug"]).stat().st_mtime if (root / "work" / v["slug"]).is_dir() else 0,
                reverse=True)
    for scope, pool in (("canal", [v for v in videos if v["channel"] == channel]), ("todos los canales", videos)):
        rows = [m for v in pool[:count * 3] for m in [metrics(root / "work" / v["slug"])] if m][:count]
        if len(rows) >= minimum:
            return {"scope": scope, "videos": len(rows),
                    "toFallback": round(statistics.median(r["toFallback"] for r in rows), 3),
                    "unfilled": round(statistics.median(r["unfilled"] for r in rows), 3),
                    "coldOpen": round(sum(r["coldOpen"] for r in rows) / len(rows), 3)}
    return {"scope": "sin vídeos de referencia", "videos": 0}


def coverage(ctx: Any) -> dict[str, Any]:
    """Where every footage shot's material came from in this run, and what the run asked YouTube (must be 0)."""

    from .ingest import MANIFEST, OUTPUT

    state = _read(ctx.work_dir / STATE) or {}
    since = float(state.get("startedAt") or 0)
    before = state.get("mediaBefore") or {}
    selections = (_read(ctx.work_dir / "selection.json") or {}).get("selections") or []
    media = {m["shotId"]: m for m in (_read(ctx.work_dir / OUTPUT / MANIFEST) or {}).get("media") or []}
    fallback = _read(ctx.work_dir / "fallback.json") or {}
    items = {i["shotId"]: i for i in fallback.get("items") or []}
    unresolved = fallback.get("unresolved") or {}
    reused = alternative = 0
    sources: dict[str, int] = {}
    for s in selections:
        sid = s["shotId"]
        if sid in items:
            alternative += 1
            name = f"relleno: {items[sid].get('method')}"
        elif sid in media and s.get("status") == "selected":
            if before.get(media[sid].get("path"), "?") == media[sid].get("candidateId"):
                reused += 1
                name = "clip ya descargado"
            else:
                alternative += 1
                name = str(media[sid].get("source") or "?")
        else:
            continue
        sources[name] = sources.get(name, 0) + 1
    requests = 0
    log = ctx.work_dir / "youtube_downloads.jsonl"
    if log.is_file():
        for line in log.read_text("utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            # the files («archivo …») are what the requests brought (or a cut of a file already on disk)
            requests += float(row.get("ts") or 0) >= since and not str(row.get("action", "")).startswith("archivo")
    coldopen = _read(ctx.work_dir / "coldopen.json") or {}
    return {"shots": len(selections), "reused": reused, "alternative": alternative, "unfilled": sorted(unresolved),
            "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])), "youtubeRequests": int(requests),
            "clipsBefore": len(before), "clipsKept": sum((ctx.root / p).is_file() for p in before),
            "coldOpenClips": len(coldopen.get("clips") or []), "moments": len(coldopen.get("moments") or []),
            **{k: v for k, v in (metrics(ctx.work_dir) or {}).items() if k in ("toFallback",)},
            "unfilledShare": round(len(unresolved) / len(selections), 3) if selections else 0.0}


def gate(ctx: Any) -> dict[str, Any]:
    """After coldopen, without YouTube: on to the edit only if the material is no worse than the channel's usual."""

    from . import stickman
    from .coldopen import opening_seconds

    if stickman.active(ctx):                     # drawn in code: no footage to measure
        return {}
    cfg = ctx.section("without_youtube")
    found = coverage(ctx)
    ref = reference(ctx.root, ctx.channel, ctx.slug, int(cfg.get("reference_videos", 10)),
                    int(cfg.get("reference_min_videos", 3)))
    margin = float(cfg.get("fallback_margin", 0.05))
    max_fallback = ref["toFallback"] + margin if ref.get("videos") else float(cfg.get("max_fallback_share", 0.35))
    max_unfilled = ref["unfilled"] if ref.get("videos") else float(cfg.get("max_unfilled_share", 0.0))
    usual_cold = (ref.get("coldOpen", 0) >= 0.5) if ref.get("videos") else opening_seconds(ctx) > 0
    problems = []
    if found["youtubeRequests"]:
        problems.append(f"{found['youtubeRequests']} peticiones a YouTube durante la pausa (debían ser 0)")
    if found["clipsKept"] < found["clipsBefore"]:
        problems.append(f"faltan {found['clipsBefore'] - found['clipsKept']} de los {found['clipsBefore']} clips que había")
    share = found.get("toFallback", 0.0)
    if share > max_fallback + 1e-9:
        problems.append(f"{share:.0%} de los planos acabaron en el relleno (lo normal: {max_fallback - margin if ref.get('videos') else max_fallback:.0%}"
                        + (f", +{margin:.0%} de margen" if ref.get("videos") else "") + ")")
    if found["unfilledShare"] > max_unfilled + 1e-9:
        problems.append(f"{len(found['unfilled'])} planos sin nada que los cubra ({found['unfilledShare']:.0%}; "
                        f"lo normal: {max_unfilled:.0%})")
    if usual_cold and not found["coldOpenClips"] and cfg.get("require_cold_open", True):
        problems.append("sin cold open (sus clips con sonido salen de YouTube)")
    status = "pendiente" if problems else "hecho sin YouTube"
    state = _read(ctx.work_dir / STATE) or {}
    state.update(status=status, at=time.time(), sig=signature(ctx.root, ctx.slug), coverage=found, reference=ref,
                 limits={"toFallback": round(max_fallback, 3), "unfilled": round(max_unfilled, 3), "coldOpen": usual_cold},
                 problems=problems)
    _write(ctx.work_dir / STATE, state)
    report = _markdown(ctx.slug, state)
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    (ctx.out_dir / REPORT).write_text(report, encoding="utf-8")
    print("   " + report.replace("\n", "\n   ").rstrip())
    if problems:
        raise WaitingForYouTube(f"{ctx.slug}: hecho sin YouTube queda corto ({'; '.join(problems)}): espera a que "
                                "YouTube vuelva y la cola sigue con el siguiente")
    return state


def _markdown(slug: str, state: dict[str, Any]) -> str:
    c, ref = state["coverage"], state["reference"]
    lines = [f"# {slug}: sin YouTube ({'⏸ espera a YouTube' if state['problems'] else '✅ sigue al montaje'})", "",
             f"- Planos con metraje: {c['shots']}",
             f"- Con clip ya descargado (conservado): {c['reused']}",
             f"- Con otras fuentes: {c['alternative']}"
             + (" (" + ", ".join(f"{k} {v}" for k, v in c["sources"].items() if k != "clip ya descargado") + ")" if c["sources"] else ""),
             f"- Sin cubrir: {len(c['unfilled'])}" + (f" ({', '.join(c['unfilled'][:20])})" if c["unfilled"] else ""),
             f"- Al relleno: {c.get('toFallback', 0):.0%} · límite {state['limits']['toFallback']:.0%}",
             f"- Cold open: {c['coldOpenClips']} clips · momentos con sonido original: {c['moments']}",
             f"- Peticiones a YouTube en esta ejecución: {c['youtubeRequests']}",
             f"- Clips que ya había: {c['clipsKept']} de {c['clipsBefore']} siguen en su sitio",
             f"- Referencia: {ref['scope']}" + (f" ({ref['videos']} vídeos hechos con YouTube: relleno {ref['toFallback']:.0%}, "
                                               f"sin cubrir {ref['unfilled']:.0%}, cold open en {ref['coldOpen']:.0%})"
                                               if ref.get("videos") else "")]
    if state["problems"]:
        lines += ["", "Espera a YouTube porque:", *[f"- {p}" for p in state["problems"]]]
    return "\n".join(lines) + "\n"
