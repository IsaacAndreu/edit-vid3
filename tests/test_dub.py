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
