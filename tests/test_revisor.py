"""The automatic reviewer in report mode: measured faults (black frames, repeats) without a model, objective ones by
the vision model with a proof, a report and sheets — and nothing of the video changed."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipeline import revisor
from pipeline.context import RunContext

pytestmark = pytest.mark.skipif(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
                                reason="ffmpeg")


def _clip(path: Path, source: str, vf: str = "null") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = f"{source}{':' if '=' in source else '='}s=320x180:r=30:d=2"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", spec, "-vf", vf, "-pix_fmt", "yuv420p",
                    str(path)], check=True)


def _video(root: Path) -> Path:
    (root / "materiales" / "v").mkdir(parents=True)
    (root / "config.yaml").write_text("{}\n")
    ctx = RunContext.create("v", root=root)
    work = ctx.work_dir
    _clip(work / "media" / "s001.mp4", "testsrc")
    _clip(work / "media" / "s002.mp4", "color=c=black")
    _clip(work / "media" / "s003.mp4", "rgbtestsrc")
    _clip(work / "media" / "s004.mp4", "testsrc2")
    shots, plan, selections = [], [], []
    texts = ["Usain Bolt gana en Pekín.", "La noche antes de la final.", "Nadie lo esperaba en París.",
             "Volvió a correr en Londres."]
    for n, text in enumerate(texts):
        sid = f"s00{n + 1}"
        shots.append({"id": sid, "type": "broll", "from": n * 60, "durationInFrames": 60, "text": text,
                      "media": {"src": f"media/{sid}.mp4", "kind": "video", "source": "youtube"}})
        plan.append({"id": sid, "type": "broll", "startWord": n * 5, "endWord": n * 5 + 4, "start": n * 2.0,
                     "end": n * 2.0 + 2, "text": text, "chapter": 0,
                     "broll": {"visualIntent": f"intent {n}", "queries": ["a", "b", "c"], "queriesLocal": ["x"]}})
        selections.append({"shotId": sid, "status": "selected", "candidateId": "yt:AAA" if n in (0, 3) else f"yt:{n}",
                           "start": 10.0 if n in (0, 3) else 0.0, "end": 12.0 if n in (0, 3) else 2.0,
                           "url": "https://youtu.be/x", "title": "Bolt 2008", "source": "youtube", "decidedBy": "judge"})
    (work / "timeline.json").write_text(json.dumps({"fps": 30, "shots": shots}))
    (work / "shots.json").write_text(json.dumps({"shots": plan}))
    (work / "selection.json").write_text(json.dumps({"selections": selections}))
    return work


def test_report_mode_flags_measured_and_model_faults_with_proof(tmp_path):
    work = _video(tmp_path)
    before = {p: p.read_bytes() for p in work.rglob("*") if p.is_file()}
    seen = []

    def model(entries):
        seen.append([e["id"] for e in entries])
        assert all(len(e["images"]) == 2 for e in entries)
        answers = [{"n": e["n"], "verdict": "ok", "problem": "none", "evidence": "", "confidence": 0.1} for e in entries]
        third = next(e for e in entries if e["id"] == "s003")
        answers[entries.index(third)] = {"n": third["n"], "verdict": "wrong", "problem": "unrelated",
                                         "evidence": "la frase dice París; en la imagen sale un fractal", "confidence": 0.9}
        return answers, 0.01

    result = revisor.review(tmp_path, "v", ask_model=model)
    flagged = {r["id"]: r for r in result["flagged"]}
    assert flagged["s002"]["problem"] == "roto" and flagged["s002"]["by"] == "medida"
    assert flagged["s004"]["problem"] == "repetido" and "s001" in flagged["s004"]["evidence"]   # same stretch, same source
    assert flagged["s003"]["problem"] == "no_tiene_que_ver" and "París" in flagged["s003"]["evidence"]
    assert "s001" not in flagged
    assert seen == [["s001", "s003"]]                    # what is already measured is not paid for again
    out = tmp_path / "out" / "v" / "revisor"
    report = (out / "informe.md").read_text()
    assert "Planos marcados: 3" in report and "No tiene que ver con la frase" in report and "judge" in report
    assert (out / "hoja-1.jpg").is_file() and json.loads((out / "revisor.json").read_text())["usd"] == 0.01
    after = {p: p.read_bytes() for p in work.rglob("*") if p.is_file()}
    assert after == before                               # report mode: the video is untouched


def test_the_budget_stops_the_model_and_says_so(tmp_path):
    _video(tmp_path)
    (tmp_path / "config.yaml").write_text("revisor: {shots_per_sheet: 1, parallel: 1}\n")
    calls = []

    def model(entries):
        calls.append([e["id"] for e in entries])
        return [], 0.5

    result = revisor.review(tmp_path, "v", max_usd=0.4, ask_model=model)
    assert calls == [["s001"]] and result["stoppedAtBudget"]                  # s003 never asked: over the cap
    assert "parado al llegar al tope" in (tmp_path / "out" / "v" / "revisor" / "informe.md").read_text()


def test_repeats_ignore_pieces_of_the_same_shot():
    items = [{"id": "s001", "at": 0, "hashes": [5]}, {"id": "s001-2", "at": 2, "hashes": [5]},
             {"id": "s009", "at": 30, "hashes": [5 ^ 0b111]}]
    assert revisor.repeats(items) == {"s009": "repite el plano s001 (a los 0:00): fotogramas casi idénticos"}


def test_the_sheets_can_go_to_telegram(tmp_path, monkeypatch):
    from pipeline import notify

    _video(tmp_path)
    result = revisor.review(tmp_path, "v", ask_model=lambda entries: ([], 0.0))
    sent = []
    monkeypatch.setattr(notify, "telegram", lambda ctx, text, photos=(): sent.append((text, [p.name for p in photos])) or True)
    assert revisor.send_telegram(tmp_path, "v", result)
    text, photos = sent[0]
    assert "2 de 4 planos marcados" in text and "Repetido: 1" in text and photos == ["hoja-1.jpg"]


def test_borrowed_unreadable_and_final_video_frames(tmp_path):
    """A shot covered in the edit with another shot's clip says so; a clip that cannot be read is taken from the
    finished video; one that cannot be read at all is listed as not reviewed, never called broken."""

    work = _video(tmp_path)
    timeline = json.loads((work / "timeline.json").read_text())
    timeline["shots"].append({"id": "s005", "type": "broll", "from": 240, "durationInFrames": 60, "text": "hueco",
                              "media": {"src": "media/s003.mp4", "kind": "video", "source": "youtube"}})
    timeline["shots"].append({"id": "s006", "type": "broll", "from": 300, "durationInFrames": 60, "text": "se borró",
                              "media": {"src": "media/gone.mp4", "kind": "video", "source": "youtube"}})
    (work / "timeline.json").write_text(json.dumps(timeline))
    result = revisor.review(tmp_path, "v", ask_model=lambda entries: ([], 0.0))
    flagged = {r["id"]: r for r in result["flagged"]}
    assert flagged["s005"]["problem"] == "repetido" and "tapado con el clip del plano s003" in flagged["s005"]["evidence"]
    assert "s006" not in flagged and result["unreadable"] == ["s006"]

    final = tmp_path / "out" / "v" / "video-final.mp4"                       # now the finished video exists
    _clip(final, "testsrc2")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=14", "-pix_fmt",
                    "yuv420p", str(final)], check=True)
    result = revisor.review(tmp_path, "v", ask_model=lambda entries: ([], 0.0))
    assert result["unreadable"] == []                                        # read from the final video instead
