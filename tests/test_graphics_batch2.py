from pipeline import graphics, motion, planner, timeline
from pipeline.config import PROJECT_ROOT
from pipeline.context import RunContext

TEXT = ("En la final de suelo Yulo sacó 15,000, Dolgopyat 14,966 y Jake Jarman 14,933. "
        "Su doble mortal carpado con giro es el salto que nadie más se atreve a hacer: tres giros y medio.")


def test_standings_need_three_said_scores():
    rows = [{"name": "Yulo", "score": "15,000"}, {"name": "Dolgopyat", "score": "14,966"},
            {"name": "Jake Jarman", "score": "14,933"}, {"name": "Nagornyy", "score": "14,800"}]
    out = graphics.clean("standings", {"title": "Final de suelo", "rows": rows}, TEXT, None, set())
    assert [r["name"] for r in out["rows"]] == ["Yulo", "Dolgopyat", "Jake Jarman"]          # 14,800 never said
    assert graphics.clean("standings", {"rows": rows[:2]}, TEXT, None, set()) is None


def test_strobe_and_replay_labels_come_from_the_script():
    assert graphics.clean("strobe", {"name": "doble mortal carpado", "note": "tres giros y medio"}, TEXT, None, set()) == {
        "type": "strobe", "name": "doble mortal carpado", "note": "tres giros y medio"}
    assert graphics.clean("strobe", {"name": "Yurchenko triple"}, TEXT, None, set()) is None
    replay = graphics.clean("replay", {"name": "el doble mortal"}, TEXT, None, set())
    assert replay == {"type": "replay", "name": "el doble mortal", "badge": "REPETICIÓN"}
    assert graphics.clean("replay", {"name": "la caída que lo cambió todo"}, TEXT, None, set())["name"] is None


def test_speed_ramp_time_map():
    parts = motion.ramp_map(peak=2.0, length=4.0, slow=0.25, half=0.5)
    assert parts == [(0.0, 1.5, 1.0), (1.5, 2.5, 0.25), (2.5, 4.0, 1.0)]
    assert motion.ramp_time(1.0, parts) == 1.0
    assert motion.ramp_time(2.0, parts) == 1.5 + 0.5 / 0.25                 # half of the slow part
    assert motion.ramp_time(4.0, parts) == 1.5 + 4.0 + 1.5


def test_format_outlines_and_cues():
    for fmt, word in (("tecnica", "TÉCNICA"), ("final", "FINAL")):
        assert word in planner.outline_system(RunContext.create("_t", root=PROJECT_ROOT, config={"format": fmt}))
    assert timeline.graphic_cues({"type": "strobe", "ghosts": [{}] * 3}, 150) == [("pop", 8), ("pop", 14), ("pop", 20)]
    assert timeline.graphic_cues({"type": "replay", "peak": 1.5}, 150) == [("impact", 45)]
