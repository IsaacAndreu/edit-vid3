"""Speed: near-identical searches merged, a hard shot gives up early, the time report, the judge's knobs."""

import json
from pathlib import Path

from pipeline import runner, tiempos
from pipeline.sourcing.youtube import GAVE_UP, YouTubeSource


def _source(cfg):
    src = YouTubeSource.__new__(YouTubeSource)
    src.cfg = cfg
    src.api = None
    return src


def test_near_identical_queries_become_one_but_never_across_years():
    src = _source({"query_merge": 0.8})
    assert src.merged("Simone Biles Amanar vault Rio 2016") == "Simone Biles Amanar vault Rio 2016"
    assert src.merged("Simone Biles Amanar vault 2016 Rio Olympics") == "Simone Biles Amanar vault Rio 2016"
    assert src.merged("Simone Biles Amanar vault Rio 2021") == "Simone Biles Amanar vault Rio 2021"   # another year
    assert src.merged("Simone Biles floor Rio 2016") == "Simone Biles floor Rio 2016"                 # another skill
    assert _source({"query_merge": 0}).merged("a b c") == "a b c"


def test_a_hard_shot_stops_after_a_few_videos(monkeypatch):
    src = _source({"max_details_per_shot": 4, "videos_per_shot": 3})
    entries = {f"v{i}": {"id": f"v{i}", "title": "x", "query": "q"} for i in range(12)}
    monkeypatch.setattr(src, "search_pool", lambda queries, notes: ([list(entries)], entries))
    monkeypatch.setattr(src, "queries_for", lambda broll: ["q"])
    asked = []
    monkeypatch.setattr(src, "candidate", lambda v, e, s, n: asked.append(v))   # every one fails the filters

    class B:
        entities = []

    notes = []
    assert src.candidates(B(), notes) == []
    assert len(asked) == 4 and any(n.startswith(GAVE_UP) for n in notes)


def test_speed_knobs_never_make_a_stage_run_again():
    for k in ("query_merge", "max_details_per_shot", "rounds_rest", "model_rest", "usd_per_mtok_rest"):
        assert k in runner.SPEED_KEYS


def test_time_report_names_the_slowest_stage(tmp_path: Path):
    work = tmp_path / "work" / "gim1"
    (work / ".stages").mkdir(parents=True)
    (work / "candidates").mkdir()
    for stage, seconds in {"sourcing": 7200, "render": 1800, "judge": 600}.items():
        (work / ".stages" / f"{stage}.json").write_text(json.dumps({"seconds": seconds}))
    (work / "candidates" / "_summary.json").write_text(json.dumps({"shots": 120}))
    (work / "youtube_downloads.jsonl").write_text(json.dumps({"action": "search", "seconds": 3, "wait": 20}) + "\n")
    assert tiempos.slowest(work).startswith("buscar material 2 h 00 min (75")
    text = tiempos.write(tmp_path)
    assert "60 s por plano" in text and "Terceros · 1 vídeos" in text and (tmp_path / tiempos.REPORT).is_file()
