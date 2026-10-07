"""A server's chores: peak RAM/CPU per stage and cleaning finished videos."""

import os
import time

from pipeline import housekeeping
from pipeline.context import RunContext


def test_the_sampler_reports_the_machines_peak_ram():
    with housekeeping.Sampler(every=0.05) as usage:
        time.sleep(0.3)
    fields = usage.fields()
    assert fields.get("ramPeakGb", 1) > 0


def test_cleanup_keeps_the_video_and_plans_and_drops_heavy_files(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={"paths": {}, "cleanup": {"after_video": True, "cache_days": 1}})
    (ctx.work_dir / "render").mkdir(parents=True)
    (ctx.work_dir / "render" / "seg.mp4").write_bytes(b"x" * 100)
    (ctx.work_dir / "timeline.json").write_text("{}")
    housekeeping.after_video(ctx)                        # no final video yet: nothing goes
    assert (ctx.work_dir / "render").is_dir()
    ctx.out_dir.mkdir(parents=True)
    (ctx.out_dir / "video-final.mp4").write_bytes(b"v")
    housekeeping.after_video(ctx)
    assert not (ctx.work_dir / "render").exists() and (ctx.work_dir / "timeline.json").is_file()
    old = ctx.cache_dir / "videos" / "abc" / "full_hd.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    os.utime(old, (time.time() - 3 * 86400,) * 2)
    fresh = ctx.cache_dir / "videos" / "abc" / "info.json"
    fresh.write_text("{}")
    housekeeping.old_cache(ctx)
    assert not old.exists() and fresh.exists()


def test_uploaded_videos_lose_their_heavy_files_but_stay_done(tmp_path):
    import json
    import time

    import main
    from pipeline import housekeeping

    for slug in ("subido", "nuevo"):
        folder = tmp_path / "materiales" / slug
        folder.mkdir(parents=True)
        (folder / "guion.txt").write_text("x")
        (folder / "voz.mp3").write_bytes(b"x")
        out = tmp_path / "out" / slug
        (out / "shorts").mkdir(parents=True)
        (out / "video-final.mp4").write_bytes(b"0" * 1000)
        (out / "shorts" / "short-1.mp4").write_bytes(b"0" * 100)
        (out / "diagnostico.md").write_text("ok")
        (tmp_path / "work" / slug / "render").mkdir(parents=True)
        (tmp_path / "work" / slug / "render" / "seg.mp4").write_bytes(b"0" * 500)
    housekeeping.mark_published(tmp_path, "subido", "https://youtu.be/x")
    data = json.loads((tmp_path / "out" / "subido" / housekeeping.PUBLISHED).read_text())
    data["at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 8 * 86400))
    (tmp_path / "out" / "subido" / housekeeping.PUBLISHED).write_text(json.dumps(data))
    assert housekeeping.rotate_published(tmp_path, {}) == 0                     # not configured: never by surprise
    cfg = {"cleanup": {"published_days": 7, "min_free_gb": 0}}
    assert housekeeping.rotate_published(tmp_path, cfg) > 0
    out = tmp_path / "out" / "subido"
    assert (out / "video-final.mp4").exists() and not (out / "shorts" / "short-1.mp4").exists()   # kept for a compilation
    (tmp_path / "out" / "_compilaciones.json").write_text(json.dumps({"c1": {"videos": ["subido"]}}))
    assert housekeeping.rotate_published(tmp_path, cfg) > 0                      # compiled: now it goes
    out = tmp_path / "out" / "subido"
    assert not (out / "video-final.mp4").exists() and not (out / "shorts" / "short-1.mp4").exists()
    assert (out / "diagnostico.md").is_file() and (out / housekeeping.REMOVED).is_file()
    assert not (tmp_path / "work" / "subido" / "render").exists()
    assert (tmp_path / "out" / "nuevo" / "video-final.mp4").is_file()           # not uploaded: untouched
    assert main.pending_slugs(tmp_path) == []                                    # cleaned ≠ pending: never made again


def test_upload_found_on_the_channel_by_title():
    from pipeline import housekeeping

    assert housekeeping._same_title("Los Fallos De Gimnasia Que SORPRENDIERON Al Mundo",
                                    "Los fallos de gimnasia que sorprendieron al mundo 😱")
    assert not housekeeping._same_title("Los fallos de gimnasia", "La historia de Carlos Yulo")
