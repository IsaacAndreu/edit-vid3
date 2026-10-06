"""Stage 3 — find candidate footage and images for every shot that shows footage.

Writes work/<slug>/candidates/<shot_id>.json (+ _summary.json). Per-shot files are
reused when the shot's search spec and the sourcing config are unchanged, so an
interrupted run resumes where it stopped.
"""

from __future__ import annotations

import base64
import json
import queue
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import ValidationError

from .. import library
from ..context import RunContext
from ..schemas import Shot, ShotCandidates, ShotsFile
from .common import SourceUnavailable, key
from .images import ImageSources
from .youtube import YouTubeSource


STAGE = "sourcing"
OUTPUT = "candidates"
SUMMARY = "_summary.json"
WIDENED = "búsqueda amplia hecha"


def needs_footage(shot: Shot) -> bool:
    return shot.broll is not None and shot.type in ("broll", "chapter", "split", "stat")


HYPOTHETICAL = "WHAT IF"


def hypothetical(shot: Shot) -> bool:
    """A shot of something that never happened ("¿y si…?" videos): its event starts with 'WHAT IF'. No footage
    exists, so it is illustrated with a generated image, badged as such on screen."""

    return bool(shot.broll and shot.broll.event and shot.broll.event.strip().upper().startswith(HYPOTHETICAL))


def broader(broll: Any) -> Any:
    """A wider search for a shot that found nothing: the queries not tried yet, the names alone, then the first
    words of each query («Booking.com multa CNMC suspendida Audiencia Nacional» → «Booking.com multa CNMC»)."""

    def first_words(query: str) -> str:
        words = query.split()[:3]
        while len(words) > 1 and len(words[-1]) <= 3:     # not ending on «de», «the», «en»
            words.pop()
        return " ".join(words)

    short = [first_words(q) for q in [*broll.queries, *broll.queriesLocal]]
    english = list(dict.fromkeys(q for q in [*broll.queries[2:], *broll.entities, *short[: len(broll.queries)]]
                                 if q and q not in broll.queries[:2]))
    local = list(dict.fromkeys(q for q in [*broll.queriesLocal[1:], *short[len(broll.queries):]]
                               if q and q not in broll.queriesLocal[:1]))
    if not english and not local:
        return None
    return broll.model_copy(update={"queries": english or broll.queries, "queriesLocal": local or broll.queriesLocal})


def _spec_hash(shot: Shot, cfg: dict[str, Any]) -> str:
    return key(shot.broll.model_dump() if shot.broll else None, cfg)


def _cookies_file(yt_cfg: dict[str, Any]) -> Path | None:
    if yt_cfg.get("cookies_file"):
        path = Path(str(yt_cfg["cookies_file"])).expanduser()
        if path.is_file():
            return path
    return None


def netscape_from_json(raw: str) -> str:
    """Cookies exported as JSON (browser extensions) → the Netscape cookies.txt yt-dlp reads."""

    data = json.loads(raw)
    cookies = data.get("cookies", data) if isinstance(data, dict) else data
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = str(c["domain"])
        host_only = c.get("hostOnly", not domain.startswith("."))
        expires = int(float(c.get("expirationDate") or c.get("expires") or 0))
        lines.append("\t".join([
            domain, "FALSE" if host_only else "TRUE", str(c.get("path") or "/"),
            "TRUE" if c.get("secure") else "FALSE", str(max(0, expires)), str(c["name"]), str(c.get("value", "")),
        ]))
    return "\n".join(lines) + "\n"


def browser_cookies(spec: str) -> str:
    """YouTube/Google cookies of a browser account, read at run time (always fresh): yt-dlp's
    syntax BROWSER[:PROFILE][::CONTAINER], e.g. "firefox::Cuenta1" for a Firefox container."""

    from yt_dlp.cookies import extract_cookies_from_browser

    head, _, container = spec.partition("::")
    browser, _, profile = head.partition(":")
    jar = extract_cookies_from_browser(browser.strip().lower(), profile.strip() or None,
                                       container=container.strip() or None)
    lines = ["# Netscape HTTP Cookie File"]
    for c in jar:
        if not any(d in c.domain for d in ("youtube.com", "google.com")):
            continue                                  # only what YouTube needs, nothing else of the browser
        lines.append("\t".join([c.domain, "TRUE" if c.domain.startswith(".") else "FALSE", c.path or "/",
                                "TRUE" if c.secure else "FALSE", str(int(c.expires or 0)), c.name, c.value or ""]))
    return "\n".join(lines) + "\n"


def cookie_folders(ctx: RunContext, yt_cfg: dict[str, Any]) -> list[Path]:
    """Where cookies of several accounts are looked for: <project>/cookies/ (git-ignored) and
    youtube.cookies_dir (~/.config/edit-vid3/cookies by default)."""

    folders = [ctx.root / "cookies"]
    if yt_cfg.get("cookies_dir"):
        folders.append(Path(str(yt_cfg["cookies_dir"])).expanduser())
    return folders


def cookie_sets(ctx: RunContext, yt_cfg: dict[str, Any]) -> list[tuple[str, Path | None]]:
    """Every YouTube account available: YOUTUBE_COOKIES_B64, youtube.cookies_file and each .txt in
    youtube.cookies_dir (one per secondary account), in that order, without duplicates."""

    sets: list[tuple[str, Path | None]] = []
    encoded = ctx.env("YOUTUBE_COOKIES_B64", required=False)
    if encoded:
        sets.append((base64.b64decode(encoded).decode("utf-8"), None))
    files = []
    if _cookies_file(yt_cfg):
        files.append(_cookies_file(yt_cfg))
    for folder in cookie_folders(ctx, yt_cfg):
        if folder.is_dir():
            for exported in sorted(folder.glob("*.json")):          # JSON export → cookies.txt next to it
                target = exported.with_suffix(".txt")
                if not target.is_file() or target.stat().st_mtime < exported.stat().st_mtime:
                    try:
                        target.write_text(netscape_from_json(exported.read_text(encoding="utf-8")), encoding="utf-8")
                    except (ValueError, KeyError, TypeError) as error:
                        print(f"   Aviso: no entiendo las cookies de {exported.name} ({error})")
            files += sorted(p for p in folder.glob("*.txt") if p.is_file())
    for spec in yt_cfg.get("browser_accounts") or []:             # e.g. "firefox::Cuenta1" (container)
        try:
            text = browser_cookies(str(spec))
        except Exception as error:
            print(f"   Aviso: no pude leer las cookies de {spec} ({str(error)[:120]})")
            continue
        if "youtube.com" in text:
            sets.append((text, None))
        else:
            print(f"   Aviso: {spec} no tiene sesión de YouTube (entra en youtube.com con esa cuenta)")
    seen = set()
    for path in files:
        text = path.read_text(encoding="utf-8")
        if text.lstrip().startswith(("[", "{")):                     # JSON pasted into a .txt
            try:
                text = netscape_from_json(text)
                path.write_text(text, encoding="utf-8")
            except (ValueError, KeyError, TypeError) as error:
                print(f"   Aviso: no entiendo las cookies de {path.name} ({error})")
                continue
        if text.strip() and text not in seen:
            seen.add(text)
            sets.append((text, path))
    return sets


def youtube_source(ctx: RunContext) -> YouTubeSource:
    """A YouTubeSource with this project's config and every cookies account; call .close() when done."""

    import inspect

    yt_cfg = ctx.section("sourcing").get("youtube", {})
    mode = yt_cfg.get("cookies", "rotate")
    mode = "fallback" if mode is False else "rotate" if mode is True else str(mode or "rotate").lower()
    sets = cookie_sets(ctx, yt_cfg) if mode != "never" else []
    if mode == "never":
        print("   YouTube: sin cuenta (cookies: never)")
    elif sets and mode == "fallback":
        print(f"   YouTube: sin cuenta; {len(sets)} cuenta(s) de reserva si YouTube pide cuenta o «no eres un bot»")
    elif sets:
        print(f"   YouTube: {len(sets)} cuenta(s) de cookies, por turnos: "
              + ", ".join(path.name if path else "navegador/entorno" for _, path in sets))
    else:
        print("   YouTube: sin cookies (busco archivos .txt/.json en "
              + " y ".join(str(f) for f in cookie_folders(ctx, yt_cfg)) + ")")
    source = YouTubeSource(root=ctx.root, cache_dir=ctx.cache_dir, config=yt_cfg, cookie_sets=sets)
    source.metrics_path = ctx.work_dir / "youtube_downloads.jsonl"
    caller = inspect.stack()[1].filename
    source.stage = Path(caller).parent.name if Path(caller).stem == "__init__" else Path(caller).stem
    if source.pot:
        print(f"   YouTube: PO Token Provider activo · clientes {', '.join(source.clients)}")
    if yt_cfg.get("api_search", True):
        from ..ytapi import YouTubeAPI

        api = YouTubeAPI(ctx)
        if api.keys:
            quota = api.quota()
            if quota["searchesLeft"] > 0:
                source.api = api
                print(f"   YouTube: búsquedas con la API ({len(api.keys)} claves, ~{quota['searchesLeft']} búsquedas libres hoy)")
    return source


class Precomputer:
    """Computes stage 4's per-source CLIP features while sourcing waits on the network.

    Sourcing is I/O-bound and analysis's coarse pass is CPU-bound, so doing the latter in a
    background thread as candidates arrive makes it almost free. Results land in the same
    global cache stage 4 reads; if the analysis dependencies are missing it silently no-ops.
    """

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.queue: queue.Queue = queue.Queue()
        self.done = 0
        self.busy_seconds = 0.0
        self.error: str | None = None
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def submit(self, candidates: list) -> None:
        for candidate in candidates:
            self.queue.put(candidate)

    def _work(self) -> None:
        try:
            from ..analysis import image_features, make_models, video_features

            clip, detectors = make_models(self.ctx)
        except Exception as error:  # torch/open_clip not installed, etc.
            self.error = str(error)[:160]
            clip = None
        cfg = self.ctx.section("analysis")
        while True:
            candidate = self.queue.get()
            if candidate is None:
                return
            if clip is None:
                continue
            began = time.monotonic()
            try:
                if candidate.kind == "video":
                    video_features(clip, candidate, self.ctx.root, cfg)
                else:
                    image_features(clip, detectors, candidate, self.ctx.root)
                self.done += 1
            except Exception as error:
                self.error = f"{candidate.id}: {str(error)[:120]}"
            self.busy_seconds += time.monotonic() - began

    def finish(self) -> None:
        began = time.monotonic()
        self.queue.put(None)
        self.thread.join()
        extra = time.monotonic() - began
        print(f"   Precálculo CLIP: {self.done} fuentes ({self.busy_seconds:.0f} s de CPU, {extra:.0f} s de espera al final)")
        if self.error:
            print(f"   Aviso precálculo: {self.error}")


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
    youtube = youtube_source(ctx) if yt_cfg.get("enabled", True) else None
    if youtube is not None and ctx.section("content").get("title_blocklist") is not None:
        youtube.cfg = {**youtube.cfg, "title_blocklist": ctx.section("content")["title_blocklist"]}
    images = ImageSources(
        root=ctx.root,
        cache_dir=ctx.cache_dir,
        config=cfg.get("images", {}),
        pixabay_key=ctx.env("PIXABAY_API_KEY", required=False),
        serper_key=ctx.env("SERPER_API_KEY", required=False),
    )

    precompute = Precomputer(ctx) if ctx.section("analysis").get("precompute_during_sourcing", True) else None

    def process(shot: Shot) -> ShotCandidates:
        result = _process(shot)
        if precompute is not None:
            precompute.submit(result.candidates)
        return result

    def _process(shot: Shot) -> ShotCandidates:
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
        if hypothetical(shot):
            result = ShotCandidates(shotId=shot.id, specHash=spec_hash, queries={}, candidates=[],
                                    notes=["hipotético: se ilustra con una imagen generada"])
            ctx.write_json(f"{OUTPUT}/{shot.id}.json", result.model_dump(exclude_none=True))
            print(f"   {shot.id}: hipotético → imagen generada")
            return result
        # Sources of the same person that earlier videos already vetted (other moments of them). When the
        # library already brings a full set, one YouTube search is enough (the second video about an athlete
        # is quicker to source).
        per_shot = int(cfg.get("library_per_shot", 3))
        from_library = library.candidates_for(ctx, shot.broll, set(), per_shot)
        if youtube is not None:
            fewer = 1 if per_shot and len(from_library) >= per_shot else None
            queries["youtube"] = youtube.queries_for(shot.broll)[:fewer] if fewer else youtube.queries_for(shot.broll)
            try:
                candidates += youtube.candidates(shot.broll, notes, max_queries=fewer)
            except SourceUnavailable as error:
                notes.append(str(error))
        present = {c.id for c in candidates}
        candidates += [c for c in from_library if c.id not in present]
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

    def widen(shot: Shot, result: ShotCandidates) -> ShotCandidates:
        """Second chance for a shot with nothing: broader queries (once; the note keeps it from repeating)."""

        wide = broader(shot.broll)
        if wide is None:
            return result
        notes = [*result.notes, WIDENED]
        candidates = []
        if youtube is not None:
            try:
                candidates += youtube.candidates(wide, notes)
            except SourceUnavailable as error:
                notes.append(str(error))
        queries = {**result.queries, **{f"{k} (amplia)": v for k, v in images.queries_for(wide).items()}}
        candidates += images.search(wide, notes)[1]
        widened = ShotCandidates(shotId=shot.id, specHash=result.specHash, queries=queries, candidates=candidates,
                                 notes=notes)
        ctx.write_json(f"{OUTPUT}/{shot.id}.json", widened.model_dump(exclude_none=True))
        counts: dict[str, int] = {}
        for c in candidates:
            counts[c.source] = counts.get(c.source, 0) + 1
        print(f"   {shot.id} (búsqueda amplia): " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "nada"))
        if precompute is not None:
            precompute.submit(candidates)
        return widened

    with ThreadPoolExecutor(max_workers=int(cfg.get("parallel", 3))) as pool:
        results = list(pool.map(process, shots))
        blocked = any("bloquea" in n for r in results for n in r.notes)
        retry = [i for i, r in enumerate(results) if not r.candidates and WIDENED not in r.notes
                 and shots[i].broll is not None and not hypothetical(shots[i])]
        if retry and not blocked and cfg.get("widen_empty", True):
            print(f"   {len(retry)} planos sin candidatos: segunda búsqueda más amplia…")
            for i, widened in zip(retry, pool.map(lambda i: widen(shots[i], results[i]), retry)):
                results[i] = widened
    if youtube is not None:
        youtube.close()
        if youtube.stats:
            print(f"   Tiempos YouTube: {youtube.stats_line()}")
    if precompute is not None:
        precompute.finish()

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
    # YouTube blocked this machine half way (negocio2, after raising the downloads at once: 109 of 299 shots left
    # with nothing): going on makes a video of chalkboards. Stop; the next run searches again (retry_if) once the
    # block is over — failed searches are never cached.
    if any("bloquea" in n for n in notes) and ctx.section("sourcing").get("youtube", {}).get("stop_when_blocked", True):
        from ..ytpause import YouTubeBlocked

        raise YouTubeBlocked(
            f"YouTube ha bloqueado las búsquedas a mitad ({len(empty)} de {len(results)} planos sin candidatos). "
            "Suele pasar al pedir demasiado a la vez: baja sourcing.youtube.concurrency y espera unas horas; "
            "el vídeo se reintenta solo y vuelve a buscar.")


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
