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
