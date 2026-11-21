"""The scene index of the material de partida (bloque 4, second part): sources cut into scenes where the picture
changes, one line each from a vision model, kept once per source; a shot finds its scene by shared words."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from pipeline import indice


def test_scenes_are_cut_where_the_picture_changes_or_every_twenty_seconds():
    a, b = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    times = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
    vectors = np.array([a, a, a, b, b, b, b, b, b, b, b, b])
    scenes = indice.segment(times, vectors, cut=0.82, longest=20, step=5)
    assert [(s, e) for s, e, _ in scenes] == [(0, 15), (15, 35), (35, 55), (55, 60)]   # a change, then 20 s pieces
    assert scenes[0][2] == 1                                                         # the middle thumbnail


def test_a_shot_finds_its_scene_by_shared_words():
    scenes = [{"start": 0, "end": 10, "en": "title card with a logo", "es": "logo, título", "tags": ""},
              {"start": 10, "end": 30, "en": "red sports car speeding along a beach at night", "es": "coche, playa, noche",
               "tags": "Vice Beach de noche"},
              {"start": 30, "end": 50, "en": "bank robbery shootout inside", "es": "banco, atraco", "tags": ""}]
    assert indice.best_scene(scenes, {"persecucion", "coche", "playa", "noche"})["start"] == 10
    assert indice.best_scene(scenes, {"atraco", "banco"})["start"] == 30
    assert indice.best_scene(scenes, {"avion"}) is None                              # nothing in common: no scene


def test_a_source_is_described_once_and_kept(tmp_path, monkeypatch):
    import cv2

    from pipeline.context import RunContext
    from pipeline.schemas import Candidate

    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={})
    rng = np.random.default_rng(1)
    sheet = rng.integers(40, 220, (90, 1600, 3), dtype=np.uint8)             # textured: not a blank thumbnail
    cv2.imwrite(str(tmp_path / "sb.jpg"), sheet)
    board = {"sheets": ["sb.jpg"], "columns": 10, "rows": 1, "tileWidth": 160, "tileHeight": 90, "interval": 5.0, "frames": 10}
    clip_candidate = Candidate.model_validate({
        "id": "propio:abc", "source": "propio", "kind": "video", "url": "file:x.mp4", "title": "Vice Beach de noche",
        "channel": "material propio", "license": "propio", "credit": "Fuente: material propio", "attribution": "x",
        "query": "material de partida", "rankScore": 2.0, "durationSeconds": 50, "storyboard": board})
    calls = []

    def describe(ctx, tiles):
        calls.append(len(tiles))
        return [{"en": f"scene {n}", "es": "coche, playa"} for n in range(len(tiles))]

    monkeypatch.setattr(indice, "describe", describe)
    fake_clip = SimpleNamespace(embed_images=lambda tiles: np.array(
        [[1.0, 0.0] if n < 5 else [0.0, 1.0] for n in range(len(tiles))]))
    scenes = indice.scenes_for(ctx, clip_candidate, fake_clip, {})
    assert len(scenes) == 4 and scenes[0]["tags"] == "Vice Beach de noche" and calls == [4]   # a change and the 20 s cap
    assert indice.scenes_for(ctx, clip_candidate, fake_clip, {}) == scenes and calls == [4]   # kept, not described again
