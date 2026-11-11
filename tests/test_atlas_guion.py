"""pipeline/atlas_guion.py: tiempos estimados, órdenes de datos y el bucle de corrección del storyboard."""

import json
import shutil

from pipeline import atlas_guion


def test_estimated_timing_follows_the_script():
    t = atlas_guion.estimated_transcript("Una frase corta. Y otra frase que sigue después.")
    starts = [w["start"] for w in t["words"]]
    assert starts == sorted(starts) and t["words"][0]["word"] == "Una"
    # la pausa de fin de frase: «Y» empieza más tarde que el ritmo normal
    gap = t["words"][3]["start"] - t["words"][2]["start"]
    assert gap > 1 / atlas_guion.WORDS_PER_SECOND + 0.3
    assert t["duration_seconds"] > t["words"][-1]["end"] and t["estimated"]


def test_every_data_kind_becomes_an_atlas_data_command(tmp_path):
    cmds = {
        "contour": atlas_guion.data_commands({"kind": "contour", "region": "andes", "meters": 3500}, "x"),
        "profile": atlas_guion.data_commands({"kind": "profile", "id": "p", "from": [-77, -12], "to": [-68.1, -16.5]}, "x"),
        "cells": atlas_guion.data_commands({"kind": "cells", "id": "c", "bbox": [-72, -20, -65, -14]}, "x"),
        "terrain": atlas_guion.data_commands({"kind": "terrain", "id": "t", "bbox": [-72, -20, -65, -14], "smooth": 2}, "x"),
        "country": atlas_guion.data_commands({"kind": "country", "name": "Bolivia", "id": "bolivia"}, "x"),
    }
    assert cmds["contour"] == [["atlas:data", "--", "contour", "andes", "3500"]]
    assert cmds["profile"][0][-2:] == ["-77,-12", "-68.1,-16.5"]
    assert cmds["cells"][0][3:6] == ["c", "-72,-20,-65,-14", "9"]
    assert cmds["terrain"][0][-1] == "2" and cmds["country"][0][3:] == ["Bolivia", "bolivia"]
    region = {"kind": "region", "id": "zz-test-region", "bbox": [[-80, -25], [-60, -5]],
              "projection": {"type": "conicConformal", "rotate": [70, 0], "parallels": [-20, -10]}}
    try:
        assert atlas_guion.data_commands(region, "x") == [["atlas:data", "--", "region", "zz-test-region"]]
        written = json.loads((atlas_guion.PROJECT_ROOT / "scripts/atlas-data/regions/zz-test-region.json").read_text())
        assert written["width"] == 5600 and written["projection"]["parallels"] == [-20, -10]
    finally:
        (atlas_guion.PROJECT_ROOT / "scripts/atlas-data/regions/zz-test-region.json").unlink(missing_ok=True)


def test_the_pipeline_owns_audio_and_duration():
    board = {"meta": {"slug": "lo que diga la IA", "duration": 99}, "audio": {"voice": "inventada.mp3"}, "scenes": []}
    silent = atlas_guion.with_audio(board, "Mi Video 2", "atlas-work/mi-video-2/transcript.json", None, 42.0)
    assert silent["meta"]["slug"] == "mi-video-2" and silent["meta"]["duration"] == 42.0
    assert silent["audio"] == {"transcript": "atlas-work/mi-video-2/transcript.json"}
    voiced = atlas_guion.with_audio(board, "v", "t.json", "atlas-work/v/voz.mp3", None)
    assert "duration" not in voiced["meta"] and voiced["audio"]["voice"] == "atlas-work/v/voz.mp3"


def test_validation_errors_go_back_to_the_model_until_it_fixes_them():
    slug = "zz-test-guion"
    work = atlas_guion.PUBLIC / "atlas-work" / slug
    work.mkdir(parents=True, exist_ok=True)
    script = "Por qué los aviones evitan el Tíbet. El suelo es alto."
    (work / "transcript.json").write_text(json.dumps(atlas_guion.estimated_transcript(script)))
    path = atlas_guion.PROJECT_ROOT / "storyboards" / f"{slug}.json"

    def scene(theme, anchor):
        return {"id": "a", "type": "atlas-statement", "start": {"t": 0}, "theme": theme, "enter": "fade",
                "title": "El suelo *es alto*", "titleAt": {"say": anchor}}

    def board(theme, anchor):
        return {"storyboard": {"meta": {"slug": slug, "title": "x", "brand": {"name": "ATLAS", "icon": "✦"}, "chapters": []},
                               "audio": {}, "scenes": [scene(theme, anchor)]}, "data": []}

    answers = [board("sepia", "el suelo es alto"), board("paper", "frase que no existe"), board("paper", "el suelo es alto")]
    prompts = []

    def ask(system, user):
        prompts.append(user)
        return answers[len(prompts) - 1]

    try:
        result = atlas_guion.draft(ask, slug, script, "Una frase en pantalla.", 6.0, path, f"atlas-work/{slug}/transcript.json", None)
        assert len(prompts) == 3
        assert "theme" in prompts[1] and "no aparece en la transcripción" in prompts[2]
        assert result["storyboard"]["scenes"][0]["theme"] == "paper"
        assert "atlas-relief-map" in atlas_guion.catalog() and "![" not in atlas_guion.catalog()
    finally:
        path.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)


def test_chapter_lines_are_not_spoken():
    text = "Primera frase.\n\n## LA MANCHA SOBRE EL MAPA\n\nSegunda frase."
    assert atlas_guion.spoken_script(text) == "Primera frase.\n\n\nSegunda frase."
    words = [w["word"] for w in atlas_guion.estimated_transcript(atlas_guion.spoken_script(text))["words"]]
    assert "##" not in words and "MANCHA" not in words


def test_a_storyboard_channel_needs_only_the_script(tmp_path):
    (tmp_path / "guion.txt").write_text("Hola.")
    engine = {"visual": {"style": "atlas", "engine": "storyboard"}}
    assert atlas_guion.is_atlas_folder(tmp_path, engine)
    assert not atlas_guion.is_atlas_folder(tmp_path, {"visual": {"style": "atlas"}})   # el Atlas de globo de siempre
    (tmp_path / "escenas.md").write_text("1. …")
    assert atlas_guion.is_atlas_folder(tmp_path)


def test_the_model_plans_the_scenes_from_the_script_and_reuses_the_data():
    seen = []

    def ask(system, user):
        seen.append((system, user))
        return {"escenas": "1. «El suelo es alto»: atlas-statement"}

    assert atlas_guion.plan(ask, "El suelo es alto.") == "1. «El suelo es alto»: atlas-statement"
    system, user = seen[0]
    assert "LITERAL" in system and "atlas-relief-map" in system
    assert "GEOGRAFÍA YA GENERADA" in user and "región andes" in user
