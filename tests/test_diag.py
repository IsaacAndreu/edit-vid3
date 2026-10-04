import json
import sys

from pipeline import diag
from pipeline.context import RunContext


def test_log_keeps_everything_with_times(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={})
    with diag.logging(ctx):
        print("[7/15] ingest: ejecutando…")
        print("   Tiempos YouTube: download 40× 71.3 s · espera por límite 3× 120.0 s")
        print("   AVISO yt-dlp: yt-dlp no puede resolver los retos de YouTube")
        sys.stderr.write("un error\n")
    text = (ctx.out_dir / "log.txt").read_text("utf-8")
    assert "ingest: ejecutando" in text and "un error" in text and text.count(":") > 6
    facts = diag._log_facts(ctx)
    assert facts["youtube"]["ingest"]["download"] == (40, 71.3)
    assert facts["avisos_ytdlp"] == ["yt-dlp no puede resolver los retos de YouTube"]


def test_hints_explain_slow_downloads_failures_and_stock(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={"report": {"max_stock": 0.1}, "factcheck": {"notices": True}})
    data = {"entorno": {"yt-dlp-ejs": "0.8.0", "javascript": "deno", "disco_libre_gb": 200},
            "youtube": {"ingest": {"download": (40, 71.3), "espera por límite": (3, 120.0)}},
            "descarga": {"causas": {"YouTube devolvió un tramo vacío": ["s1", "s2", "s3"],
                                    "clip 4:3/vertical rechazado (versión antigua)": ["s4"]}},
            "pantalla": {"terceros (YouTube)": 0.8, "Pexels": 0.2}, "relleno": {"metodos": {"pexels-video": 20}},
            "juez": {"shots": 100, "fallback": 30}, "verificacion": {"wrong": 2}, "render_fps": 3.0}
    tips = " ".join(diag.hints(data, ctx))
    for expected in ("71 s por tramo", "min por límites", "tramo vacío", "git pull", "20%", "30 de 100", "2 dato", "3.0 fps"):
        assert expected in tips, expected


def test_write_never_breaks_and_reports_the_error(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={})
    try:
        raise RuntimeError("fallo de prueba")
    except RuntimeError as error:
        diag.write(ctx, error)
    report = (ctx.out_dir / "diagnostico.md").read_text("utf-8")
    assert "fallo de prueba" in report and "## Qué mejorar" in report
    assert json.loads((ctx.work_dir / "diag.json").read_text("utf-8"))["error"] == "RuntimeError: fallo de prueba"
