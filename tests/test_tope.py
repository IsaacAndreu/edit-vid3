"""content.max_third_party_seconds (decisión del dueño, 21-11): the cap of a third-party clip per channel and video.
Changing it never re-runs a stage (a video half made with 5 s goes on), the schemas accept both, QA checks each video
against its own channel's cap, and the video page says how long each source runs on screen."""

from pathlib import Path

from pipeline import runner, tope
from pipeline.context import RunContext
from pipeline.schemas import HARD_LIMIT_SECONDS, Selection, TimelineMedia, TimelineShot


def test_changing_the_cap_never_makes_a_stage_run_again(tmp_path: Path):
    stage = next(s for s in runner.STAGES if s.name == "judge")
    before = RunContext.create("v", root=tmp_path, config={"content": {"max_third_party_seconds": 5}})
    after = RunContext.create("v", root=tmp_path, config={"content": {"max_third_party_seconds": 12}})
    other = RunContext.create("v", root=tmp_path, config={"content": {"title_blocklist": ["x"]}})
    for ctx in (before, after, other):
        ctx.work_dir.mkdir(parents=True, exist_ok=True)
    assert runner.fingerprint(before, stage) == runner.fingerprint(after, stage)
    assert runner.fingerprint(before, stage) != runner.fingerprint(other, stage)      # a real «what» still does


def test_the_cap_per_video_and_its_limits(tmp_path: Path):
    assert tope.seconds(RunContext.create("v", root=tmp_path, config={})) == 5.0                 # nothing set: as before
    assert tope.seconds(RunContext.create("v", root=tmp_path, config={"content": {"max_third_party_seconds": 60}})) == 60
    assert tope.seconds(RunContext.create("v", root=tmp_path, config={"content": {"max_third_party_seconds": 999}})) \
        == HARD_LIMIT_SECONDS
    assert tope.seconds(RunContext.create("v", root=tmp_path, config={"content": {"max_third_party_seconds": "x"}})) == 5


def test_half_made_5_s_and_new_12_s_clips_both_validate():
    for end in (15.0, 22.0):
        Selection(shotId="s1", status="selected", decidedBy="judge", candidateId="yt:a", source="youtube", kind="video",
                  start=10.0, end=end, credit="Fuente: c", url="u")


def test_qa_checks_the_cap_of_its_own_channel():
    import inspect

    from pipeline import qa

    assert "tope.seconds(ctx)" in inspect.getsource(qa.run)


def test_the_longest_run_of_each_source():
    def shot(n, start, seconds, src, credit="Fuente: A"):
        return TimelineShot.model_validate({"id": f"s{n:03d}", "type": "broll", "from": start * 30, "durationInFrames":
                                            seconds * 30, "text": "t", "media": TimelineMedia(
                                                src=src, kind="video", source="youtube", credit=credit)}).model_dump(by_alias=True)

    timeline = {"fps": 30, "shots": [shot(1, 0, 4, "a.mp4"), shot(2, 4, 5, "a.mp4"), shot(3, 9, 3, "b.mp4", "Fuente: B"),
                                     shot(4, 12, 2, "a.mp4")]}
    runs = tope.longest_runs(timeline)
    assert runs[0] == {"source": "Fuente: A", "seconds": 9.0, "at": 0.0, "src": "a.mp4"}
    assert runs[1]["source"] == "Fuente: B" and runs[1]["seconds"] == 3.0
