"""The judge's frozen lessons, --doctor and --actualizar."""

import json
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import main
from pipeline import actualizar, chequeo, feedback, judge


def test_lessons_are_renewed_only_every_few_corrections(monkeypatch, tmp_path: Path):
    entries = [{"text": f"t{i}"} for i in range(3)]
    monkeypatch.setattr(feedback, "lesson_entries", lambda root, ch: entries)
    monkeypatch.setattr(feedback, "lessons", lambda root, ch, limit: f"lessons of {len(entries)}")
    ctx = SimpleNamespace(root=tmp_path, cache_dir=tmp_path / "cache", channel="gimnasia",
                          section=lambda name: {"lessons_refresh": 5})
    assert judge.frozen_lessons(ctx) == "lessons of 3"
    entries += [{"text": "x"}] * 4                       # 4 new: the judge keeps the same prompt (and cache)
    assert judge.frozen_lessons(ctx) == "lessons of 3"
    entries += [{"text": "y"}]                           # the 5th: renewed
    assert judge.frozen_lessons(ctx) == "lessons of 8"


def test_doctor_never_shows_a_key_and_flags_an_old_ytdlp(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-123")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rows = chequeo.keys(tmp_path)
    assert not any("sk-secret" in r["text"] for r in rows)
    assert any(r["level"] == chequeo.FAIL and "OPENAI_API_KEY" in r["text"] for r in rows)
    assert chequeo.ytdlp_age("2026.09.01", date(2026, 11, 3)) == 63
    assert chequeo.ytdlp_age("raro") is None


def test_updating_holds_third_party_videos_only(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(main, "is_drawn", lambda root, slug: slug.startswith("sim"))
    assert main.while_updating(tmp_path, ["gim1", "sim1"]) == ["gim1", "sim1"]
    (tmp_path / "out").mkdir()
    (tmp_path / actualizar.FLAG).write_text("x")
    assert main.while_updating(tmp_path, ["gim1", "sim1"]) == ["sim1"]
    old = (tmp_path / actualizar.FLAG).stat().st_mtime - actualizar.FLAG_MAX_AGE - 10
    os.utime(tmp_path / actualizar.FLAG, (old, old))          # a mark left by a killed update stops nothing
    assert main.while_updating(tmp_path, ["gim1"]) == ["gim1"]


def test_running_videos_are_the_ones_with_a_live_process(tmp_path: Path):
    for slug, info in {"gim1": {"stage": "sourcing", "pid": os.getpid()},
                       "gim2": {"stage": "render", "pid": os.getpid(), "ended": "x"},
                       "gim3": {"stage": "judge", "pid": 99999999}}.items():
        (tmp_path / "work" / slug).mkdir(parents=True)
        (tmp_path / "work" / slug / "current.json").write_text(json.dumps(info))
    assert actualizar.running(tmp_path) == [("gim1", "sourcing")]


def test_no_gap_in_time_changes_nothing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(actualizar, "third_party", lambda root: [("gim1", "sourcing")])
    called = []
    monkeypatch.setattr(actualizar, "_git", lambda root, *a: called.append(a))
    assert actualizar.main(tmp_path, max_hours=0, every=0) == 2
    assert called == [] and not (tmp_path / actualizar.FLAG).exists()
