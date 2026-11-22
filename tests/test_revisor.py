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
    assert flagged["s005"]["problem"] == "hueco_tapado" and "tapado con el clip del plano s003" in flagged["s005"]["evidence"]
    assert "s006" not in flagged and result["unreadable"] == ["s006"]

    final = tmp_path / "out" / "v" / "video-final.mp4"                       # now the finished video exists
    _clip(final, "testsrc2")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=14", "-pix_fmt",
                    "yuv420p", str(final)], check=True)
    result = revisor.review(tmp_path, "v", ask_model=lambda entries: ([], 0.0))
    assert result["unreadable"] == []                                        # read from the final video instead


def test_the_borrowed_copy_is_blamed_not_the_judges_choice():
    """newgym3: the wedding chosen by the judge for 9:57 and borrowed at 0:58. The early copy is the fault; a pair is
    counted once, on its weaker side (borrowed < filler < protagonist < the judge)."""

    items = [{"id": "s028", "at": 58, "method": "", "hashes": [7]},              # borrowed, first on screen
             {"id": "s100", "at": 300, "method": "protagonist-filler", "hashes": [99], "candidateId": "yt:A",
              "start": 10.0, "end": 12.0},
             {"id": "s217", "at": 603, "method": "judge", "hashes": [7]},          # the original, later
             {"id": "s220", "at": 610, "method": "judge", "hashes": [12345], "candidateId": "yt:A",
              "start": 10.5, "end": 12.5}]
    blamed = revisor.repeats(items, already={"s028"})
    assert "s217" not in blamed and "s028" not in blamed                       # the copy is flagged elsewhere, once
    assert list(blamed) == ["s100"] and "repite el plano s220" in blamed["s100"]   # the filler, not the judge


def test_a_shot_showing_another_shots_file_is_the_borrowed_one_even_with_its_own_selection():
    """newgym3-ideas2: s050 was judged but ended with no clip, and the edit covered it with s062's file; the revisor
    took s050 for the owner and blamed s062 as «repetido». The file name says whose it is."""

    assert revisor.file_owner("work/v/media_fallback/s062.mp4") == "s062"
    assert revisor.file_owner("work/v/media/s012-2.mp4") == "s012"
    assert revisor.file_owner("biblioteca/clips/abc.mp4") is None
    items = [{"id": "s050", "at": 111, "method": "judge", "hashes": [7], "borrowed": "s062"},
             {"id": "s062", "at": 151, "method": "protagonist", "hashes": [7]}]
    assert revisor.repeats(items, already={"s050"}) == {}                    # flagged once, as hueco tapado


def test_the_baseline_puts_every_video_in_one_table():
    results = [{"slug": "newgym3", "shots": 200, "asText": 7, "model": "m", "usd": 0.01, "unreadable": ["s9"],
                "flagged": [{"problem": "hueco_tapado"}] * 20 + [{"problem": "repetido"}] * 10 + [{"problem": "roto"}]}]
    text = revisor.baseline(results)
    assert "| newgym3 | 200 | 7 | — | — | — | — | 16 | 20 | 10 | 0 | — | 0 | 0 | 0 | 1 | 1 | m | 0.010 |" in text
    measured = revisor.baseline([{**results[0], "textShare": 48.5, "firstImage": 40.0}])
    assert "| newgym3 | 200 | 7 | 48.5 | 40.0 | — | — | 16 |" in measured
    labelled = [{"slug": "v", "shots": 100, "model": "m", "usd": 0.0, "flagged": [
        {"problem": "no_tiene_que_ver", "kind": "literal"}, {"problem": "no_tiene_que_ver", "kind": "ambiente"}]}]
    assert "| v | 100 | — | — | — | — | — | 2 | 0 | 0 | 2 | 1 |" in revisor.baseline(labelled)       # one of the two was a literal idea


def test_a_video_not_edited_yet_does_not_stop_the_baseline(tmp_path, monkeypatch, capsys):
    _video(tmp_path)
    monkeypatch.setattr(revisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(revisor, "ask", lambda *a, **k: ([], 0.0))
    assert revisor.main(["v", "aun-no", "--base"]) == 0
    text = (tmp_path / "out" / "_revisor_base.md").read_text()
    assert "| v | 4 | 0 |" in text and "| aun-no | sin montar todavía |" in text
    assert "aun-no: sin revisar" in capsys.readouterr().out


def test_what_goes_back_to_the_fill_in():
    """Bloque 3.3: measured faults always; literal ideas when sure; ambient ideas only objective faults; videos without
    ideas only objective and very sure; a borrowed clip becomes text."""

    rows = [{"id": "s001", "problem": "repetido", "by": "medida", "confidence": 1.0, "candidateId": "yt:A", "start": 1.0},
            {"id": "s002-2", "problem": "no_tiene_que_ver", "by": "modelo", "confidence": 0.9, "kind": "literal"},
            {"id": "s003", "problem": "no_tiene_que_ver", "by": "modelo", "confidence": 0.99, "kind": "ambiente"},
            {"id": "s004", "problem": "persona_equivocada", "by": "modelo", "confidence": 0.9, "kind": "ambiente"},
            {"id": "s005", "problem": "persona_equivocada", "by": "modelo", "confidence": 0.9, "kind": None},
            {"id": "s006", "problem": "dibujo_animado", "by": "modelo", "confidence": 0.97, "kind": None},
            {"id": "s007", "problem": "hueco_tapado", "by": "medida", "confidence": 1.0},
            {"id": "s008", "problem": "no_tiene_que_ver", "by": "modelo", "confidence": 0.7, "kind": "literal"}]
    wrong, as_text = revisor.to_fix({"flagged": rows}, {})
    assert sorted(wrong) == ["s001", "s002", "s004", "s006"] and as_text == ["s007"]
    assert wrong["s001"]["candidateId"] == "yt:A" and wrong["s002"]["by"] == "revisor"


def test_the_reviewer_stage_sends_back_once_and_redoes_the_fill_in_and_the_edit(tmp_path, monkeypatch):
    from pipeline import feedback, runner
    from pipeline.runner import Stage

    (tmp_path / "config.yaml").write_text("revisor: {enabled: false}\n")
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path)
    revisor.stage_run(ctx, review_fn=lambda: pytest.fail("off: not reviewed"))
    assert "skipped" in json.loads((ctx.out_dir / "revisor" / "revisor.json").read_text())

    ctx.config["revisor"]["enabled"] = True
    ran = []
    stages = [Stage(name, lambda c: [], lambda c: [], lambda c, n=name: ran.append(n), None, ()) for name in revisor.AGAIN]
    monkeypatch.setattr(runner, "STAGES", stages)
    looks = iter([{"flagged": [{"id": "s004", "problem": "repetido", "by": "medida", "confidence": 1.0,
                                "candidateId": "yt:A", "start": 3.0, "end": 5.0}]}, {"flagged": []}])
    revisor.stage_run(ctx, review_fn=lambda: next(looks))
    assert ran == list(revisor.AGAIN)
    assert all((ctx.work_dir / ".stages" / f"{n}.json").is_file() for n in revisor.AGAIN)    # not done a third time
    assert feedback.wrong_shots(ctx.work_dir) == {"s004": "Repetido"}
    summary = json.loads((ctx.out_dir / "revisor" / "revisor.json").read_text())
    assert summary["before"] == 1 and summary["flagged"] == [] and summary["sentBack"] == 1

    ran.clear()                                                                  # once per video, never in a loop
    revisor.stage_run(ctx, review_fn=lambda: {"flagged": [{"id": "s009", "problem": "repetido", "by": "medida",
                                                           "confidence": 1.0}]})
    assert ran == []


def test_your_labels_and_the_reviewers_are_both_read_yours_win(tmp_path):
    from pipeline import feedback

    (tmp_path / feedback.REVISION_AUTO).write_text(json.dumps({"wrong": {"s001": {"reason": "repetido"},
                                                                         "s002": {"reason": "roto"}},
                                                               "noBorrow": ["s009"]}))
    (tmp_path / feedback.REVISION).write_text(json.dumps({"wrong": {"s002": {"reason": "persona_equivocada"}}}))
    assert feedback.wrong_shots(tmp_path) == {"s001": "Repetido", "s002": "Sale otra persona"}
    assert feedback.no_borrow(tmp_path) == set()                       # 23-11: the reviewer never turns a shot into text
    assert feedback.no_borrow(tmp_path, holes=True) == {"s009"}
    assert feedback.no_borrow(tmp_path, sent_back=True, holes=True) == {"s001", "s002", "s009"}
    # s001 (repeated) keeps its clip when nothing better comes; s002 (broken) and what you marked do not
    assert feedback.keep_if_unreplaced(tmp_path) == {"s001"}


def test_the_reviewer_never_turns_a_shot_into_text():
    """ideas-pantallas-de-texto.md, 23-11: newideas had half its length in text, part of it from the reviewer's
    «sent back → text». Off by default; a shot sent back with nothing better keeps its own clip (timeline)."""

    import inspect

    from pipeline import timeline

    source = inspect.getsource(timeline)
    assert 'get("no_borrow_sent_back", False)' in source and 'get("huecos_a_texto", False)' in source
    assert "keep_if_unreplaced(ctx.work_dir)" in source


def test_the_score_of_every_video_and_the_panel(tmp_path):
    """1: with revisor.nota the stage scores the edit without sending anything back; «Puntería» gathers the scores per
    channel (the last five averaged) and each video's page shows its own."""

    import os
    import time

    from pipeline import web

    (tmp_path / "config.yaml").write_text("revisor: {nota: true}\n")
    (tmp_path / "materiales" / "gimnasia" / "a").mkdir(parents=True)
    (tmp_path / "materiales" / "gimnasia" / "config.yaml").write_text("canal: gimnasia\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "gimnasia.yaml").write_text("{}\n")
    ctx = RunContext.create("a", root=tmp_path)
    revisor.stage_run(ctx, review_fn=lambda: {"shots": 200, "asText": 7, "flagged": [{"problem": "repetido"}] * 30})
    saved = json.loads((ctx.out_dir / "revisor" / "revisor.json").read_text())
    assert saved["mode"] == "nota" and not (ctx.work_dir / "revision.auto.json").exists()      # nothing sent back
    older = tmp_path / "out" / "b" / "revisor" / "revisor.json"
    older.parent.mkdir(parents=True)
    older.write_text(json.dumps({"shots": 100, "flagged": [{"problem": "roto"}] * 25}))
    os.utime(older, (time.time() - 86400, time.time() - 86400))
    (tmp_path / "out" / "c" / "revisor").mkdir(parents=True)
    (tmp_path / "out" / "c" / "revisor" / "revisor.json").write_text(json.dumps({"skipped": "off"}))
    panel = web.punteria(tmp_path)
    by_channel = {c["channel"]: c for c in panel["channels"]}
    assert panel["videos"] == 2 and set(by_channel) == {"gimnasia", "—"}            # the skipped one is not a score
    gym = by_channel["gimnasia"]
    assert [v["slug"] for v in gym["videos"]] == ["a"] and gym["videos"][0]["per100"] == 15.0 and gym["recent"] == 15.0
    assert by_channel["—"]["videos"][0]["per100"] == 25.0 and gym["videos"][0]["asText"] == 7
    assert web.punteria(tmp_path, mine=["otro"])["videos"] == 0                    # a partner sees only theirs
    assert web._video_score(tmp_path / "out" / "a") == {"flagged": 30, "shots": 200, "per100": 15.0, "asText": 7}


def test_what_is_still_wrong_goes_to_the_phone_with_its_sheets(tmp_path, monkeypatch):
    from pipeline import notify

    (tmp_path / "config.yaml").write_text("{}\n")
    ctx = RunContext.create("v", root=tmp_path)
    sent = []
    monkeypatch.setattr(notify, "telegram", lambda c, text, photos=(): sent.append((text, list(photos))) or True)
    assert not revisor.still_wrong(ctx)                                    # the revisor did not run: nothing
    out = ctx.out_dir / revisor.OUT_DIR
    out.mkdir(parents=True)
    (out / "revisor.json").write_text(json.dumps({"skipped": "x"}))
    assert not revisor.still_wrong(ctx) and not sent
    for n in (1, 2, 10):
        (out / f"hoja-{n}.jpg").write_bytes(b"x")
    (out / "revisor.json").write_text(json.dumps({"mode": "cola", "shots": 50, "before": 6, "sentBack": 4, "flagged": [
        {"problem": "repetido"}, {"problem": "no_tiene_que_ver"}, {"problem": "repetido"}]}))
    assert revisor.still_wrong(ctx)
    text, photos = sent[-1]
    assert "3 de 50" in text and "antes 6" in text and revisor.PROBLEMS["repetido"] + ": 2" in text
    assert [p.name for p in photos] == ["hoja-1.jpg", "hoja-2.jpg", "hoja-10.jpg"]
    (tmp_path / "config.yaml").write_text("revisor: {aviso: false}\n")
    assert not revisor.still_wrong(RunContext.create("v", root=tmp_path))


def test_channels_the_revisor_keeps_finding_cartoons_in_are_learned_only_when_asked(tmp_path):
    from pipeline import feedback
    from pipeline.sourcing import common

    def flagged(slug, rows):
        out = tmp_path / "out" / slug / "revisor"
        out.mkdir(parents=True)
        (out / "revisor.json").write_text(json.dumps({"shots": 10, "flagged": rows}))

    cartoon = {"problem": "dibujo_animado", "channel": "Toons", "source": "youtube", "confidence": 0.9}
    flagged("a", [cartoon, cartoon, {**cartoon, "confidence": 0.5}])
    assert feedback.revisor_channels(tmp_path) == {}                       # one video, and one doubt: not yet
    flagged("b", [cartoon, {**cartoon, "problem": "no_tiene_que_ver", "channel": "News"},
                  {**cartoon, "channel": "Other"}])
    assert feedback.revisor_channels(tmp_path) == {"Toons": 3}
    try:
        assert feedback.load_learned(tmp_path) == [] and not common.LEARNED_BLOCKED_CHANNELS
        assert feedback.load_learned(tmp_path, from_revisor=True) == ["Toons"]
        assert common.LEARNED_BLOCKED_CHANNELS == {"toons"}
    finally:
        common.LEARNED_BLOCKED_CHANNELS = set()


def test_text_share_and_first_image_come_from_the_edit():
    """ideas-pantallas-de-texto.md: newideas, ~half in text and the first image at 0:40, invisible to «per 100»."""

    shots = [{"id": "s001", "type": "broll", "from": 0, "durationInFrames": 300},                     # 10 s of board
             {"id": "s002", "type": "chapter", "from": 300, "durationInFrames": 60},
             {"id": "s003", "type": "broll", "from": 360, "durationInFrames": 240, "media": {"kind": "video"}},
             {"id": "s004", "type": "broll", "from": 600, "durationInFrames": 300, "groupId": "panel-1"}]
    got = revisor.screen_measures({"fps": 30, "durationInFrames": 900, "shots": shots})
    assert got == {"textShare": 33.3, "firstImage": 12.0}


def test_sources_per_minute_and_functions_per_key_event():
    from types import SimpleNamespace as NS

    cover = lambda role: NS(coverage=NS(event="k1", name="gol", role=role))   # noqa: E731
    plan = {"s001": cover("accion"), "s002": cover("reaccion"), "s003": cover("testimonio"), "s004": NS(coverage=None)}
    shot = lambda n, start, src, credit: {"id": f"s{n:03d}", "type": "broll", "from": start, "durationInFrames": 300,  # noqa: E731
                                          "media": {"kind": "video", "src": src, "credit": credit}}
    timeline = {"fps": 30, "durationInFrames": 1800, "shots": [
        shot(1, 0, "media/s001.mp4", "Fuente: TV"), shot(2, 300, "media/s002.mp4", "Fuente: Grada"),
        shot(3, 600, "media/s001.mp4", "Fuente: TV"),                  # borrowed: the testimony was not found
        shot(4, 900, "media/s004.mp4", "Fuente: Otro")]}
    got = revisor.coverage_measures(plan, timeline)
    assert got["sourcesPerMinute"] == 3.0 and got["functions"] == "2/3"
    assert got["events"] == [{"event": "k1", "name": "gol", "asked": 3, "found": 2, "sources": 2}]
