from pipeline import dub


def _timeline():
    media = {"src": "media/a.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X", "layout": "full"}
    shots = [{"id": "c1", "type": "broll", "from": 0, "durationInFrames": 30, "text": "", "media": media, "coldOpen": True}]
    shots += [{"id": f"s{i}", "type": "broll", "from": 30 + i * 60, "durationInFrames": 60, "text": "", "media": dict(media)}
              for i in range(5)]
    return {"slug": "x", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 330, "shots": shots,
            "groups": [{"id": "g", "kind": "stat", "from": 90, "durationInFrames": 60, "steps": [], "words": [],
                        "stat": {"value": "15.3", "label": "oro en suelo", "sign": "positive"}}],
            "labels": [{"kind": "place", "text": "PARÍS", "from": 150, "durationInFrames": 30}],
            "audio": {"voice": "audio/voz.mp3", "voiceFrom": 30, "clips": [], "speech": [], "sfx": []}}


def test_anchors_and_time_map_are_monotonic():
    old = [{"start": t} for t in (0, 2, 4, 6)]
    new = [{"start": t} for t in (0, 1, 3, 5)]
    points = dub.anchors([(1, 1), (2, 1), (3, 3), (9, 9)], old, new, 8.0, 6.0)
    assert points == [(0.0, 0.0), (2, 1), (6, 5), (8.0, 6.0)]     # (2,1) duplicate target and out-of-range dropped
    f = dub.time_map(points)
    assert f(0) == 0 and f(2) == 1 and f(4) == 3 and f(8) == 6


def test_retime_keeps_cold_open_and_moves_everything_else():
    out = dub.retime(_timeline(), lambda t: t * 0.5, 5.0, 5.0)      # narration twice as fast
    assert out["durationInFrames"] == 30 + 150
    assert [s["from"] for s in out["shots"]] == [0, 30, 60, 90, 120, 150]
    assert sum(s["durationInFrames"] for s in out["shots"]) == out["durationInFrames"]
    assert out["groups"][0]["from"] == 60 and out["groups"][0]["durationInFrames"] == 30
    assert out["labels"][0]["from"] == 90


def test_retime_caps_third_party_clips_at_five_seconds():
    out = dub.retime(_timeline(), lambda t: t * 3, 30.0, 5.0)       # three times slower
    assert all(s["durationInFrames"] <= 150 for s in out["shots"][:-1])
    assert sum(s["durationInFrames"] for s in out["shots"]) == out["durationInFrames"] == 30 + 900


def test_screen_texts_roundtrip_skips_names():
    t = _timeline()
    t["labels"].append({"kind": "name", "text": "CARLOS YULO", "from": 200, "durationInFrames": 30})
    texts = dub.screen_texts(t)
    assert "label:1" not in texts and texts["stat:g"] == "oro en suelo"
    dub.apply_texts(t, {**texts, "stat:g": "floor gold", "label:0": "PARIS"})
    assert t["groups"][0]["stat"]["label"] == "floor gold" and t["labels"][0]["text"] == "PARIS"
    assert t["labels"][1]["text"] == "CARLOS YULO"


def test_retime_with_a_moment_keeps_its_length_and_maps_around_it():
    t = _timeline()
    # a 30-frame moment inserted at voice frame 120 (video frame 150): shots after it moved by 30
    moment = {"id": "m01", "type": "broll", "from": 150, "durationInFrames": 30, "text": "", "coldOpen": True,
              "media": {"src": "coldopen/m.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}}
    for s in t["shots"]:
        if s["from"] >= 150:
            s["from"] += 30
    t["shots"].insert(3, moment)
    t["labels"] = []
    t["durationInFrames"] = 360
    t["audio"]["voiceGaps"] = [[120, 30]]
    t["audio"]["clips"] = [{"src": "coldopen/m.mp4", "from": 150, "durationInFrames": 30}]
    out = dub.retime(t, lambda v: v * 0.5, 5.0, 5.0)
    m = next(s for s in out["shots"] if s["id"] == "m01")
    assert m["durationInFrames"] == 30 and m["from"] == 30 + 60          # voice 4 s → 2 s
    assert out["audio"]["voiceGaps"] == [[60, 30]]
    assert out["audio"]["clips"][0]["from"] == m["from"]
    assert out["durationInFrames"] == 30 + 150 + 30
    assert sum(s["durationInFrames"] for s in out["shots"]) == out["durationInFrames"]


def test_speech_spans_split_at_pauses():
    words = [{"start": 0.0, "end": 1.0}, {"start": 1.2, "end": 3.0}]
    assert dub.speech_spans(words, 30, 10, pauses=[[60, 30]]) == [[10, 70], [100, 130]]


def test_graphic_texts_are_translated_but_not_paths_or_years():
    t = _timeline()
    t["groups"].append({"id": "graphic-1", "kind": "graphic", "from": 30, "durationInFrames": 60, "steps": [], "words": [],
                        "graphic": {"type": "timeline", "title": "El camino", "events": [{"year": "2019", "text": "Oro en Stuttgart"}],
                                    "media": {"src": "people/x.png", "kind": "image"}}})
    texts = dub.screen_texts(t)
    assert texts["graphic:graphic-1.title"] == "El camino" and "graphic:graphic-1.media.src" not in texts
    assert not any(k.endswith(".year") for k in texts)
    dub.apply_texts(t, {**texts, "graphic:graphic-1.title": "The road", "graphic:graphic-1.events.0.text": "Gold in Stuttgart"})
    g = t["groups"][-1]["graphic"]
    assert g["title"] == "The road" and g["events"][0] == {"year": "2019", "text": "Gold in Stuttgart"}
    assert g["media"]["src"] == "people/x.png"
