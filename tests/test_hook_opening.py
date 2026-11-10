from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipeline import coldopen, hook
from pipeline.context import RunContext

FALLOS = ("La gimnasia es uno de los deportes más elegantes que existen. Capaz de dejar a cualquiera con la boca abierta. "
          "Hoy repasamos los fallos más recordados. Empezamos con Shawn Johnson. Ganó el oro en viga en Pekín. "
          "Años después reveló que hablaban de Harry Potter. Seguimos con Gabby Douglas. Se cayó sentada sobre la viga. "
          "Afanasyeva sufrió una caída aparatosa en suelo.")


def _ctx(tmp_path: Path, config: dict | None = None) -> RunContext:
    return RunContext.create("Fallos", root=tmp_path, config=config or {})


def test_hook_flags_a_late_promise_and_a_generic_start(tmp_path):
    answer = {"promise": "ver fallos de gimnasia", "first_payoff": 7, "generic_opening": True, "strongest": 8,
              "problems": ["La frase 0 es genérica"], "new_opening": "Afanasyeva cayó. Y no fue la única.", "tips": ["x"]}
    with patch("pipeline.hook.complete_json", return_value=answer) as llm:
        r = hook.review(_ctx(tmp_path, {"gancho": {"payoff_seconds": 15}}), "Los Fallos De Gimnasia", FALLOS)
    sent = llm.call_args.kwargs["user"]
    assert "TÍTULO: Los Fallos De Gimnasia" in sent and "[7]" in sent
    assert r["payoffSentence"] == "Se cayó sentada sobre la viga."
    assert r["payoffSeconds"] > 15 and r["verdict"].startswith("❌") and not r["ok"]
    assert "Apertura propuesta" in hook.markdown(r)


def test_hook_ok_when_the_promise_comes_first(tmp_path):
    answer = {"promise": "fallos", "first_payoff": 0, "generic_opening": False, "strongest": 0, "problems": [],
              "first_kind": "momento", "end_promise": 1, "channel_intro": None, "new_opening": "", "tips": []}
    with patch("pipeline.hook.complete_json", return_value=answer):
        r = hook.review(_ctx(tmp_path), "Fallos", "Afanasyeva se cayó en la final. " + FALLOS.replace("Hoy repasamos los fallos más recordados. ", ""))
    assert r["ok"] and r["verdict"].startswith("✅")


def test_hook_ignores_chapter_headings():
    assert hook.split_sentences("## Capítulo 1\nUna frase. «Otra», dijo. ¿Y esto?") == ["Una frase.", "«Otra», dijo.", "¿Y esto?"]


def test_there_is_no_opening_before_the_voice():
    assert not hasattr(coldopen, "opening_seconds") and not hasattr(coldopen, "pick_teaser")


def test_the_three_rules_of_the_first_seconds(tmp_path):
    answer = {"promise": "fallos", "first_payoff": 1, "generic_opening": False, "strongest": 8, "problems": [],
              "first_kind": "contexto", "end_promise": None, "channel_intro": None,
              "new_opening": "Afanasyeva se cayó en la final. Y la última caída nadie la ha repetido nunca.", "replaces": 3,
              "tips": []}
    with patch("pipeline.hook.complete_json", return_value=answer):
        r = hook.review(_ctx(tmp_path), "Fallos", FALLOS)
    first, promise, intro = r["rules"]
    assert not first["ok"] and "contexto" in first["detail"] and not promise["ok"]
    # «Hoy repasamos los fallos…» at ~8 s: the video presented before the 15th second, even if the model missed it
    assert not intro["ok"] and "Hoy repasamos" in intro["detail"]
    with patch("pipeline.hook.complete_json", return_value=answer):
        r = hook.review(_ctx(tmp_path), "Fallos", FALLOS.replace("Hoy repasamos", "Hoy vamos a ver"))
    assert not r["rules"][2]["ok"] and "Hoy vamos a ver" in r["rules"][2]["detail"] and r["verdict"].startswith("❌")
    # the new opening takes the place of the first three sentences, the rest of the script as written
    assert r["scriptWithOpening"].startswith("Afanasyeva se cayó en la final. Y la última")
    assert "elegantes" not in r["scriptWithOpening"] and "Empezamos con Shawn Johnson." in r["scriptWithOpening"]
    assert "## Las tres reglas del arranque" in hook.markdown(r)


def test_with_opening_keeps_line_breaks_and_stops_where_the_text_differs():
    script = "La gimnasia es\nelegante. Nació en Grecia.\n\n## UNO\nSe cayó."
    sents = [{"n": 0, "start": 0, "text": "La gimnasia es elegante."}, {"n": 1, "start": 2, "text": "Nació en Grecia."},
             {"n": 2, "start": 4, "text": "Otra cosa."}]
    assert hook.with_opening(script, sents, "Se cayó en la final.", 3) == "Se cayó en la final.\n\n## UNO\nSe cayó."
    assert hook.with_opening(script, sents, "", 2) == ""
