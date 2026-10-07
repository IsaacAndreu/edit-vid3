"""The library of people and topics (pipeline/library.py)."""

from __future__ import annotations

from pathlib import Path

from pipeline import library
from pipeline.context import RunContext
from pipeline.schemas import BrollSpec


def _video(cid: str, title: str, channel: str = "Noticias", sheet: str = "") -> dict:
    board = {"sheets": [sheet], "columns": 1, "rows": 1, "tileWidth": 1, "tileHeight": 1, "interval": 5, "frames": 1}
    return {"id": cid, "source": "youtube", "kind": "video", "url": f"https://y/{cid}", "title": title, "channel": channel,
            "license": "l", "credit": f"Fuente: {channel}", "attribution": "a", "query": "q", "rankScore": 1,
            "durationSeconds": 100, "storyboard": board}


def _opt(cid: str, total: float) -> dict:
    return {"candidateId": cid, "source": "youtube", "kind": "video", "pass": "fine", "start": 1.0, "end": 3.0,
            "scores": {"clip": total}, "total": total}


def _job(root: Path) -> RunContext:
    (root / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    ctx = RunContext.create("n1", root=root, config={})
    for cid in ("yt:a", "yt:b", "yt:c", "yt:d"):
        sheet = root / "cache" / "videos" / cid[3:] / "sb" / "000.jpg"
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_bytes(b"jpg")
    sb = lambda cid: f"cache/videos/{cid[3:]}/sb/000.jpg"
    broll = lambda entities: {"visualIntent": "sede", "queries": ["a", "b", "c"], "queriesLocal": ["d"], "entities": entities}
    shots = [
        {"id": "s001", "type": "broll", "startWord": 0, "endWord": 0, "start": 0, "end": 2, "text": "t", "chapter": 0,
         "broll": broll(["Booking.com", "CNMC"])},
        {"id": "s002", "type": "broll", "startWord": 1, "endWord": 1, "start": 2, "end": 4, "text": "t", "chapter": 0,
         "broll": broll(["Audiencia Nacional"])},
    ]
    ctx.write_json("shots.json", {"slug": "n1", "title": "T", "durationSeconds": 4, "chapters": [{"title": "X", "startWord": 0,
                   "fromScript": False}], "shots": shots})
    ctx.write_json("candidates/s001.json", {"shotId": "s001", "specHash": "h", "queries": {}, "candidates": [
        _video("yt:a", "La CNMC multa a Booking.com", sheet=sb("yt:a")), _video("yt:b", "Booking.com sede", sheet=sb("yt:b")),
        _video("yt:c", "Hoteles de Madrid", sheet=sb("yt:c"))]})
    ctx.write_json("candidates/s002.json", {"shotId": "s002", "specHash": "h", "queries": {}, "candidates": [
        _video("yt:d", "Tribunal edificio", sheet=sb("yt:d"))]})
    ctx.write_json("scores/s001.json", {"shotId": "s001", "inputsHash": "h", "needed": 2.0, "prompts": ["p"],
                                        "options": [_opt("yt:a", 0.5), _opt("yt:b", 0.4), _opt("yt:c", 0.2)]})
    return ctx


def test_topics_learn_used_and_approved_sources_and_keep_their_thumbnails(tmp_path):
    ctx = _job(tmp_path)
    library.remember(ctx, [{"shotId": "s001", "candidateId": "yt:a", "decidedBy": "judge"},
                           {"shotId": "s002", "candidateId": "yt:d", "decidedBy": "judge"}])
    booking, cnmc = library.load(ctx, "Booking.com"), library.load(ctx, "CNMC")
    assert set(booking["videos"]) == {"yt:a", "yt:b"}                   # used + approved (0.4 ≥ 0.35), not the 0.2
    assert booking["stats"]["yt:a"]["used"] == 1 and booking["stats"]["yt:b"]["approved"] == 1
    assert set(cnmc["videos"]) == {"yt:a"}                               # only the one that names it
    assert set(library.load(ctx, "Audiencia Nacional")["videos"]) == {"yt:d"}   # the shot was only about it
    sheet = booking["videos"]["yt:a"]["storyboard"]["sheets"][0]
    assert sheet.startswith("cache/library/_media/") and (tmp_path / sheet).is_file()
    (tmp_path / "cache" / "videos" / "a" / "sb" / "000.jpg").unlink()   # the cache cleanup: still usable
    found = library.candidates_for(ctx, BrollSpec(visualIntent="sede", queries=["a", "b", "c"], queriesLocal=["d"],
                                                  entities=["Booking.com"]), set(), 3)
    assert [c.id for c in found] == ["yt:a", "yt:b"]                     # used ranks above approved
    assert found[0].query == "biblioteca: Booking.com"


def test_the_studio_lists_marks_and_removes(tmp_path):
    ctx = _job(tmp_path)
    library.remember(ctx, [{"shotId": "s001", "candidateId": "yt:a", "decidedBy": "judge"}])
    names = {e["name"]: e for e in library.overview(tmp_path)}
    assert names["Booking.com"]["videos"] == 2 and names["Booking.com"]["inVideos"] == 1
    key = names["Booking.com"]["key"]
    assert library.mark_right(tmp_path, "yt:b") == 1
    assert library.entity(tmp_path, key)["sources"][0]["id"] == "yt:b"  # ⭐ correcta counts double
    assert library.preview(tmp_path, key, "yt:a").is_file()
    library.remove(tmp_path, key, "yt:a")
    library.remember(ctx, [{"shotId": "s001", "candidateId": "yt:a", "decidedBy": "judge"}])
    assert "yt:a" not in library.load(ctx, "Booking.com")["videos"]     # removed: never comes back
    library.remove(tmp_path, key)
    assert "Booking.com" not in {e["name"] for e in library.overview(tmp_path)}


def test_old_libraries_get_their_thumbnails_protected(tmp_path):
    ctx = _job(tmp_path)
    data = library.load(ctx, "Carlos Yulo")
    data["videos"]["yt:c"] = _video("yt:c", "Carlos Yulo final", sheet="cache/videos/c/sb/000.jpg")
    library.save(ctx, "Carlos Yulo", data)
    assert library.protect(ctx) == 1 and library.protect(ctx) == 0
    assert library.load(ctx, "Carlos Yulo")["videos"]["yt:c"]["storyboard"]["sheets"][0].startswith("cache/library/_media/")


def test_the_clips_on_screen_are_kept_small_and_listed(tmp_path):
    import subprocess

    ctx = _job(tmp_path)
    clip = ctx.work_dir / "media" / "s001.mp4"
    clip.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30:duration=4",
                    str(clip)], check=True)
    library.remember(ctx, [{"shotId": "s001", "candidateId": "yt:a", "decidedBy": "judge", "kind": "video",
                            "media": "media/s001.mp4", "sourceStart": 12.5}])
    key = library.person_key("Booking.com")
    used = next(s for s in library.entity(tmp_path, key)["sources"] if s["id"] == "yt:a")
    assert len(used["clips"]) == 1 and used["clips"][0]["video"] == "n1"
    saved = library.clip_file(tmp_path, used["clips"][0]["file"])
    assert saved is not None and saved.stat().st_size < clip.stat().st_size
    assert library.clip_file(tmp_path, "../../etc/passwd") is None
    approved = next(s for s in library.entity(tmp_path, key)["sources"] if s["id"] == "yt:b")
    assert approved["clips"] == []                                         # not on screen: no clip
