"""Adaptive fine pass (analysis.adaptive): the best videos of each shot first; the next ones only for the shots none
of those gave a usable fragment — the same thresholds, never more windows than before."""

from __future__ import annotations

import numpy as np
import pytest

from pipeline import analysis
from pipeline.context import RunContext
from pipeline.schemas import Candidate, Shot, ShotCandidates, ShotsFile


def _candidate(n: int) -> Candidate:
    return Candidate.model_validate({
        "id": f"yt:{n:011d}", "source": "youtube", "kind": "video", "url": "u", "title": f"v{n}", "channel": "c",
        "license": "l", "credit": "Fuente: c", "attribution": "a", "query": "q", "rankScore": 0.1, "durationSeconds": 200,
        "storyboard": {"sheets": ["s.jpg"], "columns": 3, "rows": 3, "tileWidth": 320, "tileHeight": 180, "interval": 5.0, "frames": 9}})


def _shot(n: int) -> Shot:
    return Shot.model_validate({
        "id": f"s{n:03d}", "type": "broll", "startWord": (n - 1) * 5, "endWord": (n - 1) * 5 + 4, "start": (n - 1) * 4.0, "end": n * 4.0,
        "text": "Una frase del guion.", "chapter": 0,
        "broll": {"visualIntent": "una escena", "queriesEn": ["a", "b", "c"], "queriesEs": ["a"], "entities": [],
                  "mustContain": [], "avoid": [], "preferredShot": "medium"}})


class FakeClip:
    def shot_vector(self, prompts):
        return np.ones(4, np.float32) / 2


class FakeYouTube:
    concurrency = 1
    _pacers = [None]

    def __init__(self, root):
        self.root, self.downloaded = root, []

    def download_section(self, video, a, b):
        self.downloaded.append(f"yt:{video}")
        return self.root / f"{video}_{a}_{b}.mp4"

    def prefetch_sections(self, video):
        return False

    def captions(self, video):
        return []

    def close(self):
        pass


@pytest.mark.parametrize("adaptive,expected", [(False, 4), (True, 3)])
def test_a_shot_with_a_good_first_video_stops_there_and_a_hard_one_sees_the_rest(tmp_path, monkeypatch, adaptive, expected):
    ctx = RunContext.create("v", root=tmp_path, config={"analysis": {"adaptive": adaptive, "adaptive_first": 1, "fine_windows": 2,
                                                                     "extra_windows_with_entities": 0}})
    shots = [_shot(1), _shot(2)]
    ctx.write_json("shots.json", ShotsFile.model_validate({
        "slug": "v", "title": "v", "durationSeconds": 8.0, "chapters": [{"title": "c", "startWord": 0, "fromScript": False}],
        "shots": [s.model_dump() for s in shots]}).model_dump(by_alias=True))
    # s001: video 1 is good; s002: video 3 is unusable (talking head), video 4 is good
    pools = {"s001": [_candidate(1), _candidate(2)], "s002": [_candidate(3), _candidate(4)]}
    for sid, cands in pools.items():
        ctx.write_json(f"candidates/{sid}.json", ShotCandidates(shotId=sid, specHash="h", queries={}, candidates=cands).model_dump())
    better = {"yt:00000000001": 0.9, "yt:00000000002": 0.5, "yt:00000000003": 0.9, "yt:00000000004": 0.5}
    monkeypatch.setattr(analysis, "make_models", lambda ctx: (FakeClip(), None))
    monkeypatch.setattr(analysis, "video_features", lambda clip, c, root, cfg: (
        np.array([50.0]), np.full((1, 4), better[c.id], np.float32)))
    fake = FakeYouTube(tmp_path)
    monkeypatch.setattr(analysis, "youtube_source", lambda ctx: fake)

    def fine(window_path, window, needed, **_):
        bad = "00000000003" in str(window_path)
        return [{"start": window[0], "end": window[0] + needed, "scores": {"clip": 0.3}, "phash": "0" * 16,
                 "discarded": "presentador hablando a cámara" if bad else None}]

    monkeypatch.setattr(analysis, "fine_options", fine)
    monkeypatch.setattr(analysis, "_write_summary", lambda ctx, shots: None)
    analysis.analyse(ctx)
    assert len(fake.downloaded) == expected
    if adaptive:
        assert "yt:00000000002" not in fake.downloaded and "yt:00000000004" in fake.downloaded
        rounds = ctx.read_json("scores/_rondas.json")
        assert rounds["shotsSecondRound"] == 1 and rounds["windowsSecondRound"] == 1 and rounds["videos"] == 3


def test_the_report_counts_overlapping_downloads_of_the_same_kind():
    from pipeline.informe_analisis import overlaps

    rows = [{"ts": 1, "action": "archivo a360", "video": "x", "ok": True, "start": 10, "end": 19},
            {"ts": 2, "action": "archivo a360", "video": "x", "ok": True, "start": 15, "end": 24},     # overlaps
            {"ts": 3, "action": "archivo a360", "video": "x", "ok": True, "start": 30, "end": 39},
            {"ts": 4, "action": "archivo hd", "video": "x", "ok": True, "start": 15, "end": 19}]       # another kind
    assert overlaps(rows) == 1


def test_the_report_compares_videos_before_and_with_the_adaptive_pass(tmp_path, monkeypatch):
    import json

    from pipeline import agenda, informe_analisis

    def work(slug, adaptive, videos, metas, judged, fallback):
        w = tmp_path / "work" / slug
        (w / ".stages").mkdir(parents=True)
        (w / "scores").mkdir()
        (w / ".stages" / "analysis.json").write_text(json.dumps({"seconds": 600}))
        (w / "scores" / "_rondas.json").write_text(json.dumps({"adaptive": adaptive, "videos": videos, "shotsSecondRound": 2}))
        (w / "selection.json").write_text(json.dumps({"stats": {"byScore": 0, "byJudge": judged, "fallback": fallback}}))
        rows = [{"ts": i, "stage": "analysis", "action": "metadata", "ok": True} for i in range(metas)]
        rows.append({"ts": 99, "stage": "analysis", "action": "metadata", "ok": True, "proxy": "metadatos"})   # not home budget
        (w / "youtube_downloads.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

    work("a1", False, 200, 200, 80, 20)
    work("a2", True, 120, 120, 79, 21)
    monkeypatch.setattr(agenda, "videos", lambda root: [{"slug": "a1", "channel": "c"}, {"slug": "a2", "channel": "c"}])
    data = informe_analisis.report(tmp_path)
    before, after = sorted(data["summary"], key=lambda s: s["adaptive"])
    assert (before["videos"], before["units"], before["accepted"]) == (200, 800, 0.8)
    assert (after["videos"], after["units"], after["accepted"]) == (120, 480, 0.79)
    assert "adaptativo" in informe_analisis.markdown(data)


def test_a_restart_in_the_middle_keeps_the_shots_already_analysed(tmp_path, monkeypatch):
    ctx = RunContext.create("v", root=tmp_path, config={"analysis": {"fine_windows": 2, "extra_windows_with_entities": 0},
                                                        "sourcing": {"youtube": {"concurrency": 1}}})
    shots = [_shot(1), _shot(2)]
    ctx.write_json("shots.json", ShotsFile.model_validate({
        "slug": "v", "title": "v", "durationSeconds": 8.0, "chapters": [{"title": "c", "startWord": 0, "fromScript": False}],
        "shots": [s.model_dump() for s in shots]}).model_dump(by_alias=True))
    pools = {"s001": [_candidate(1), _candidate(2)], "s002": [_candidate(3), _candidate(4)]}
    for sid, cands in pools.items():
        ctx.write_json(f"candidates/{sid}.json", ShotCandidates(shotId=sid, specHash="h", queries={}, candidates=cands).model_dump())
    monkeypatch.setattr(analysis, "make_models", lambda ctx: (FakeClip(), None))
    monkeypatch.setattr(analysis, "video_features", lambda clip, c, root, cfg: (np.array([50.0]), np.full((1, 4), 0.6, np.float32)))
    monkeypatch.setattr(analysis, "fine_options", lambda window_path, window, needed, **_: [
        {"start": window[0], "end": window[0] + needed, "scores": {"clip": 0.3}, "phash": "0" * 16, "discarded": None}])
    monkeypatch.setattr(analysis, "_write_summary", lambda ctx, shots: None)

    class Crashing(FakeYouTube):
        def download_section(self, video, a, b):
            if video.endswith("3"):
                raise SystemExit("the service restarts")          # not an Exception: it stops the whole stage
            return super().download_section(video, a, b)

    monkeypatch.setattr(analysis, "youtube_source", lambda ctx: Crashing(tmp_path))
    with pytest.raises(SystemExit):
        analysis.analyse(ctx)
    assert (ctx.work_dir / "scores" / "s001.json").is_file()          # its windows were all in: kept
    assert not (ctx.work_dir / "scores" / "s002.json").is_file()
    again = FakeYouTube(tmp_path)
    monkeypatch.setattr(analysis, "youtube_source", lambda ctx: again)
    analysis.analyse(ctx)
    assert {v[:14] for v in again.downloaded} == {"yt:00000000003", "yt:00000000004"}   # only what was missing
