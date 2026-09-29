import json
import subprocess

from pipeline import edit_model
from pipeline.context import RunContext


def base():
    return {
        "fps": 30, "durationInFrames": 360, "title": "T", "slug": "v",
        "shots": [{"id": "s001", "type": "broll", "from": 0, "durationInFrames": 90, "text": "uno",
                   "media": {"src": "media/s001.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: A"}},
                  {"id": "s002", "type": "broll", "from": 90, "durationInFrames": 90, "text": "dos",
                   "media": {"src": "media/s002.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: B"}},
                  {"id": "s003", "type": "broll", "from": 180, "durationInFrames": 90, "text": "tres",
                   "media": {"src": "media/s003.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: C"}},
                  {"id": "s004", "type": "broll", "from": 270, "durationInFrames": 90, "text": "cuatro",
                   "media": {"src": "media/s004.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: D"}}],
        "groups": [{"id": "graphic-1", "kind": "graphic", "from": 100, "durationInFrames": 60, "graphic": {"type": "kinetic", "lines": ["HOLA"]}}],
        "labels": [{"kind": "name", "text": "YULO", "from": 10, "durationInFrames": 60}],
        "transitions": [{"kind": "whip", "from": 84, "durationInFrames": 12}],
        "shakes": [],
        "audio": {"voice": "audio/voz.wav", "voiceFrom": 0, "voiceGaps": [], "speech": [[0, 360]], "clips": [],
                  "musicParts": [{"src": "audio/intriga-a.mp3", "from": 0, "durationInFrames": 180, "mood": "intriga"},
                                 {"src": "audio/triunfo-b.mp3", "from": 180, "durationInFrames": 180, "mood": "triunfo"}],
                  "sfx": [{"src": "audio/whoosh-espada.mp3", "from": 88, "volume": 0.2},
                          {"src": "audio/pop-synth.mp3", "from": 110, "volume": 0.25}]},
    }


STORY = {"events": [{"label": "a", "startWord": 0, "tag": "CASO A"}, {"label": "b", "startWord": 20, "tag": "CASO B"}],
         "shots": [{"id": "s001", "startWord": 0}, {"id": "s002", "startWord": 10}, {"id": "s003", "startWord": 20},
                   {"id": "s004", "startWord": 30}]}


def test_trim_moves_the_cut_and_what_rides_on_it():
    t = edit_model.build(base(), {"cuts": {"s002": 70}})
    assert [(s["from"], s["durationInFrames"]) for s in t["shots"][:2]] == [(0, 70), (70, 110)]
    assert t["transitions"][0]["from"] == 64                    # the whip is centred on the new cut
    assert t["audio"]["sfx"][0]["from"] == 68                    # and its whoosh goes with it
    clamped = edit_model.build(base(), {"cuts": {"s002": 175}})
    assert clamped["shots"][1]["durationInFrames"] == edit_model.MIN_SHOT


def test_graphic_moves_with_its_sounds_and_swaps():
    t = edit_model.build(base(), {"timing": {"graphic-1": [200, 45]}, "media": {"s001": "s004", "s004": "s001"},
                                  "sfx": {"volume": {"whoosh-espada.mp3@88": 0.05}, "added": [{"src": "audio/pop-synth.mp3", "from": 300, "volume": 0.3}]}})
    assert (t["groups"][0]["from"], t["groups"][0]["durationInFrames"]) == (200, 45)
    assert [s["from"] for s in t["audio"]["sfx"]] == [88, 210, 300]   # the pop rides with its graphic
    assert t["audio"]["sfx"][0]["volume"] == 0.05
    assert t["shots"][0]["media"]["src"] == "media/s004.mp4" and t["shots"][3]["media"]["src"] == "media/s001.mp4"


def test_added_templates_labels_and_music():
    added = {"id": "user-1", "kind": "graphic", "from": 30, "durationInFrames": 90, "graphic": {"type": "kinetic", "lines": ["NUEVO"]}}
    t = edit_model.build(base(), {"added": [added], "addedLabels": [{"kind": "place", "text": "PARÍS", "from": 200, "durationInFrames": 60}],
                                  "labelTiming": {"YULO": [20, 50]}, "music": {"1": "assets/music/remontada-x.mp3"},
                                  "own": {"s003": {"src": "editor/uploads/mio.mp4", "kind": "video"}}})
    assert [g["id"] for g in t["groups"]] == ["user-1", "graphic-1"]
    assert [(l["text"], l["from"]) for l in t["labels"]] == [("YULO", 20), ("PARÍS", 200)]
    assert t["audio"]["musicParts"][1]["mood"] == "remontada"
    assert t["shots"][2]["media"]["credit"] == "Fuente: propia"


def test_scenes_follow_the_story():
    found = edit_model.scenes(base(), STORY, min_seconds=1)
    assert [(s["title"], s["shots"]) for s in found] == [("CASO A", ["s001", "s002"]), ("CASO B", ["s003", "s004"])]


def test_reorder_moves_everything_and_recuts_the_voice(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={})
    (ctx.work_dir / "audio").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", str(ctx.work_dir / "audio" / "voz.wav")],
                   check=True)
    t = edit_model.build(base(), {"order": ["sc-s003", "sc-s001"]}, ctx, STORY)
    assert [s["id"] for s in t["shots"]] == ["s003", "s004", "s001", "s002"]
    assert [s["from"] for s in t["shots"]] == [0, 90, 180, 270]
    assert t["groups"][0]["from"] == 280 and t["audio"]["voiceFrom"] == 0 and t["audio"]["voice"].startswith("editor/voz-")
    assert t["edited"]["blocks"] == [[180, 360, 0], [0, 180, 180]]
    assert [p["src"] for p in t["audio"]["musicParts"]] == ["audio/triunfo-b.mp3", "audio/intriga-a.mp3"]
    deleted = edit_model.build(base(), {"deleted": ["sc-s001"]}, ctx, STORY)
    assert deleted["durationInFrames"] == 180 and [s["id"] for s in deleted["shots"]] == ["s003", "s004"]
    assert deleted["groups"] == []                                # the graphic was in the deleted scene
