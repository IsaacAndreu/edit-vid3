import json

from pipeline import report
from pipeline.context import RunContext


def _video(tmp_path, stock=0.02, wrong=0, weak=2):
    ctx = RunContext.create("v", root=tmp_path, config={"factcheck": {"notices": True}})
    (ctx.out_dir / "qa").mkdir(parents=True)
    ctx.work_dir.mkdir(parents=True)
    rows = [{"shotId": "a", "start": 0, "end": 6, "media": "m/a.mp4", "title": "Carlos Yulo floor final", "decidedBy": "judge"},
            {"shotId": "b", "start": 6, "end": 8, "media": "m/b.jpg", "decidedBy": "people"},
            {"shotId": "c", "start": 8, "end": 10, "media": "m/c.mp4", "title": "crowd", "decidedBy": "judge"}]
    (ctx.out_dir / "manifest.json").write_text(json.dumps({"shots": rows}))
    (ctx.out_dir / "qa" / "qa.json").write_text(json.dumps({"shareBySeconds": {"terceros (YouTube)": 1 - stock, "Pexels": stock},
                                                            "lowScore": [f"s{i} (0:0{i}) — nota 0.2" for i in range(weak)]}))
    (ctx.work_dir / "shots.json").write_text(json.dumps({"subject": "Carlos Yulo · gimnasia"}))
    (ctx.work_dir / "factcheck.json").write_text(json.dumps({"claims": [
        {"verdict": "wrong", "quote": "dato", "correction": "otro"}] * wrong}))
    return ctx


def test_ready_video(tmp_path):
    text = report.write(_video(tmp_path))
    assert text.startswith("✅ Listo para subir") and "Carlos Yulo en pantalla: 80%" in text
    assert (tmp_path / "out" / "v" / "resumen.md").is_file()


def test_video_that_needs_a_look(tmp_path):
    text = report.write(_video(tmp_path, stock=0.25, wrong=2, weak=20))
    assert text.startswith("⚠️ Revisar: mucho metraje genérico; 2 dato(s) del guion a corregir; 20 planos flojos")
    assert "… y 12 más" in text and "«dato» → otro" in text


def test_the_uploaded_script_is_the_script_no_fact_notices_by_default(tmp_path):
    ctx = _video(tmp_path, stock=0.5, wrong=2, weak=20)
    plain = RunContext.create("v", root=tmp_path, config={})
    text = report.text(report.card(plain))
    assert "dato" not in text
