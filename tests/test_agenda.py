"""The publishing calendar: slots per channel, which video fills each, gaps with deadlines, queue order, board."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from pipeline import agenda


def _site(tmp: Path) -> Path:
    (tmp / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    (tmp / "canales").mkdir()
    for name in ("gimnasia", "negocios"):
        (tmp / "canales" / f"{name}.yaml").write_text("format: historia\n", encoding="utf-8")
        (tmp / "materiales" / name).mkdir(parents=True)
        (tmp / "materiales" / name / "config.yaml").write_text(f"canal: {name}\n", encoding="utf-8")
    return tmp


def _video(root: Path, channel: str, slug: str, *, done=False, voice=True, published: str | None = None) -> None:
    folder = root / "materiales" / channel / slug
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("Hola.", encoding="utf-8")
    if voice:
        (folder / "voz.mp3").write_bytes(b"ID3")
    if done or published:
        (root / "out" / slug).mkdir(parents=True, exist_ok=True)
        (root / "out" / slug / "video-final.mp4").write_bytes(b"x")
    if published:
        (root / "out" / slug / "publicado.json").write_text(json.dumps({"at": published + "T18:05:00", "url": ""}))


MONDAY = datetime(2026, 10, 5, 9, 0)        # a Monday


def test_slots_follow_the_days_and_the_readiest_video_goes_first(tmp_path: Path) -> None:
    root = _site(tmp_path)
    _video(root, "gimnasia", "g-ready", done=True)
    _video(root, "gimnasia", "g-queued")
    _video(root, "gimnasia", "g-novoice", voice=False)
    plan = [s for s in agenda.plan(root, MONDAY.date(), 7, MONDAY) if s["channel"] == "gimnasia"]
    assert [s["date"] for s in plan] == ["2026-10-05", "2026-10-07", "2026-10-09"]     # L, X, V
    assert [s["video"]["slug"] for s in plan] == ["g-ready", "g-queued", "g-novoice"]
    assert plan[0]["ok"] and not plan[1]["gap"] and plan[2]["gap"]                     # no voice yet: a gap
    assert plan[2]["deadline"] == "2026-10-08T06:00"                                   # Friday 18:00 − 36 h


def test_an_empty_slot_is_a_gap_and_late_after_its_deadline(tmp_path: Path) -> None:
    root = _site(tmp_path)
    friday_morning = datetime(2026, 10, 9, 9, 0)
    slot = next(s for s in agenda.plan(root, friday_morning.date(), 1, friday_morning) if s["channel"] == "negocios")
    assert slot["video"] is None and slot["gap"] and slot["late"]


def test_published_and_pinned_videos_keep_their_day(tmp_path: Path) -> None:
    root = _site(tmp_path)
    _video(root, "negocios", "n-out", published="2026-10-05")
    _video(root, "negocios", "n-pinned", done=True)
    _video(root, "negocios", "n-other", done=True)
    agenda.update(root, {"assign": "n-pinned", "date": "2026-10-09"})
    plan = {s["date"]: s for s in agenda.plan(root, MONDAY.date(), 7, MONDAY) if s["channel"] == "negocios"}
    assert plan["2026-10-05"]["video"]["slug"] == "n-out"
    assert plan["2026-10-09"]["video"]["slug"] == "n-pinned" and plan["2026-10-09"].get("pinned")
    assert plan["2026-10-07"]["video"]["slug"] == "n-other"


def test_schedule_changes_and_reserve(tmp_path: Path) -> None:
    root = _site(tmp_path)
    agenda.update(root, {"channel": "gimnasia", "days": [1, 3], "time": "20:30"})
    agenda.update(root, {"channel": "negocios", "enabled": False})
    plan = agenda.plan(root, MONDAY.date(), 7, MONDAY)
    assert {s["channel"] for s in plan} == {"gimnasia"} and all(s["time"] == "20:30" for s in plan)
    _video(root, "gimnasia", "g1", done=True)
    assert agenda.reserve(root) == {"gimnasia": 1}


def test_the_board_columns(tmp_path: Path) -> None:
    root = _site(tmp_path)
    _video(root, "gimnasia", "g-done", done=True)
    _video(root, "gimnasia", "g-novoice", voice=False)
    idea = agenda.add_idea(root, "La caída de X", "negocios", "ángulo", (date.today() + timedelta(days=3)).isoformat())
    columns = agenda.board(root)
    assert [i["title"] for i in columns["idea"]] == ["La caída de X"]
    assert [v["slug"] for v in columns["hecho"]] == ["g-done"] and [v["slug"] for v in columns["falta voz"]] == ["g-novoice"]
    agenda.remove_idea(root, idea["id"])
    assert agenda.board(root)["idea"] == []
