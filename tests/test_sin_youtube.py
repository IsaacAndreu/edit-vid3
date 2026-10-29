"""The queue goes on without YouTube while it is paused (pipeline/sin_youtube.py): no request, nothing lost, the
coverage measured, short videos wait and resume later."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import main
from pipeline import runner, sin_youtube
from pipeline.context import RunContext
from pipeline.runner import Stage, run_stages
from pipeline.schemas import Candidate, Option, ShotCandidates, ShotScores
from pipeline.sourcing.common import SourceUnavailable
from pipeline.sourcing.youtube import YouTubeSource

from tests.test_scenes import BOARD, _broll, _plan


@pytest.fixture
def offline():
    with sin_youtube.offline():
        yield


def _materials(root: Path, slug: str, channel: str | None = None) -> None:
    folder = root / "materiales" / slug
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("hola")
    (folder / "voz.mp3").write_bytes(b"x")
    if channel:
        (folder / "config.yaml").write_text(f"canal: {channel}\n")


def _pause(root: Path) -> None:
    (root / "out").mkdir(parents=True, exist_ok=True)
    (root / "out" / "_pausa_youtube").write_text('{"reason": "bot"}')


# --- not one request ------------------------------------------------------------------------------------------

def test_without_youtube_nothing_goes_out_and_what_is_on_disk_is_still_read(tmp_path, offline):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0})
    yt.metrics_path = tmp_path / "log.jsonl"
    asked = []
    with pytest.raises(SourceUnavailable, match=sin_youtube.NOTE):
        yt._call("search", lambda: asked.append(1))
    with pytest.raises(SourceUnavailable):
        yt._get("https://i.ytimg.com/sb/x.jpg")
    with pytest.raises(SourceUnavailable):
        yt._api_search("query", 8)
    with pytest.raises(SourceUnavailable):
        yt.download_section("abcdefghijk", 10, 15)               # not on disk: it cannot come
    clip = tmp_path / "videos" / "abcdefghijk" / "a360_9.000_16.000.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x")
    assert yt.download_section("abcdefghijk", 10, 15) == clip     # on disk: used as always
    search = tmp_path / "search" / "youtube"
    search.mkdir(parents=True)
    from pipeline.sourcing.common import key

    (search / f"{key('cached query', 8)}.json").write_text('[{"id": "abcdefghijk"}]')
    assert yt.search("cached query") == [{"id": "abcdefghijk"}]
    assert asked == [] and not yt.metrics_path.exists()          # no request, and no «failed download» logged
    assert yt.captions("zzzzzzzzzzz") == []


def test_with_youtube_the_source_is_as_before(tmp_path):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0})
    assert yt.offline is None and yt._call("search", lambda: 7) == 7


# --- sourcing: kept while paused, searched again after -------------------------------------------------------

def _sourcing(tmp_path, monkeypatch, youtube):
    import pipeline.sourcing as sourcing

    plan = _plan([[_broll("e", "first query", "second query")]])
    ctx = RunContext.create("v", root=tmp_path, config={"sourcing": {"images": {}, "youtube": {}},
                                                         "analysis": {"precompute_during_sourcing": False}, "content": {}})
    ctx.write_json("shots.json", plan.model_dump(exclude_none=True))

    class NoImages:
        def __init__(self, **_):
            pass

        def search(self, broll, notes):
            return {}, []

        def queries_for(self, broll):
            return {}

    monkeypatch.setattr(sourcing, "youtube_source", lambda c: youtube)
    monkeypatch.setattr(sourcing, "ImageSources", NoImages)
    monkeypatch.setattr(sourcing.library, "candidates_for", lambda *a, **k: [])
    return ctx, sourcing


class FakeYouTube:
    api = None
    stats: dict = {}

    def __init__(self, offline=None):
        self.offline = offline
        self.searched = 0

    def queries_for(self, broll):
        return list(broll.queries)

    def candidates(self, broll, notes, max_queries=None):
        self.searched += 1
        if self.offline:
            raise SourceUnavailable(self.offline)
        return [Candidate(id="yt:AAAAAAAAAAA", source="youtube", kind="video", url="u", title="t", channel="c",
                          license="l", credit="Fuente: c", attribution="a", durationSeconds=60, query="q",
                          rankScore=0.1, storyboard=BOARD)]

    def close(self):
        pass


def test_a_shot_searched_without_youtube_is_searched_again_once_youtube_is_back(tmp_path, monkeypatch):
    youtube = FakeYouTube(sin_youtube.REASON)
    ctx, sourcing = _sourcing(tmp_path, monkeypatch, youtube)
    with sin_youtube.offline():
        sourcing.run(ctx)                                 # no YouTube: the shot gets the note, and no «blocked» stop
        sourcing.run(ctx)                                 # again while paused: kept, nothing searched again
    found = ShotCandidates.model_validate_json((ctx.work_dir / "candidates" / "s001.json").read_text())
    assert any(sin_youtube.NOTE in n for n in found.notes) and youtube.searched == 1
    youtube.offline = None
    sourcing.run(ctx)                                     # YouTube back: searched with it
    found = ShotCandidates.model_validate_json((ctx.work_dir / "candidates" / "s001.json").read_text())
    assert youtube.searched == 2 and [c.id for c in found.candidates] == ["yt:AAAAAAAAAAA"]


def test_a_shot_searched_with_youtube_is_never_redone_without_it(tmp_path, monkeypatch):
    youtube = FakeYouTube()
    ctx, sourcing = _sourcing(tmp_path, monkeypatch, youtube)
    sourcing.run(ctx)
    youtube.offline = sin_youtube.REASON
    with sin_youtube.offline():
        sourcing.run(ctx)
    found = ShotCandidates.model_validate_json((ctx.work_dir / "candidates" / "s001.json").read_text())
    assert youtube.searched == 1 and [c.id for c in found.candidates] == ["yt:AAAAAAAAAAA"]


# --- the judge keeps the clips already downloaded and leaves YouTube out ----------------------------------------

def _option(cid, source, total, kind="video"):
    return Option.model_validate({"candidateId": cid, "source": source, "kind": kind, "pass": "fine",
                                  "start": 1.0 if kind == "video" else None, "end": 3.0 if kind == "video" else None,
                                  "scores": {"clip": total}, "total": total, "phash": None})


def _candidate(cid, source, kind="video"):
    extra = {"storyboard": BOARD} if kind == "video" else {"imagePath": "x.jpg", "mediaUrl": "https://x/y.jpg"}
    return Candidate(id=cid, source=source, kind=kind, url=f"https://{cid}", title=cid, channel="c", license="l",
                     credit="Fuente: c", attribution="a", durationSeconds=60, query="q", rankScore=0.1, **extra)


def test_the_judge_keeps_a_downloaded_youtube_clip_and_otherwise_picks_what_needs_no_youtube(tmp_path):
    from pipeline import judge

    plan = _plan([[_broll("e", "a", "b"), _broll("e", "c", "d")]])
    ctx = RunContext.create("v", root=tmp_path, config={"judge": {"hook_seconds": 0, "margin": 0, "min_score": 0}})
    ctx.write_json("shots.json", plan.model_dump(exclude_none=True))
    for sid, ids in (("s001", ["yt:AAAAAAAAAAA", "wm:1"]), ("s002", ["yt:BBBBBBBBBBB", "wm:2"])):
        cands = [_candidate(i, "youtube" if i.startswith("yt") else "wikimedia", "video" if i.startswith("yt") else "image")
                 for i in ids]
        ctx.write_json(f"candidates/{sid}.json", ShotCandidates(shotId=sid, specHash="h", queries={}, candidates=cands)
                       .model_dump(exclude_none=True))
        options = [_option(ids[0], "youtube", 0.9), _option(ids[1], "wikimedia", 0.5, "image")]
        ctx.write_json(f"scores/{sid}.json", ShotScores(shotId=sid, inputsHash="h", needed=2, prompts=[], options=options)
                       .model_dump(by_alias=True, exclude_none=True))
    judge.run(ctx)                                         # with YouTube: both shots take their YouTube clip
    before = json.loads((ctx.work_dir / "selection.json").read_text())["selections"]
    assert [s["candidateId"] for s in before] == ["yt:AAAAAAAAAAA", "yt:BBBBBBBBBBB"]
    media = ctx.work_dir / "media"
    media.mkdir()
    (media / "s001.mp4").write_bytes(b"x")                 # only s001's clip came down before the block
    (media / "_ingest.json").write_text(json.dumps({"slug": "v", "media": [
        {"shotId": "s001", "kind": "video", "path": "work/v/media/s001.mp4", "source": "youtube",
         "candidateId": "yt:AAAAAAAAAAA", "width": 1920, "height": 1080, "credit": "Fuente: c", "specHash": "x",
         "durationSeconds": 2.0}]}))
    with sin_youtube.offline():
        judge.run(ctx)
    after = {s["shotId"]: s for s in json.loads((ctx.work_dir / "selection.json").read_text())["selections"]}
    assert after["s001"] == before[0]                      # exactly the same choice: the ingest keeps the file
    assert after["s002"]["candidateId"] == "wm:2"          # its YouTube clip cannot come now


# --- the runner: done without YouTube → redone with it; the gate after coldopen --------------------------------

def test_stages_done_without_youtube_run_again_when_youtube_is_back_and_not_while_paused(tmp_path):
    calls = []

    def make(name):
        def run(ctx):
            calls.append(name)
            (ctx.work_dir / f"{name}.json").write_text("{}")
        return Stage(name, lambda ctx: [ctx.work_dir / f"{name}.json"], lambda ctx: [], run, None, ())

    stages = [make("planner"), make("sourcing")]
    ctx = RunContext.create("v", root=tmp_path, config={})
    with patch.multiple(runner, STAGES=stages, STAGE_NAMES=["planner", "sourcing"]):
        with sin_youtube.offline():
            run_stages(ctx)
            run_stages(ctx)                                 # still paused: nothing again
        assert calls == ["planner", "sourcing"]
        assert sin_youtube.made_without(tmp_path, "v")
        run_stages(ctx)                                     # YouTube back: only the stage YouTube feeds
        assert calls == ["planner", "sourcing", "sourcing"]
        assert not sin_youtube.made_without(tmp_path, "v")


def test_without_youtube_the_video_stops_after_coldopen_when_the_gate_says_so(tmp_path):
    calls = []

    def make(name):
        def run(ctx):
            calls.append(name)
            (ctx.work_dir / f"{name}.json").write_text("{}")
        return Stage(name, lambda ctx: [ctx.work_dir / f"{name}.json"], lambda ctx: [], run, None, ())

    ctx = RunContext.create("v", root=tmp_path, config={})
    with patch.multiple(runner, STAGES=[make("coldopen"), make("timeline")], STAGE_NAMES=["coldopen", "timeline"]), \
            patch.object(sin_youtube, "gate", side_effect=sin_youtube.WaitingForYouTube("corto")):
        with sin_youtube.offline(), pytest.raises(sin_youtube.WaitingForYouTube):
            run_stages(ctx)
        assert calls == ["coldopen"]


# --- the gate ---------------------------------------------------------------------------------------------------

def _video(root: Path, slug: str, *, shots: int, fallback: int, unresolved: int = 0, cold: bool = True,
           done: bool = True) -> None:
    work = root / "work" / slug
    work.mkdir(parents=True, exist_ok=True)
    selections = [{"shotId": f"s{i:03d}", "status": "fallback" if i < fallback + unresolved else "selected",
                   "decidedBy": "score"} for i in range(shots)]
    (work / "selection.json").write_text(json.dumps({"slug": slug, "selections": selections, "stats": {}}))
    items = [{"shotId": f"s{i:03d}", "method": "pexels-video", "source": "pexels"} for i in range(fallback)]
    unres = {f"s{i:03d}": "nada" for i in range(fallback, fallback + unresolved)}
    (work / "fallback.json").write_text(json.dumps({"slug": slug, "items": items, "unresolved": unres}))
    (work / "coldopen.json").write_text(json.dumps({"slug": slug, "clips": [{"x": 1}] if cold else []}))
    if done:
        (root / "out" / slug).mkdir(parents=True, exist_ok=True)
        (root / "out" / slug / "video-final.mp4").write_bytes(b"x")


def _channel(root: Path, slugs: list[str]) -> None:
    (root / "config.yaml").write_text("{}\n")
    (root / "canales").mkdir(exist_ok=True)
    (root / "canales" / "gym.yaml").touch()
    for slug in slugs:
        _materials(root, slug, "gym")


def test_the_gate_lets_through_a_video_as_covered_as_the_channels_usual(tmp_path):
    _channel(tmp_path, ["a", "b", "c", "new"])
    for slug in ("a", "b", "c"):
        _video(tmp_path, slug, shots=20, fallback=4)       # the channel: 20 % to the fallback, cold open
    _video(tmp_path, "new", shots=20, fallback=5, done=False)        # 25 % ≤ 20 % + 5
    ctx = RunContext.create("new", root=tmp_path)
    sin_youtube.begin(ctx)
    state = sin_youtube.gate(ctx)
    assert state["status"] == "hecho sin YouTube" and state["reference"]["scope"] == "canal"
    assert (ctx.out_dir / sin_youtube.REPORT).read_text().count("✅") == 1


def test_the_gate_holds_a_video_worse_than_usual_and_says_why(tmp_path):
    _channel(tmp_path, ["a", "b", "c", "new"])
    for slug in ("a", "b", "c"):
        _video(tmp_path, slug, shots=20, fallback=4)
    _video(tmp_path, "new", shots=20, fallback=14, unresolved=1, cold=False, done=False)
    ctx = RunContext.create("new", root=tmp_path)
    sin_youtube.begin(ctx)
    with pytest.raises(sin_youtube.WaitingForYouTube) as error:
        sin_youtube.gate(ctx)
    state = json.loads((ctx.work_dir / sin_youtube.STATE).read_text())
    assert state["status"] == "pendiente" and len(state["problems"]) == 3     # fallback, uncovered, cold open
    assert "relleno" in str(error.value)
    assert sin_youtube.waiting(tmp_path, "new")
    (tmp_path / "materiales" / "new" / "biblioteca.txt").write_text("nuevo")   # its materials change: tried again
    assert not sin_youtube.waiting(tmp_path, "new")


def test_the_gate_counts_clips_kept_and_any_youtube_request_of_the_run(tmp_path):
    _channel(tmp_path, ["new"])
    _video(tmp_path, "new", shots=4, fallback=0, done=False)
    ctx = RunContext.create("new", root=tmp_path, config={"without_youtube": {"require_cold_open": False}})
    media = ctx.work_dir / "media"
    media.mkdir()
    (media / "s001.mp4").write_bytes(b"x")
    (media / "_ingest.json").write_text(json.dumps({"slug": "new", "media": [
        {"shotId": "s001", "path": "work/new/media/s001.mp4", "source": "youtube", "candidateId": "yt:x"}]}))
    sin_youtube.begin(ctx)
    assert sin_youtube.coverage(ctx)["reused"] == 1 and sin_youtube.coverage(ctx)["clipsKept"] == 1
    with (ctx.work_dir / "youtube_downloads.jsonl").open("w") as log:
        log.write(json.dumps({"ts": 1, "action": "search"}) + "\n")             # before this run: not counted
        log.write(json.dumps({"ts": time.time() + 1, "action": "archivo a360"}) + "\n")   # a file, not a request
    assert sin_youtube.coverage(ctx)["youtubeRequests"] == 0
    with (ctx.work_dir / "youtube_downloads.jsonl").open("a") as log:
        log.write(json.dumps({"ts": time.time() + 1, "action": "metadata"}) + "\n")
    with pytest.raises(sin_youtube.WaitingForYouTube, match="peticiones a YouTube"):
        sin_youtube.gate(ctx)


# --- the queue --------------------------------------------------------------------------------------------------

def test_while_paused_a_channel_that_allows_it_goes_on_without_youtube_and_one_that_falls_short_waits(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "gym.yaml").write_text("watch:\n  continue_without_youtube: true\n")
    _materials(tmp_path, "GYM", "gym")
    _materials(tmp_path, "SHORT", "gym")
    _materials(tmp_path, "OTHER")
    _pause(tmp_path)
    assert main.waits_for_youtube(tmp_path, "OTHER") and not main.waits_for_youtube(tmp_path, "GYM")
    ran, modes = [], []

    def fake_run(slug, **kwargs):
        ran.append(slug)
        modes.append(sin_youtube.active())
        if slug == "SHORT":
            raise sin_youtube.WaitingForYouTube("SHORT: hecho sin YouTube queda corto")

    with patch.object(main, "run_one", side_effect=fake_run), patch.object(main, "notify", lambda *a, **k: None):
        failures = main.run_queue(force=set(), until=None, review=False, root=tmp_path, check=False)
    assert sorted(ran) == ["GYM", "SHORT"] and failures == 0          # OTHER waits as before; SHORT is no failure
    assert "| SHORT | espera YouTube |" in (tmp_path / main.QUEUE_REPORT).read_text()


def test_run_one_makes_the_video_without_youtube_only_while_paused_and_allowed(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "gym.yaml").write_text("watch:\n  continue_without_youtube: true\n")
    _materials(tmp_path, "GYM", "gym")
    seen = []
    with patch.object(main, "_run_one", side_effect=lambda ctx, **k: seen.append(sin_youtube.active())), \
            patch("pipeline.budget.check", lambda *a, **k: None), patch("pipeline.formats.ensure_auto", lambda ctx: False):
        main.run_one("GYM", force=set(), until=None, review=False, root=tmp_path)
        _pause(tmp_path)
        main.run_one("GYM", force=set(), until=None, review=False, root=tmp_path)
    assert seen == [False, True] and not sin_youtube.active()
    assert json.loads((tmp_path / "work" / "GYM" / sin_youtube.STATE).read_text())["status"] == "haciendo"


def test_a_video_made_without_youtube_still_needs_it_after_its_ingest(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    _materials(tmp_path, "V")
    stages = tmp_path / "work" / "V" / ".stages"
    stages.mkdir(parents=True)
    (stages / "ingest.json").write_text(json.dumps({"stage": "ingest", "withoutYouTube": True}))
    assert main.needs_youtube(tmp_path, "V")
    (stages / "ingest.json").write_text(json.dumps({"stage": "ingest"}))
    assert not main.needs_youtube(tmp_path, "V")


def test_a_stickman_video_never_waits_for_youtube(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "dibujos.yaml").write_text("visual:\n  style: stickman\n")
    _materials(tmp_path, "S", "dibujos")
    assert not main.needs_youtube(tmp_path, "S")
