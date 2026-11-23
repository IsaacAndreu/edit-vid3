"""When the image check stops a video, it fixes itself: the sentences without an image rewritten, the synthetic voice
made again and the video started over — or, if that cannot be done, it goes on anyway and says so."""

import json

import pytest

from pipeline import imagen_guion
from pipeline.context import RunContext


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    folder = tmp_path / "materiales" / "newgym9"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("Una frase sin imagen. Otra frase buena.\n")
    (folder / "titulo.txt").write_text("Simone Biles\n")
    (folder / "voz.mp3").write_bytes(b"old")
    (folder / "voz.genaipro.json").write_text("{}")
    return RunContext.create("newgym9", root=tmp_path)


def fix(ctx, script, title, refs):
    return {"script": script.replace("Una frase sin imagen.", "En Río 2016 ganó el oro."), "changed": 1,
            "before": {"shares": {"sin_imagen": 38}}, "after": {"shares": {"sin_imagen": 12}}}


def test_a_synthetic_voice_video_rewrites_its_script_remakes_the_voice_and_starts_over(ctx):
    made, told = [], []
    voice = lambda c: made.append((c.materials_dir / "voz.mp3").write_bytes(b"new"))
    with pytest.raises(imagen_guion.ScriptRewritten):
        imagen_guion.rescue(ctx, "38 % sin imagen", fix_fn=fix, ensure_voice=voice, send=told.append)
    folder = ctx.materials_dir
    assert "Río 2016" in (folder / "guion.txt").read_text() and "sin imagen" in (folder / "guion.original.txt").read_text()
    assert made and (folder / "voz.mp3").read_bytes() == b"new" and "38 % → 12 %" in told[0]
    again = imagen_guion.rescue(ctx, "36 % sin imagen", fix_fn=fix, ensure_voice=voice, send=told.append)
    assert again == "" and "ya se intentó" in told[-1]                     # once: then it goes on, saying so
    assert json.loads((ctx.work_dir / imagen_guion.GATE_FILE).read_text())["continued"] is True


def test_with_the_owners_own_voice_it_goes_on_without_touching_the_script(ctx):
    (ctx.materials_dir / "voz.genaipro.json").unlink()                      # a recorded voice: cannot be remade
    told = []
    assert imagen_guion.rescue(ctx, "40 % sin imagen", fix_fn=fix, send=told.append) == ""
    assert "Río" not in (ctx.materials_dir / "guion.txt").read_text() and "tuya grabada" in told[0]


def test_nothing_rewritable_goes_on_and_off_keeps_the_old_stop(ctx):
    told = []
    nothing = lambda *a: {"script": "", "changed": 0}
    assert imagen_guion.rescue(ctx, "40 %", fix_fn=nothing, send=told.append) == "" and "sin inventar" in told[0]
    (ctx.root / "config.yaml").write_text("guion: {arreglar_solo: false}\n")
    off = RunContext.create("newgym9", root=ctx.root)
    assert imagen_guion.rescue(off, "40 %", fix_fn=fix, send=told.append) == "40 %"


def test_the_run_starts_over_once_after_a_rewrite(ctx, monkeypatch):
    from pipeline import runner

    calls = []

    def fake(c, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise imagen_guion.ScriptRewritten("reescrito")
        return ["sourcing"]

    monkeypatch.setattr(runner, "_run_stages", fake)
    assert runner.run_stages(ctx) == ["sourcing"] and len(calls) == 2


ORIGINAL = """Nunca fue a unos Juegos Olímpicos. Llegó a cobrar mucho dinero.

## EL CAMBIO DE REGLAS DE 2021

Hasta 2021, en Estados Unidos, un deportista universitario no podía ganar dinero con su imagen. Ni anuncios.

LA VIDA DESPUÉS DE LA GIMNASIA

Si alguien pensaba que su fama se apagaría al dejar la gimnasia, se equivocaba.
"""

GLUED = ORIGINAL.replace("## EL CAMBIO DE REGLAS DE 2021\n\nHasta 2021", "## EL CAMBIO DE REGLAS DE 2021 Hasta julio de 2021") \
    .replace("LA VIDA DESPUÉS DE LA GIMNASIA\n\nSi alguien", "LA VIDA DESPUÉS DE LA GIMNASIA Tras el anuncio, si alguien")


def test_chapter_titles_go_back_on_their_own_line_newgym9():
    fixed = imagen_guion.restore_headings(ORIGINAL, GLUED)
    assert "## EL CAMBIO DE REGLAS DE 2021\n\nHasta julio de 2021" in fixed
    assert "LA VIDA DESPUÉS DE LA GIMNASIA\n\nTras el anuncio" in fixed
    assert imagen_guion.restore_headings(ORIGINAL, ORIGINAL) == ORIGINAL                 # nothing to repair: unchanged


def test_a_title_glued_to_a_sentence_is_never_sent_to_be_rewritten(ctx):
    sent = {}

    def review(c, script, title):
        return {"sinImagen": [{"n": 3, "text": "## EL CAMBIO DE REGLAS DE 2021 Hasta 2021, en Estados Unidos, un "
                                              "deportista universitario no podía ganar dinero con su imagen.", "idea": ""}],
                "shares": {"sin_imagen": 40}}

    def ask(user):
        sent["user"] = user
        return {"cambios": [{"n": 3, "nueva": "Hasta julio de 2021, la NCAA prohibía cobrar por la imagen."}]}

    out = imagen_guion.fix(ctx, ORIGINAL, review_fn=review, ask=ask)
    assert "[3] Hasta 2021" in sent["user"] and "[3] ## EL CAMBIO" not in sent["user"]
    assert "## EL CAMBIO DE REGLAS DE 2021\n\nHasta julio de 2021, la NCAA" in out["script"] and out["changed"] == 1


def test_the_repair_command_fixes_a_script_already_rewritten(ctx):
    (ctx.materials_dir / "guion.original.txt").write_text(ORIGINAL)
    (ctx.materials_dir / "guion.txt").write_text(GLUED)
    assert imagen_guion.repair(ctx.root, "newgym9") == 2
    assert imagen_guion.repair(ctx.root, "newgym9") == 0
