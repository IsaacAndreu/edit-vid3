"""The queue pauses itself while YouTube blocks the connection and resumes when a probe works."""

from __future__ import annotations

from pathlib import Path

from pipeline import ytpause


def test_pause_is_written_once_and_resume_clears_it(tmp_path: Path, monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(ytpause, "_tell", lambda root, text: sent.append(text))
    assert ytpause.paused(tmp_path) is None
    ytpause.pause(tmp_path, "YouTube ha bloqueado las búsquedas")
    ytpause.pause(tmp_path, "otra vez")                       # a second blocked video: no second message
    assert ytpause.paused(tmp_path)["reason"].startswith("YouTube ha bloqueado")
    assert len(sent) == 1
    assert not ytpause.due(tmp_path, 60) and ytpause.due(tmp_path, 0)
    ytpause.resume(tmp_path)
    assert ytpause.paused(tmp_path) is None and len(sent) == 2


def test_blocked_is_a_runtime_error() -> None:
    assert issubclass(ytpause.YouTubeBlocked, RuntimeError)


def test_a_video_over_its_budget_stops_and_leaves_the_queue(tmp_path: Path) -> None:
    import json

    import pytest

    from pipeline import budget

    work, folder = tmp_path / "work" / "v", tmp_path / "materiales" / "v"
    work.mkdir(parents=True)
    folder.mkdir(parents=True)
    (work / "costs.json").write_text(json.dumps({"totalUsd": 3.0}))
    budget.check_video(tmp_path, {}, work, folder, started_at=2.0)          # this attempt: 1.0 $ ≤ 1.5 $
    with pytest.raises(budget.VideoOverBudget):
        budget.check_video(tmp_path, {}, work, folder, started_at=1.0)      # 2.0 $ > 1.5 $
    assert (folder / ".en-espera").is_file()


def test_speed_knobs_do_not_change_a_stage_fingerprint(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from pipeline import runner

    def ctx(cfg):
        return SimpleNamespace(section=lambda name: cfg.get(name, {}))

    stage = SimpleNamespace(inputs=lambda c: [], config_sections=("sourcing",))
    base = {"sourcing": {"parallel": 4, "youtube": {"concurrency": 6, "results_per_query": 8, "player_client": ["default"]}}}
    faster = {"sourcing": {"parallel": 8, "youtube": {"concurrency": 2, "results_per_query": 8, "player_client": ["mweb"]}}}
    other = {"sourcing": {"parallel": 4, "youtube": {"concurrency": 6, "results_per_query": 5}}}
    assert runner.fingerprint(ctx(base), stage) == runner.fingerprint(ctx(faster), stage)
    assert runner.fingerprint(ctx(base), stage) != runner.fingerprint(ctx(other), stage)
    assert runner.fingerprint(ctx(base), stage, legacy=True) != runner.fingerprint(ctx(faster), stage, legacy=True)
