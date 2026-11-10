"""Scene-level YouTube search (`sourcing.scene_search`, off by default; the per-shot search stays as the reference).

A scene is a run of consecutive footage shots of the same chapter and the same story event (the planner gives every
sentence of an event the same `event`), cut into pieces of at most `scene_max_shots` (4: with 6, replayed on two
videos, the same few sources filled twice as many shots). The scene searches once — its
event query, a couple of the shots' own queries that add something new (a narrated moment first) and one in the
script's language — ranks everything found together and extracts the details of only a few finalists
(`scene_videos` + `scene_videos_per_shot` per shot, up to `scene_videos_max`; one try more at most). Every shot of the scene gets those finalists, ordered
by how well each title matches that shot's own queries; the judge then picks the moment of each one per shot.

Per shot the old way asked 2-3 searches and up to 3 videos' details (each extraction is one request YouTube can
answer with «are you a bot»); a scene of 4 shots asks ~5 searches and ~5 extractions. On two past documentaries,
replayed offline (scenebench.py): ~850 requests → ~460 (searches 380-460 → 215-250, extractions 360-500 → 225-235),
the same CLIP quality, and — with `judge.variety_margin: 0.02` — about as many different sources on screen. `python main.py
--comparar-escenas` measures both on the same fixed set of scenes, offline (scenebench.py).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Callable

from ..schemas import Shot
from .common import fuse_ranks, tokens


def _event(shot: Shot) -> str:
    return " ".join(str(shot.broll.event or "").casefold().split()) if shot.broll else ""


def group_scenes(shots: list[Shot], max_shots: int = 6) -> list[list[Shot]]:
    """Consecutive shots of one chapter and one event, in balanced pieces of at most max_shots. Shots without an
    event (an intro montage) group by chapter only: their own queries still go into the scene's search."""

    runs: list[list[Shot]] = []
    for shot in shots:
        if runs and runs[-1][-1].chapter == shot.chapter and _event(runs[-1][-1]) == _event(shot):
            runs[-1].append(shot)
        else:
            runs.append([shot])
    scenes: list[list[Shot]] = []
    for run in runs:
        pieces = max(1, math.ceil(len(run) / max(1, max_shots)))
        size = math.ceil(len(run) / pieces)
        scenes += [run[i:i + size] for i in range(0, len(run), size)]
    return scenes


def _novel(query: str, chosen: list[str], limit: float = 0.6) -> bool:
    words = tokens(query)
    if not words:
        return False
    for other in chosen:
        others = tokens(other)
        if others and len(words & others) / len(words | others) >= limit:
            return False
    return True


def scene_queries(scene: list[Shot], cfg: dict[str, Any], api: bool = False) -> list[str]:
    """The scene's searches: the most shared first query (the event), then the shots' own queries that add new
    words (narrated moments first), then the most shared query in the script's language."""

    brolls = [s.broll for s in scene if s.broll]
    if not brolls:
        return []
    firsts = Counter(b.queries[0] for b in brolls)
    anchor = max(firsts, key=lambda q: (firsts[q], -[b.queries[0] for b in brolls].index(q)))
    extra = int(cfg.get("scene_extra_queries", 3))
    if api:          # each API search costs 100 units and one of the day's searches
        extra = min(extra, int(cfg.get("api_scene_extra_queries", 2)))
    chosen = [anchor]
    ordered = [b for b in brolls if b.moment] + [b for b in brolls if not b.moment]
    for broll in ordered:
        for query in broll.queries[: int(cfg.get("queries_en", 2))]:
            if len(chosen) > extra:
                break
            if query not in chosen and _novel(query, chosen):
                chosen.append(query)
    local_count = int(cfg.get("scene_local_queries", 1)) if not api else 0
    if local_count:
        locals_ = Counter(b.queriesLocal[0] for b in brolls if b.queriesLocal)
        chosen += [q for q, _ in locals_.most_common(local_count)]
    return chosen


def rank_pool(per_query: list[list[str]], entries: dict[str, dict[str, Any]], scene: list[Shot]) -> dict[str, float]:
    """Reciprocal-rank fusion of every search of the scene, +0.3 when the title names one of its people/places."""

    scores = fuse_ranks(per_query)
    entity_terms = tokens(" ".join(e for s in scene if s.broll for e in s.broll.entities))
    for video_id, entry in entries.items():
        if entity_terms and entity_terms & tokens(f"{entry.get('title')} {entry.get('channel')}"):
            scores[video_id] = scores.get(video_id, 0.0) + 0.3
    return scores


def finalists(per_query: list[list[str]], scores: dict[str, float], accept: Callable[[str], bool],
              wanted: int, max_tries: int) -> list[str]:
    """The few videos whose details are fetched: first the best of each search (so a shot's own query is not
    drowned by the event's), then by score; at most max_tries extractions whatever they answer."""

    order: list[str] = []
    for ids in sorted((ids for ids in per_query if ids), key=lambda ids: -scores.get(ids[0], 0.0)):
        fresh = [v for v in ids if v not in order]          # the best this search found that no other brought
        if fresh:
            order.append(max(fresh, key=lambda v: scores.get(v, 0.0)))
    order += [v for v in sorted(scores, key=lambda v: -scores[v]) if v not in order]
    chosen: list[str] = []
    tries = 0
    for video_id in order:
        if len(chosen) >= wanted or tries >= max_tries:
            break
        tries += 1
        if accept(video_id):
            chosen.append(video_id)
    return chosen


def shot_order(shot: Shot, ids: list[str], titles: dict[str, str], scores: dict[str, float]) -> list[tuple[str, float]]:
    """The scene's finalists for one shot: the scene score plus how much of the title matches this shot's own
    queries and moment."""

    own = tokens(" ".join([*shot.broll.queries, *shot.broll.queriesLocal, shot.broll.moment or ""])) if shot.broll else set()

    def score(video_id: str) -> float:
        words = tokens(titles.get(video_id, ""))
        return scores.get(video_id, 0.0) + (0.3 * len(words & own) / max(1, len(own)) if own else 0.0)

    return sorted(((v, round(score(v), 4)) for v in ids), key=lambda item: -item[1])


def share_out(scene: list[Shot], ids: list[str], titles: dict[str, str], scores: dict[str, float],
              per_shot: int) -> dict[str, list[tuple[str, float]]]:
    """Each shot's options among the scene's finalists: its best match, then the others in turns, so that consecutive
    shots do not all get the same few sources (all of them for every shot made the same video fill a whole scene)."""

    if per_shot <= 0 or per_shot >= len(ids):
        return {s.id: shot_order(s, ids, titles, scores) for s in scene}
    out: dict[str, list[tuple[str, float]]] = {}
    for index, shot in enumerate(scene):
        ranked = shot_order(shot, ids, titles, scores)
        mine = ranked[:1]
        rest = ranked[1:]
        start = index % len(rest) if rest else 0
        mine += (rest[start:] + rest[:start])[: per_shot - 1]
        out[shot.id] = sorted(mine, key=lambda item: -item[1])
    return out


def options_per_shot(cfg: dict[str, Any]) -> int:
    """0 (default): every finalist for every shot. Handing out fewer per shot (3) was tried: it lowered the CLIP match
    and barely changed how often sources repeat, which the judge's variety_margin does fix."""

    return int(cfg.get("scene_options_per_shot", 0))


def scene_settings(cfg: dict[str, Any], shots: int = 1) -> tuple[int, int, int]:
    """(max shots per scene, videos for a scene of `shots` shots, max extractions for it): a bigger scene needs more
    different sources, so `scene_videos` plus `scene_videos_per_shot` for each shot, up to `scene_videos_max`."""

    wanted = min(int(cfg.get("scene_videos_max", 8)),
                 int(cfg.get("scene_videos", 3)) + math.ceil(float(cfg.get("scene_videos_per_shot", 0.5)) * shots))
    return int(cfg.get("scene_max_shots", 4)), wanted, wanted + int(cfg.get("scene_extra_extracts", 1))
