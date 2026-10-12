"""Scene-level YouTube search (sourcing/scenes.py), its wiring in the sourcing stage and the offline comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.context import RunContext
from pipeline.schemas import BrollSpec, Candidate, ShotsFile, Storyboard
from pipeline.sourcing.scenes import finalists, group_scenes, scene_queries, scene_settings, shot_order

BOARD = Storyboard(sheets=["cache/sb/000.jpg"], columns=3, rows=3, tileWidth=320, tileHeight=180, interval=5.0, frames=9)


def _broll(event, first, second, local="clip local", moment=None, entities=()):
    return {"visualIntent": "x" * 5, "queries": [first, second, "third generic query"], "queriesLocal": [local],
            "entities": list(entities), "event": event, "moment": moment}


def _plan(brolls_by_chapter: list[list[dict]]) -> ShotsFile:
    shots, t, word = [], 0.0, 0
    for chapter, brolls in enumerate(brolls_by_chapter):
        for broll in brolls:
            shots.append({"id": f"s{len(shots) + 1:03d}", "type": "broll", "startWord": word, "endWord": word,
                          "start": t, "end": t + 2.0, "text": "palabra", "chapter": chapter, "broll": broll})
            t += 2.0
            word += 1
    chapters = [{"title": f"Capítulo {i}", "startWord": 0, "fromScript": True} for i in range(len(brolls_by_chapter))]
    return ShotsFile.model_validate({"slug": "v", "title": "v", "durationSeconds": t, "chapters": chapters,
                                     "shots": shots})


YULO = "Carlos Yulo Paris 2024 floor gold"


def test_scenes_follow_chapter_and_event_and_split_evenly():
    plan = _plan([[_broll(YULO, YULO, f"yulo shot {i}") for i in range(7)] + [_broll("Manila 2016", "manila gym", "kids")],
                  [_broll(YULO, YULO, "podium")]])
    scenes = group_scenes(plan.shots, max_shots=6)
    assert [len(scene) for scene in group_scenes(plan.shots)] == [4, 3, 1, 1]          # default: 4 at most
    assert [[s.id for s in scene] for scene in scenes] == [
        ["s001", "s002", "s003", "s004"], ["s005", "s006", "s007"],   # 7 of one event: 4 + 3, not 6 + 1
        ["s008"],                                                    # another event
        ["s009"]]                                                    # same event, next chapter: a new scene


def test_scene_queries_event_first_then_new_words_moments_first_then_local():
    plan = _plan([[_broll(YULO, YULO, "Carlos Yulo Paris 2024 floor final gold", local="Yulo oro París"),
                   _broll(YULO, YULO, "Carlos Yulo training gym Manila"),
                   _broll(YULO, YULO, "Yulo lands triple twist", moment="lands the triple twist"),
                   _broll(YULO, YULO, "crowd celebration Bercy arena", local="Yulo oro París")]])
    scene = plan.shots
    queries = scene_queries(scene, {"queries_en": 2, "scene_extra_queries": 2})
    # the near-copy of the event query adds nothing; the narrated moment goes before the rest
    assert queries == [YULO, "Yulo lands triple twist", "Carlos Yulo training gym Manila", "Yulo oro París"]
    assert scene_queries(scene, {"queries_en": 2, "scene_extra_queries": 3, "api_scene_extra_queries": 1}, api=True) == \
        [YULO, "Yulo lands triple twist"]                         # API: fewer searches, none in Spanish


def test_finalists_take_the_best_of_each_search_and_stop_trying():
    per_query = [["a", "b", "c"], ["d", "a"]]
    scores = {"a": 0.6, "b": 0.3, "c": 0.2, "d": 0.25}
    tried = []

    def accept(video_id):
        tried.append(video_id)
        return video_id != "a"

    assert finalists(per_query, scores, accept, wanted=2, max_tries=3) == ["d", "b"]
    assert tried == ["a", "d", "b"]                               # the best of each search first, then by score
    tried.clear()
    assert finalists(per_query, scores, lambda v: tried.append(v) or False, wanted=2, max_tries=2) == []
    assert len(tried) == 2                                        # never more extractions than max_tries


def test_each_shot_orders_the_scene_finalists_by_its_own_words():
    plan = _plan([[_broll(YULO, YULO, "Carlos Yulo podium medal ceremony")]])
    titles = {"a": "Carlos Yulo full floor routine", "b": "Carlos Yulo medal ceremony podium Paris"}
    assert [v for v, _ in shot_order(plan.shots[0], ["a", "b"], titles, {"a": 0.5, "b": 0.45})] == ["b", "a"]


def test_bigger_scenes_get_more_finalists():
    assert scene_settings({}, 1) == (4, 4, 5) and scene_settings({}, 4) == (4, 5, 6)
    assert scene_settings({"scene_videos_max": 5}, 6)[1] == 5


def test_shots_can_get_the_finalists_in_turns():
    from pipeline.sourcing.scenes import share_out

    plan = _plan([[_broll(YULO, YULO, f"yulo {w}") for w in ("vault", "rings", "bars")]])
    titles = {v: "Carlos Yulo" for v in "abcd"}
    scores = {"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6}
    shared = share_out(plan.shots, list("abcd"), titles, scores, 2)
    assert [[v for v, _ in shared[s.id]] for s in plan.shots] == [["a", "b"], ["a", "c"], ["a", "d"]]
    assert all(len(v) == 4 for v in share_out(plan.shots, list("abcd"), titles, scores, 0).values())


def test_judge_variety_margin_prefers_a_source_not_on_screen_yet():
    from types import SimpleNamespace

    from pipeline.judge import prefer_variety

    options = [SimpleNamespace(candidateId="yt:a", total=0.50), SimpleNamespace(candidateId="yt:b", total=0.49),
               SimpleNamespace(candidateId="yt:c", total=0.40)]
    shown = [SimpleNamespace(candidateId="yt:a")]
    assert prefer_variety(options, shown, 0).candidateId == "yt:a"          # off by default: as before
    assert prefer_variety(options, shown, 0.02).candidateId == "yt:b"       # nearly as good and new on screen
    assert prefer_variety(options[::2], shown, 0.02).candidateId == "yt:a"  # the new one is much worse: keep the best
    assert prefer_variety(options, [], 0.02).candidateId == "yt:a" and prefer_variety([], shown, 0.02) is None


def _candidate(video_id: str, title: str) -> Candidate:
    return Candidate(id=f"yt:{video_id}", source="youtube", kind="video", url=f"https://youtu.be/{video_id}", title=title,
                     channel="Olympics", license="youtube-standard", credit="Fuente: Olympics", attribution="a",
                     durationSeconds=300, query="q", rankScore=0.1, storyboard=BOARD)


def test_sourcing_stage_searches_once_per_scene(tmp_path, monkeypatch):
    import pipeline.sourcing as sourcing

    plan = _plan([[_broll(YULO, YULO, f"Carlos Yulo moment {w}") for w in ("vault", "rings", "bars")]])
    ctx = RunContext.create("v", root=tmp_path, config={
        "sourcing": {"parallel": 2, "youtube": {"scene_search": True, "scene_videos": 1, "scene_videos_per_shot": 0.5},
                     "images": {}},
        "analysis": {"precompute_during_sourcing": False}, "content": {}})
    ctx.write_json("shots.json", plan.model_dump(exclude_none=True))
    searched, extracted = [], []

    class FakeYouTube:
        api = None
        stats = {"search": [2, 1.0]}

        def search_pool(self, queries, notes):
            searched.extend(queries)
            return [["AAAAAAAAAAA", "BBBBBBBBBBB"], ["CCCCCCCCCCC"]], {
                v: {"id": v, "title": f"Carlos Yulo {v}", "query": queries[0]} for v in ("AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC")}

        def candidate(self, video_id, entry, score, notes):
            extracted.append(video_id)
            return _candidate(video_id, entry["title"])

        def close(self):
            pass

        def stats_line(self):
            return ""

    class NoImages:
        def __init__(self, **_):
            pass

        def search(self, broll, notes):
            return {}, []

    monkeypatch.setattr(sourcing, "youtube_source", lambda c: FakeYouTube())
    monkeypatch.setattr(sourcing, "ImageSources", NoImages)
    monkeypatch.setattr(sourcing.library, "candidates_for", lambda *a, **k: [])
    sourcing.run(ctx)
    assert len(searched) == len(set(searched)) <= 4                  # one scene: its searches once, not per shot
    assert len(extracted) == 3                                      # 1 + 0.5 × 3 shots → 3 finalists, details once each
    files = [json.loads((ctx.work_dir / "candidates" / f"s00{i}.json").read_text()) for i in (1, 2, 3)]
    assert all(len(f["candidates"]) == 3 and "escena s001-s003" in f["notes"] for f in files)
    summary = json.loads((ctx.work_dir / "candidates" / "_summary.json").read_text())
    assert summary["sceneSearch"] and summary["youtubeRequests"] == {"search": 2}
    extracted.clear()
    sourcing.run(ctx)                                               # done: nothing is asked again
    assert extracted == []


def test_offline_comparison_makes_no_request_and_keeps_its_fixed_set(tmp_path, monkeypatch):
    from pipeline import scenebench
    from pipeline.sourcing.common import key

    plan = _plan([[_broll(YULO, YULO, f"Carlos Yulo moment {w}") for w in ("vault", "rings", "bars", "floor")]])
    work = tmp_path / "work" / "v"
    (work / "candidates").mkdir(parents=True)
    (work / "shots.json").write_text(plan.model_dump_json(exclude_none=True))
    (work / "selection.json").write_text(json.dumps({"selections": [
        {"shotId": "s001", "status": "selected", "candidateId": "yt:AAAAAAAAAAA"}]}))
    (tmp_path / "config.yaml").write_text("sourcing:\n  youtube: {min_interval: 0}\n")
    cache = tmp_path / "cache"
    search = cache / "search" / "youtube"
    search.mkdir(parents=True)
    entry = lambda v: {"id": v, "title": f"Carlos Yulo {v}", "channel": "Olympics", "duration": 300,  # noqa: E731
                       "url": f"https://www.youtube.com/watch?v={v}"}
    for query in (YULO, "Carlos Yulo moment vault"):
        (search / f"{key(query, 8)}.json").write_text(json.dumps([entry("AAAAAAAAAAA"), entry("BBBBBBBBBBB")]))

    def no_network(*_, **__):
        raise AssertionError("the comparison must not ask YouTube")

    monkeypatch.setattr("pipeline.sourcing.youtube.YouTubeSource._extract", no_network)
    result = scenebench.run(tmp_path, api=False, visual=False)
    old, new = result["set"]["old"], result["set"]["new"]
    assert old["shots"] == new["shots"] == 4
    assert new["searches"] < old["searches"] and new["searchesWithoutData"] < old["searchesWithoutData"]
    assert old["judgeChoiceKept"] == 1.0 and new["judgeChoiceKept"] == 1.0
    fixed = json.loads((tmp_path / scenebench.BANK).read_text())["scenes"]
    assert fixed == [{"video": "v", "shots": ["s001", "s002", "s003", "s004"]}]
    assert "Búsquedas" in scenebench.report(result)
    assert scenebench.bank(tmp_path, ["v"], 30) == fixed             # kept: the next comparison uses the same set


def test_simulated_pick_counts_repeats_and_the_variety_margin_lowers_them():
    from pipeline.scenebench import _visual_measures

    options = {f"v/s00{i}": ["a", "b"] for i in range(1, 5)}
    sims = {k: {"a": 0.40, "b": 0.39} for k in options}
    plain = _visual_measures(options, sims, 0.2, {"v": 5})
    varied = _visual_measures(options, sims, 0.2, {"v": 5}, margin=0.02)
    assert plain["simulatedSources"] == 1 and plain["simulatedRepeats"] == 0.75 and plain["visualBest"] == 0.4
    assert varied["simulatedSources"] == 2 and varied["simulatedRepeats"] == 0.5
    assert _visual_measures(options, sims, 0.2, {"v": 2})["simulatedSources"] == 2      # the per-source cap
