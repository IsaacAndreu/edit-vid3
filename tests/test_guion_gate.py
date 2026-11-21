"""guion.revisar_antes: the script read before the first paid search; «parar» stops a script nobody can show."""

import inspect
from types import SimpleNamespace

from pipeline import imagen_guion, runner


def _ctx(tmp_path, cfg):
    (tmp_path / "m").mkdir(parents=True)
    (tmp_path / "m" / "guion.txt").write_text("Una frase. Otra frase más larga aquí.", encoding="utf-8")
    return SimpleNamespace(section=lambda name: cfg if name == "guion" else {}, materials_dir=tmp_path / "m",
                           work_dir=tmp_path / "w", slug="v")


def _result(sin):
    return {"shares": {"imagen": 100 - sin, "ambiente": 0, "sin_imagen": sin}, "verdict": f"{sin} % sin imagen",
            "sinImagen": [{"n": 3, "text": "imagina que…", "idea": "di la fecha y el lugar"}]}


def test_off_by_default_and_no_call(tmp_path):
    called = []
    assert imagen_guion.gate(_ctx(tmp_path, {}), review_fn=lambda *a: called.append(1)) is None
    assert called == []


def test_parar_stops_a_script_mostly_without_images_and_says_why(tmp_path):
    sent = []
    ctx = _ctx(tmp_path, {"revisar_antes": "parar"})
    stopped = imagen_guion.gate(ctx, review_fn=lambda *a: _result(70), send=sent.append)
    assert stopped and "70 %" in stopped
    assert "di la fecha y el lugar" in sent[0] and "PARADO" in sent[0]
    # the same script again: read again (you have to change it, or switch to «aviso»)
    assert imagen_guion.gate(ctx, review_fn=lambda *a: _result(70), send=sent.append)


def test_aviso_only_warns_once_per_script(tmp_path):
    sent, calls = [], []
    ctx = _ctx(tmp_path, {"revisar_antes": "aviso"})

    def review(*a):
        calls.append(1)
        return _result(50)

    assert imagen_guion.gate(ctx, review_fn=review, send=sent.append) is None
    assert imagen_guion.gate(ctx, review_fn=review, send=sent.append) is None
    assert len(calls) == 1 and len(sent) == 1 and "PARADO" not in sent[0]


def test_a_good_script_goes_on_quietly_and_a_failing_check_never_stops(tmp_path):
    sent = []
    assert imagen_guion.gate(_ctx(tmp_path, {"revisar_antes": "parar"}), review_fn=lambda *a: _result(5),
                             send=sent.append) is None
    assert sent == []

    def broken(*a):
        raise RuntimeError("sin clave")

    assert imagen_guion.gate(_ctx(tmp_path / "b", {"revisar_antes": "parar"}), review_fn=broken, send=sent.append) is None


def test_the_runner_asks_before_the_first_paid_stage_and_claude_reads_it():
    source = inspect.getsource(runner)
    assert source.index("stopped = gate(ctx)") > source.index("problems = video_problems(ctx)")
    assert 'section = "guion" if ctx.section("guion").get("model") else "planner"' in inspect.getsource(imagen_guion)
