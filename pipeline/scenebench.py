"""Per-shot search vs scene search on the same fixed set of scenes, offline: not one request to YouTube.

    python main.py --comparar-escenas            (or Estadísticas → «Comparar búsqueda por escenas»)

The first run picks ~30 scenes spread over the videos already sourced and keeps them in out/_banco_escenas.json, so
every later comparison (after tuning scene_videos, scene_extra_queries…) uses the same scenes. Both ways are replayed
from the disk cache of earlier runs (search results, video details); a search or a video the cache does not have is
counted as a request and noted as «sin datos» (a video without details is assumed to pass the filters).

Measures, per way: searches and extractions (the requests YouTube can answer «are you a bot»), shots left without a
YouTube option, options per shot, different sources (variety), how often the clip the judge really chose in that
video is still among the shot's options, and how well the first option's title matches the shot. With CLIP
installed, also the visual quality the analysis stage would see, from the frame embeddings already cached (no
download): the best CLIP match of each shot among its options, the share above the judge's floor (`judge.min_clip`),
and a simulated pick — each shot its best option, a source at most `judge.max_per_source` times — for how often
sources repeat on screen. Videos the old runs never analysed have no embeddings: counted apart («sin huella»). Also the same counts for whole documentaries, and the downloads the earlier
runs really made (youtube_downloads.jsonl): phase 1 does not change downloads.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .context import RunContext
from .schemas import Shot, ShotsFile
from .sourcing import hypothetical, needs_footage
from .sourcing.common import fuse_ranks, tokens
from .sourcing.scenes import (finalists, group_scenes, options_per_shot, rank_pool, scene_queries, scene_settings,
                               share_out)
from .sourcing.youtube import YouTubeSource

BANK = "out/_banco_escenas.json"
OUTPUT = "out/_comparar_escenas.json"


class _NotCached(Exception):
    pass


class _Offline:
    """A YouTubeSource that only reads the cache: every request it would make is counted, none is made."""

    def __init__(self, ctx: RunContext, api: bool) -> None:
        cfg = dict(ctx.section("sourcing").get("youtube", {}))
        if ctx.section("content").get("title_blocklist") is not None:
            cfg["title_blocklist"] = ctx.section("content")["title_blocklist"]
        self.cfg = cfg
        self.yt = YouTubeSource(root=ctx.root, cache_dir=ctx.cache_dir, config={**cfg, "cookies": "never"})
        self.yt.api = object() if api else None           # only changes how many queries a shot asks
        self.yt._api_search = lambda *a, **k: None          # type: ignore[method-assign]
        self.yt._call = self._refuse                        # type: ignore[method-assign]
        self.searches: set[str] = set()
        self.extracts: set[str] = set()
        self.missing_searches: set[str] = set()
        self.missing_extracts: set[str] = set()
        self.titles: dict[str, str] = {}

    @staticmethod
    def _refuse(*_: Any, **__: Any) -> Any:
        raise _NotCached

    def pool(self, queries: list[str]) -> tuple[list[list[str]], dict[str, dict[str, Any]]]:
        per_query, entries = [], {}
        for query in queries:
            self.searches.add(query)
            try:
                results = self.yt.search(query)
            except _NotCached:
                self.missing_searches.add(query)
                results = []
            ids = []
            for entry in results:
                if self.yt.passes_search_filters(entry):
                    entries.setdefault(entry["id"], {**entry, "query": query})
                    ids.append(entry["id"])
            per_query.append(ids)
        return per_query, entries

    def accept(self, video_id: str, entry: dict[str, Any]) -> bool:
        self.extracts.add(video_id)
        path = self.yt._info_path(video_id)
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.missing_extracts.add(video_id)
            self.titles[video_id] = str(entry.get("title") or "")
            return True
        self.titles[video_id] = str(info.get("title") or entry.get("title") or "")
        return self.yt.passes_metadata_filters(info)

    # --- the two ways ----------------------------------------------------------------------------
    def per_shot(self, shot: Shot) -> list[str]:
        """sourcing/youtube.py candidates(): its queries, then details until videos_per_shot pass."""

        per_query, entries = self.pool(self.yt.queries_for(shot.broll))
        scores = fuse_ranks(per_query)
        entity_terms = tokens(" ".join(shot.broll.entities))
        for video_id, entry in entries.items():
            if entity_terms and entity_terms & tokens(f"{entry.get('title')} {entry.get('channel')}"):
                scores[video_id] = scores.get(video_id, 0.0) + 0.3
        wanted, chosen = int(self.cfg.get("videos_per_shot", 3)), []
        for video_id in sorted(entries, key=lambda v: -scores.get(v, 0.0)):
            if len(chosen) >= wanted:
                break
            if self.accept(video_id, entries[video_id]):
                chosen.append(video_id)
        return chosen

    def per_scene(self, scene: list[Shot]) -> dict[str, list[str]]:
        per_query, entries = self.pool(scene_queries(scene, self.cfg, api=self.yt.api is not None))
        scores = rank_pool(per_query, entries, scene)
        _, wanted, tries = scene_settings(self.cfg, len(scene))
        chosen = finalists(per_query, scores, lambda v: self.accept(v, entries[v]), wanted, tries)
        shared = share_out(scene, chosen, self.titles, scores, options_per_shot(self.cfg))
        return {s.id: [v for v, _ in shared[s.id]] for s in scene}


def _videos(root: Path, only: list[str] | None) -> list[str]:
    found = []
    for folder in sorted((root / "work").glob("*")):
        if (folder / "shots.json").is_file() and (folder / "candidates").is_dir() and not folder.name.startswith("_"):
            if not only or folder.name in only:
                found.append(folder.name)
    return found


def _shots(ctx: RunContext) -> list[Shot]:
    shots = ShotsFile.model_validate(ctx.read_json("shots.json")).shots
    return [s for s in shots if needs_footage(s) and not hypothetical(s)]


def _chosen(ctx: RunContext) -> dict[str, str]:
    """shot → the YouTube video the judge put on screen in that run."""

    try:
        selection = ctx.read_json("selection.json")
    except (OSError, ValueError):
        return {}
    return {s["shotId"]: str(s["candidateId"])[3:] for s in selection.get("selections", [])
            if s.get("status") == "selected" and str(s.get("candidateId", "")).startswith("yt:")}


def bank(root: Path, videos: list[str], size: int) -> list[dict[str, Any]]:
    """The fixed set: kept on disk once made (delete out/_banco_escenas.json to pick again)."""

    path = root / BANK
    if path.is_file():
        try:
            kept = json.loads(path.read_text(encoding="utf-8"))["scenes"]
            if kept and all(s["video"] in videos for s in kept):
                return kept
        except (OSError, ValueError, KeyError):
            pass
    every = []
    for slug in videos:                                    # stretches of one event of up to 6 shots, whatever the config
        ctx = RunContext.create(slug, root=root)
        every += [{"video": slug, "shots": [s.id for s in scene]} for scene in group_scenes(_shots(ctx), 6)]
    if len(every) > size:                                  # spread evenly over every video and chapter
        every = [every[round(i * (len(every) - 1) / (size - 1))] for i in range(size)] if size > 1 else every[:1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "scenes": every}, ensure_ascii=False,
                               indent=1), encoding="utf-8")
    return every


def _measure(options: dict[str, list[str]], shots: dict[str, Shot], chosen: dict[str, str],
             offline: _Offline) -> dict[str, Any]:
    with_judge = [s for s in options if s in chosen]
    relevance = []
    for shot_id, ids in options.items():
        own = tokens(" ".join(shots[shot_id].broll.queries))
        if ids and own:
            relevance.append(len(tokens(offline.titles.get(ids[0], "")) & own) / len(own))
    return {
        "shots": len(options),
        "searches": len(offline.searches),
        "extracts": len(offline.extracts),
        "searchesWithoutData": len(offline.missing_searches),
        "extractsWithoutData": len(offline.missing_extracts),
        "shotsWithoutYouTube": sum(1 for ids in options.values() if not ids),
        "optionsPerShot": round(sum(len(ids) for ids in options.values()) / max(1, len(options)), 2),
        "differentSources": len({v for ids in options.values() for v in ids}),
        "judgeChoiceKept": (round(sum(chosen[s] in options[s] for s in with_judge) / len(with_judge), 3)
                            if with_judge else None),
        "judgeShots": len(with_judge),
        "titleMatch": round(sum(relevance) / len(relevance), 3) if relevance else None,
    }


class _Visual:
    """CLIP from the disk cache only: shot prompts are encoded (the text model is local), frames never are."""

    def __init__(self, ctx: RunContext) -> None:
        from .analysis import frames_key
        from .analysis.clip import ClipScorer

        self.cfg = ctx.section("analysis")
        self.clip = ClipScorer(cache_dir=ctx.cache_dir, model=str(self.cfg.get("model", "ViT-B-32")),
                               pretrained=str(self.cfg.get("pretrained", "laion2b_s34b_b79k")))
        self.frames_key = frames_key
        self.vectors: dict[str, Any] = {}

    def sims(self, shot: Shot, ids: list[str]) -> dict[str, float]:
        """video → its best frame's similarity to the shot; videos without cached frames are left out."""

        import numpy as np

        from .analysis import prompts_for

        if shot.id not in self.vectors:
            self.vectors[shot.id] = self.clip.shot_vector(prompts_for(shot))
        found = {}
        for video_id in ids:
            path = self.clip.cache_dir / f"{self.frames_key('yt:' + video_id, self.cfg)}.npz"
            try:
                vectors = np.load(path)["vectors"].astype(np.float32)
            except (OSError, ValueError, KeyError):
                continue
            if len(vectors):
                found[video_id] = float((vectors @ self.vectors[shot.id]).max())
        return found


RECOMMENDED_MARGIN = 0.02      # judge.variety_margin to use with the scene search


def _visual_measures(options: dict[str, list[str]], sims: dict[str, dict[str, float]], floor: float,
                     caps: dict[str, int], margin: float = 0.0) -> dict[str, Any]:
    known = {k: v for k, v in sims.items() if v}
    best = {k: max(v.values()) for k, v in known.items()}
    used: dict[str, int] = {}
    picked = []
    for shot in options:                                   # in story order, as the judge goes (judge.prefer_variety)
        ranked = [(v, sim) for v, sim in sorted(sims.get(shot, {}).items(), key=lambda item: -item[1])
                  if used.get(v, 0) < caps.get(shot.split("/")[0], 5)]
        choice = ranked[0] if ranked else None
        if choice and margin > 0 and used.get(choice[0]):
            choice = next(((v, sim) for v, sim in ranked if not used.get(v) and sim >= choice[1] - margin), choice)
        if choice and choice[1] >= floor:
            used[choice[0]] = used.get(choice[0], 0) + 1
            picked.append(choice[1])
    return {
        "visualShots": len(known),
        "visualWithoutPrint": len(options) - len(known),
        "visualBest": round(sum(best.values()) / len(best), 4) if best else None,
        "visualAboveFloor": round(sum(b >= floor for b in best.values()) / len(best), 3) if best else None,
        "simulatedFilled": len(picked),
        "simulatedSources": len(used),
        "simulatedScore": round(sum(picked) / len(picked), 4) if picked else None,
        "simulatedRepeats": round(1 - len(used) / len(picked), 3) if picked else None,
        "simulatedMargin": margin,
    }


def _real_requests(ctx: RunContext) -> dict[str, int]:
    """What the earlier run really asked YouTube (its metrics file)."""

    path = ctx.work_dir / "youtube_downloads.jsonl"
    counts: dict[str, int] = {}
    if not path.is_file():
        return counts
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        action = str(row.get("action") or "?")
        kind = "download" if action.startswith("download") else action
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def compare(root: Path, videos: list[str], scenes: list[dict[str, Any]], api: bool, visual: bool = False) -> dict[str, Any]:
    """Both ways on `scenes` (grouped by video, each video with its own config)."""

    old: dict[str, list[str]] = {}
    new: dict[str, list[str]] = {}
    meta: dict[str, Shot] = {}
    chosen: dict[str, str] = {}
    old_off: _Offline | None = None
    new_off: _Offline | None = None
    totals = {"old": {"searches": 0, "extracts": 0, "searchesWithoutData": 0, "extractsWithoutData": 0},
              "new": {"searches": 0, "extracts": 0, "searchesWithoutData": 0, "extractsWithoutData": 0}}
    merged_titles: dict[str, str] = {}
    sims: dict[str, dict[str, dict[str, float]]] = {"old": {}, "new": {}}
    caps: dict[str, int] = {}
    floor = 0.20
    margins = {"old": 0.0, "new": RECOMMENDED_MARGIN}
    for slug in videos:
        mine = [s for s in scenes if s["video"] == slug]
        if not mine:
            continue
        ctx = RunContext.create(slug, root=root)
        by_id = {s.id: s for s in _shots(ctx)}
        old_off, new_off = _Offline(ctx, api), _Offline(ctx, api)
        for scene in mine:
            shots = [by_id[i] for i in scene["shots"] if i in by_id]
            if not shots:
                continue
            for shot in shots:
                key = f"{slug}/{shot.id}"
                meta[key] = shot
                old[key] = old_off.per_shot(shot)
            # the fixed set is a set of shots: the scenes inside it follow the current scene_max_shots
            for sub in group_scenes(shots, scene_settings(new_off.cfg)[0]):
                new.update({f"{slug}/{k}": v for k, v in new_off.per_scene(sub).items()})
        chosen.update({f"{slug}/{k}": v for k, v in _chosen(ctx).items() if f"{slug}/{k}" in meta})
        if visual:
            from .judge import source_cap

            judge_cfg = ctx.section("judge")
            floor = float(judge_cfg.get("min_clip", 0.20))
            margins = {"old": float(judge_cfg.get("variety_margin", 0) or 0),
                       "new": float(judge_cfg.get("variety_margin", 0) or 0) or RECOMMENDED_MARGIN}
            caps[slug] = source_cap(judge_cfg, len(by_id))
            seer = _Visual(ctx)
            for name, options in (("old", old), ("new", new)):
                for shot_key, ids in options.items():
                    if shot_key.startswith(slug + "/"):
                        sims[name][shot_key] = seer.sims(meta[shot_key], ids)
        for name, off in (("old", old_off), ("new", new_off)):
            totals[name]["searches"] += len(off.searches)
            totals[name]["extracts"] += len(off.extracts)
            totals[name]["searchesWithoutData"] += len(off.missing_searches)
            totals[name]["extractsWithoutData"] += len(off.missing_extracts)
            merged_titles.update(off.titles)
    holder = _Offline.__new__(_Offline)
    holder.titles = merged_titles
    holder.searches, holder.extracts, holder.missing_searches, holder.missing_extracts = set(), set(), set(), set()
    result = {}
    for name, options in (("old", old), ("new", new)):
        measured = _measure(options, meta, chosen, holder)
        measured.update(totals[name])
        if visual:
            measured.update(_visual_measures(options, sims[name], floor, caps, margins[name]))
        result[name] = measured
    return result


def _has_clip() -> bool:
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    return True


def run(root: Path, only: list[str] | None = None, size: int = 30, api: bool | None = None,
        visual: bool | None = None) -> dict[str, Any]:
    videos = _videos(root, only)
    visual = _has_clip() if visual is None else visual
    if not videos:
        raise SystemExit("No hay vídeos con búsquedas hechas en work/ para comparar.")
    if api is None:
        api = bool(RunContext.create(videos[0], root=root).env("YOUTUBE_API_KEY", required=False)
                   or RunContext.create(videos[0], root=root).env("YOUTUBE_API_KEYS", required=False))
    fixed = bank(root, videos, size)
    result: dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "api": api, "scenes": len(fixed),
                              "visual": visual, "set": compare(root, videos, fixed, api, visual), "videos": []}
    for slug in videos:                                    # whole documentaries: the per-video goal
        ctx = RunContext.create(slug, root=root)
        max_shots = scene_settings(ctx.section("sourcing").get("youtube", {}))[0]
        every = [{"video": slug, "shots": [s.id for s in scene]} for scene in group_scenes(_shots(ctx), max_shots)]
        whole = compare(root, [slug], every, api)
        result["videos"].append({"video": slug, "scenes": len(every), "old": whole["old"], "new": whole["new"],
                                 "realRequests": _real_requests(ctx)})
    target = root / OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


VISUAL_ROWS = [("visualBest", "CLIP: mejor opción del plano"), ("visualAboveFloor", "CLIP: planos sobre el mínimo del juez"),
               ("simulatedFilled", "Simulado: planos cubiertos"), ("simulatedSources", "Simulado: fuentes en pantalla"),
               ("simulatedRepeats", "Simulado: repetición de fuentes"), ("simulatedScore", "Simulado: CLIP medio elegido"),
               ("visualWithoutPrint", "Planos sin huella CLIP en caché"),
               ("simulatedMargin", "Simulado: judge.variety_margin")]
ROWS = [("searches", "Búsquedas"), ("extracts", "Extracciones (detalles)"), ("shotsWithoutYouTube", "Planos sin YouTube"),
        ("optionsPerShot", "Opciones por plano"), ("differentSources", "Fuentes distintas"),
        ("judgeChoiceKept", "Elección real del juez conservada"), ("titleMatch", "Título ↔ plano"),
        ("searchesWithoutData", "Búsquedas sin datos en caché"), ("extractsWithoutData", "Vídeos sin datos en caché")]


def report(result: dict[str, Any]) -> str:
    lines = [f"Conjunto fijo: {result['scenes']} escenas ({result['set']['old']['shots']} planos)"
             + (" · modo API" if result["api"] else ""), f"{'':38}{'por plano':>12}{'por escena':>12}"]
    for key, label in ROWS + (VISUAL_ROWS if result.get("visual") else []):
        lines.append(f"{label:38}{str(result['set']['old'].get(key)):>12}{str(result['set']['new'].get(key)):>12}")
    lines.append("")
    lines.append("Documentales enteros (búsquedas / extracciones; antes → escenas; real = lo que pidió aquella vez):")
    for video in result["videos"]:
        real = video["realRequests"]
        lines.append(f"  {video['video']}: {video['old']['shots']} planos en {video['scenes']} escenas · "
                     f"{video['old']['searches']}/{video['old']['extracts']} → {video['new']['searches']}/"
                     f"{video['new']['extracts']}" + (f" · real: {real}" if real else ""))
    return "\n".join(lines)
