import json

from pipeline import editor
from pipeline.context import RunContext
from pipeline.schemas import Selection

TIMELINE = {
    "fps": 30, "durationInFrames": 300, "audio": {"voice": "audio/voz.mp3", "sfx": []},
    "shots": [{"id": "c1", "type": "chapter", "from": 0, "durationInFrames": 30, "text": "", "chapterTitle": "EL INICIO"}],
    "groups": [{"id": "graphic-1", "kind": "graphic", "from": 0, "durationInFrames": 90,
                "graphic": {"type": "map", "title": "De Manila a Tokio", "points": [{"name": "Manila"}]}},
               {"id": "stat-1", "kind": "stat", "from": 100, "durationInFrames": 60}],
    "labels": [{"kind": "name", "text": "CARLOS YULO", "from": 10, "durationInFrames": 60},
               {"kind": "place", "text": "MANILA · 2008", "from": 200, "durationInFrames": 60}],
}


def test_text_edits_and_removals():
    edits = {"texts": {"group:graphic-1:graphic.title": "Rumbo a Tokio", "group:graphic-1:graphic.points.0.name": "Manila (PH)",
                       "chapter:c1": "LOS ORÍGENES", "group:gone:title": "x", "group:graphic-1:graphic.nope.0": "x"},
             "removed": ["stat-1"], "labels": {"CARLOS YULO": "CARLOS EDRIEL YULO", "MANILA · 2008": ""}}
    out = editor.apply_to_timeline(json.loads(json.dumps(TIMELINE)), edits)
    graphic = out["groups"][0]["graphic"]
    assert graphic["title"] == "Rumbo a Tokio" and graphic["points"][0]["name"] == "Manila (PH)"
    assert [g["id"] for g in out["groups"]] == ["graphic-1"]                     # the stat is removed
    assert out["shots"][0]["chapterTitle"] == "LOS ORÍGENES"
    assert [label["text"] for label in out["labels"]] == ["CARLOS EDRIEL YULO"]   # an empty label is dropped


def test_footage_swap_becomes_the_selection(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={})
    (ctx.work_dir / "scores").mkdir(parents=True)
    (ctx.work_dir / "candidates").mkdir()
    option = {"candidateId": "yt:abc", "source": "youtube", "kind": "video", "pass": "fine", "start": 10.0, "end": 12.5,
              "analysisPath": "cache/videos/abc/a360_8.0_14.0.mp4", "scores": {}, "total": 0.41, "phash": "ff"}
    (ctx.work_dir / "scores" / "s001.json").write_text(json.dumps({"shotId": "s001", "options": [option]}))
    (ctx.work_dir / "candidates" / "s001.json").write_text(json.dumps({"shotId": "s001", "candidates": [{
        "id": "yt:abc", "url": "https://www.youtube.com/watch?v=abc", "title": "Yulo floor", "channel": "Olympics",
        "license": "youtube-standard", "credit": "Fuente: Olympics", "attribution": "Olympics — Yulo floor"}]}))
    original = Selection(shotId="s001", status="fallback", decidedBy="fallback")
    assert editor.apply_footage(ctx, [original]) == [original]                 # no edits: untouched
    editor.save(ctx, {"footage": {"s001": {"candidateId": "yt:abc", "start": 10.0}}, "texts": {}, "removed": [], "labels": {}})
    swapped = editor.apply_footage(ctx, [original])[0]
    assert swapped.decidedBy == "editor" and swapped.status == "selected" and swapped.start == 10.0 and swapped.end == 12.5
    assert swapped.credit == "Fuente: Olympics"
    options = editor.options(ctx, "s001")
    assert options[0]["previewFrom"] == 2.0 and options[0]["previewTo"] == 4.5    # inside the 360p analysis window


def test_edit_refreshes_from_the_pipeline_version(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={})
    ctx.write_json("timeline.base.json", TIMELINE)
    ctx.write_json("timeline.json", TIMELINE)
    editor.edit(ctx, {"type": "remove", "id": "graphic-1"})
    assert [g["id"] for g in ctx.read_json("timeline.json")["groups"]] == ["stat-1"]
    editor.edit(ctx, {"type": "restore", "id": "graphic-1"})
    assert [g["id"] for g in ctx.read_json("timeline.json")["groups"]] == ["graphic-1", "stat-1"]
