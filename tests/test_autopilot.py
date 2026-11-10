"""Channel autopilot (pipeline/autopilot.py): the radar's outliers become candidates with their evidence, and a
candidate becomes the channel's own video (idea → script → a new video waiting for its voice), at most per_day."""

from __future__ import annotations

import json
from datetime import date

from pipeline import autopilot


def _radar(root, top):
    folder = root / "out" / "_radar"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{date.today().isoformat()}.json").write_text(json.dumps({"date": date.today().isoformat(),
                                                                        "channels": {"lugares": {"top": top}}}))
    (root / "canales").mkdir(exist_ok=True)
    (root / "canales" / "lugares.yaml").write_text("format: explicativo\n")
    (root / "config.yaml").write_text("ideas:\n  about: lugares\n")


TOP = [{"id": "a1", "title": "Por qué nadie vive en Kerguelen", "channel": "X", "ratio": 6.0, "views": 90000, "viewsPerDay": 7200, "new": True},
       {"id": "a2", "title": "Por qué Groenlandia es blanca", "channel": "Y", "ratio": 5.0, "views": 50000},
       {"id": "a3", "title": "El tren del hierro", "channel": "Z", "ratio": 2.0, "views": 30000},
       {"id": "a4", "title": "La isla perdida", "channel": "Z", "ratio": 2.2, "views": 20000}]


def test_candidates_carry_their_evidence_and_skip_what_was_made_or_refused(tmp_path):
    _radar(tmp_path, TOP)
    found = autopilot.candidates(tmp_path, "lugares")
    assert [c["id"] for c in found] == ["a1", "a2", "a3", "a4"]
    assert found[0]["evidence"] == ["x6.0 lo normal de su canal", "300 visitas/hora (X)",
                                    "los títulos «Por…» hacen x1.5 en el nicho", "nuevo hoy"]
    autopilot.skip(tmp_path, "lugares", "a3")
    assert [c["id"] for c in autopilot.candidates(tmp_path, "lugares")] == ["a1", "a2", "a4"]


def test_the_best_candidate_becomes_a_new_video_once_a_day(tmp_path, monkeypatch):
    _radar(tmp_path, TOP)
    monkeypatch.setattr(autopilot, "idea_from", lambda root, channel, video: {"title": "La isla donde nadie vive", "angleTag": "el lugar imposible"})
    import pipeline.organizar as organizar

    monkeypatch.setattr(organizar, "draft_script", lambda root, channel, idea: {
        "title": idea["title"], "script": "Frase del guion. " * 80, "words": 240, "format": "explicativo"})
    autopilot.configure(tmp_path, "lugares", on=True)
    assert autopilot.due_channels(tmp_path) == ["lugares"]
    autopilot.run_if_due(tmp_path)
    made = autopilot.channel_state(tmp_path, "lugares")["made"]
    assert len(made) == 1 and made[0]["from"] == "a1" and made[0]["angle"] == "el lugar imposible"
    folder = tmp_path / "materiales" / "lugares" / made[0]["slug"]
    assert (folder / "guion.txt").read_text().startswith("Frase del guion.")
    assert "format: explicativo" in (folder / "config.yaml").read_text()
    assert autopilot.due_channels(tmp_path) == []                    # today's is done
    assert "a1" not in [c["id"] for c in autopilot.candidates(tmp_path, "lugares")]
