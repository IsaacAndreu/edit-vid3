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
              "new_opening": "", "tips": []}
    with patch("pipeline.hook.complete_json", return_value=answer):
        r = hook.review(_ctx(tmp_path), "Fallos", "Afanasyeva se cayó en la final. " + FALLOS)
    assert r["ok"] and r["verdict"].startswith("✅")


def test_hook_ignores_chapter_headings():
    assert hook.split_sentences("## Capítulo 1\nUna frase. «Otra», dijo. ¿Y esto?") == ["Una frase.", "«Otra», dijo.", "¿Y esto?"]


def test_there_is_no_opening_before_the_voice():
    assert not hasattr(coldopen, "opening_seconds") and not hasattr(coldopen, "pick_teaser")
