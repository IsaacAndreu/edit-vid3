"""Native vertical Shorts: a stretch of the video's own timeline as a 1080x1920 timeline, and the showy sentences."""

from __future__ import annotations

from pipeline import shorts


def _timeline():
    return {"slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 900,
            "shots": [{"id": "s1", "type": "broll", "from": 0, "durationInFrames": 300, "media": {"src": "a.mp4", "kind": "video"}},
                      {"id": "s2", "type": "broll", "from": 300, "durationInFrames": 300, "media": {"src": "b.mp4", "kind": "video"}},
                      {"id": "end", "type": "endscreen", "from": 600, "durationInFrames": 300}],
            "groups": [{"id": "g1", "kind": "graphic", "from": 200, "durationInFrames": 150, "graphic": {"type": "map"}},
                       {"id": "g2", "kind": "graphic", "from": 400, "durationInFrames": 300, "graphic": {"type": "lens"}}],
            "audio": {"voice": "audio/voz.mp3", "voiceFrom": 30, "speech": [(30, 600)], "sfx": [{"from": 10}], "voiceGaps": [(100, 15)]}}


def test_a_stretch_becomes_a_vertical_timeline_of_its_own():
    caps = [{"from": 260, "durationInFrames": 20, "words": []}, {"from": 500, "durationInFrames": 20, "words": []}]
    props = shorts.vertical_props(_timeline(), 250, 550, caps)
    assert props["width"] == 1080 and props["height"] == 1920 and props["durationInFrames"] == 300
    first, second = props["shots"]
    assert first["from"] == 0 and first["durationInFrames"] == 50 and first["offset"] == 250 and first["fullDuration"] == 300
    assert second["from"] == 50 and second["durationInFrames"] == 250 and second["offset"] == 0
    assert [g["id"] for g in props["groups"]] == ["g2"] and props["groups"][0]["durationInFrames"] == 150   # cut at the end
    assert [c["from"] for c in props["captions"]] == [10, 250]
    assert props["audio"]["voiceGaps"] == [] and props["audio"]["sfx"] == [] and props["endscreenFrames"] == 0


def test_sentences_with_a_graphic_on_screen_are_the_showy_ones():
    sents = [{"n": 0, "start": 0.0, "end": 4.0}, {"n": 1, "start": 6.0, "end": 9.0}, {"n": 2, "start": 15.0, "end": 18.0},
             {"n": 3, "start": 25.0, "end": 28.0}]
    # the map from 6.7 to 11.7 s, the lens from 13.3 to 23.3 s
    assert shorts.strong_sentences(_timeline(), sents, lambda t: t) == {1, 2}
