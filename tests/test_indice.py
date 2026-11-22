"""The scene index of the material de partida (bloque 4, second part): sources cut into scenes where the picture
changes, one line each from a vision model, kept once per source; a shot finds its scene by shared words."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from pipeline import indice
from pipeline.context import RunContext


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


def test_library_sources_are_indexed_only_when_asked_and_up_to_a_limit(tmp_path):
    from types import SimpleNamespace

    from pipeline.analysis import index_sources
    from pipeline.material import MATERIAL_QUERY

    def c(cid, query):
        return SimpleNamespace(id=cid, query=query)

    mine, lib1, lib2, other = (c("p:1", MATERIAL_QUERY), c("yt:1", "biblioteca: Biles"), c("yt:2", "biblioteca: Biles"),
                               c("yt:3", "Biles final"))
    off = index_sources(RunContext.create("v", root=tmp_path, config={}))
    assert [off(x) for x in (mine, lib1, other)] == [True, False, False]
    on = index_sources(RunContext.create("v", root=tmp_path, config={"indice": {"library": True, "library_sources": 1}}))
    assert [on(x) for x in (lib1, lib1, lib2, other, mine)] == [True, True, False, False, True]
    assert on.library == {"yt:1"}


def test_a_proof_finds_the_scene_where_the_line_is_said():
    from types import SimpleNamespace as NS

    from pipeline.indice import best_scene, proves, with_speech

    scenes = [{"start": 0, "end": 10, "en": "man talking in a car", "es": "coche, hombre", "tags": ""},
              {"start": 10, "end": 20, "en": "man talking in a kitchen", "es": "cocina, hombre", "tags": ""}]
    cues = [(2.0, 4.0, "nice weather today"), (12.0, 15.0, "I am the one who knocks")]
    spoken = with_speech(scenes, cues)
    assert spoken[1]["said"] == "I am the one who knocks" and "said" not in scenes[1]
    words = {"man", "talking", "car", "knocks"}
    assert best_scene(scenes, words)["start"] == 0                  # off: by picture words only, as before
    assert best_scene(spoken, words, said_weight=2)["start"] == 10  # on: where it is said wins
    assert proves(NS(coverage=NS(role="prueba"), text=""))
    assert proves(NS(coverage=None, text='Dice «yo soy el que llama a la puerta» en la cocina'))
    assert not proves(NS(coverage=NS(role="accion"), text="un hombre en la cocina"))
