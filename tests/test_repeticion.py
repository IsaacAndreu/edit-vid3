"""Repetition risk (pipeline/repeticion.py): the three checks YouTube's «mass-produced content» rule is about —
title skeleton, thumbnail layout and footage reused under a new script."""

from __future__ import annotations

import numpy as np

from pipeline import repeticion


def test_the_same_title_skeleton_with_new_nouns_is_flagged():
    assert repeticion.skeleton("Por qué Japón es el país más raro del mundo") == \
        ["por", "qué", "_", "es", "el", "_", "más", "_", "del", "_"]
    earlier = ["Por qué Islandia es el país más caro del mundo", "Por qué Bután es el país más feliz del mundo",
               "La ciudad que se hunde 10 cm al año"]
    assert repeticion.title_check("Por qué Chile es el país más largo del mundo", earlier)["status"] == "warn"
    assert repeticion.title_check("El tren que cruza un desierto de sal", earlier)["status"] == "ok"


def test_a_thumbnail_with_the_same_composition_is_flagged_whatever_the_photo():
    def thumb(face_left: bool, tint: int):
        img = np.full((720, 1280, 3), 40 + tint, np.uint8)
        x = 100 if face_left else 800
        img[150:650, x:x + 380] = 230                          # the big bright block (a face, an object)
        img[60:160, 700 if face_left else 100:1200 if face_left else 600] = 255   # the text
        return repeticion.layout(img)

    mine = [thumb(True, 0)]
    same = [thumb(True, t) for t in (5, 10, 15)]
    other = [thumb(False, t) for t in (5, 10, 15)]
    assert repeticion.thumbnail_check(mine, same)["status"] == "warn"
    assert repeticion.thumbnail_check(mine, other)["status"] == "ok"


def test_footage_already_used_by_the_channel_is_counted():
    earlier = [{"candidateId": "yt:a", "sourceStart": 10.0, "phash": "f" * 16}, {"candidateId": "yt:b", "sourceStart": 50.0}]
    shots = [{"media": "m1", "candidateId": "yt:a", "sourceStart": 11.0},           # the same moment of the same video
             {"media": "m2", "candidateId": "yt:b", "sourceStart": 200.0},          # same video, another moment: fine
             {"media": "m3", "candidateId": "yt:c", "sourceStart": 0.0, "phash": "f" * 15 + "e"},   # the same picture
             {"media": "m4", "candidateId": "yt:d", "sourceStart": 0.0}, {"media": "m5", "candidateId": "yt:e"}]
    check = repeticion.visuals_check(shots, earlier)
    assert check["status"] == "warn" and check["text"].startswith("2 de 5 planos")
    assert repeticion.visuals_check([], earlier)["status"] == "ok"
