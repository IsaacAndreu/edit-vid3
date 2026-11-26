"""26-11: switching the text model (DeepSeek → Claude) made every planner «out of date» and videos already rendered
started again from step 3 (hours of searching and analysis). The provider is not part of a stage's fingerprint."""

import json

from pipeline import runner
from pipeline.context import RunContext


def _ctx(tmp_path, planner):
    ctx = RunContext.create("v", root=tmp_path, config={"planner": planner})
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    return ctx


def _stage():
    return next(s for s in runner.STAGES if s.name == "planner")


def test_a_plan_made_with_deepseek_is_still_up_to_date_with_claude(tmp_path):
    stage = _stage()
    before = {"model": "deepseek-flash", "thinking": False, "target_shot_seconds": 2.6, "chapter_titles": False,
              "usd_per_mtok": {"input": 0.30, "input_cache_hit": 0.006, "output": 1.20}}
    after = {"model": "claude-sonnet-5-5", "effort": "medium", "thinking": False, "target_shot_seconds": 2.6,
             "chapter_titles": False}
    new = _ctx(tmp_path, after)
    # the marker written with DeepSeek (no provider stripping, as before this change)
    import hashlib

    digest = hashlib.sha256()
    for path in stage.inputs(new):
        runner._hash_path(digest, path)
    digest.update(json.dumps(runner._without_speed(before), sort_keys=True).encode())
    assert digest.hexdigest() in {runner.fingerprint(new, stage, legacy=l, provider=p)
                                  for l in (False, True) for p in ("deepseek", "deepseek-sin-rotulos")}
    # and from now on the provider does not count at all
    assert runner.fingerprint(new, stage) == runner.fingerprint(_ctx(tmp_path, {**after, "model": "deepseek-flash"}), stage)
    # a real change of the plan still counts
    assert runner.fingerprint(new, stage) != runner.fingerprint(_ctx(tmp_path, {**after, "target_shot_seconds": 3.0}), stage)


def test_before_chapter_titles_existed_too(tmp_path):
    stage = _stage()
    import hashlib

    before = {"model": "deepseek-flash", "thinking": False, "target_shot_seconds": 2.6,
              "usd_per_mtok": {"input": 0.30, "input_cache_hit": 0.006, "output": 1.20}}
    new = _ctx(tmp_path, {"model": "claude-sonnet-5-5", "effort": "medium", "thinking": False, "target_shot_seconds": 2.6,
                          "chapter_titles": False})
    digest = hashlib.sha256()
    for path in stage.inputs(new):
        runner._hash_path(digest, path)
    digest.update(json.dumps(runner._without_speed(before), sort_keys=True).encode())
    assert digest.hexdigest() == runner.fingerprint(new, stage, provider="deepseek-sin-rotulos")
