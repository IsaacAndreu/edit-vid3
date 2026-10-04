from __future__ import annotations

import json
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


def test_every_long_video_gets_an_opening_unless_it_says_otherwise(tmp_path):
    assert coldopen.opening_seconds(_ctx(tmp_path, {"apertura": {"seconds": 7}})) == 7
    assert coldopen.opening_seconds(_ctx(tmp_path, {})) == 7                                        # code default
    assert coldopen.opening_seconds(_ctx(tmp_path, {"timeline": {"cold_open_seconds": 10}})) == 10
    assert coldopen.opening_seconds(_ctx(tmp_path, {"timeline": {"cold_open_seconds": 0}})) == 0     # Shorts
    assert coldopen.opening_seconds(_ctx(tmp_path, {"apertura": {"enabled": False}})) == 0


def _story(ctx: RunContext) -> None:
    ctx.work_dir.mkdir(parents=True)
    words, shots, selections = [], [], []
    texts = ["La gimnasia es elegante.", "Hoy repasamos fallos.", "Afanasyeva sufrió una caída aparatosa.",
             "Douglas tropezó en la viga."]
    clock = 0.0
    for n, text in enumerate(texts):
        first = len(words)
        for w in text.split():
            words.append({"text": w, "start": clock, "end": clock + 0.6})
            clock += 0.6
        sid = f"s{n + 1:03d}"
        shots.append({"id": sid, "type": "broll", "startWord": first, "endWord": len(words) - 1,
                      "start": words[first]["start"], "end": words[-1]["end"], "text": text, "chapter": 0,
                      "broll": {"visualIntent": "gymnast falling", "queries": ["q1", "q2", "q3"], "queriesLocal": ["q"], "entities": [], "mustContain": [],
                                "avoid": [], "preferredShot": "wide", "event": None}})
        selections.append({"shotId": sid, "status": "selected", "decidedBy": "judge", "candidateId": f"yt:V{n}",
                           "source": "youtube", "kind": "video", "start": 10.0 + n, "end": 13.0 + n,
                           "url": f"https://youtu.be/V{n}", "title": "London 2012 team final" if n == 2 else f"clip {n}",
                           "channel": "Olympics", "license": "youtube-standard", "credit": "Fuente: Olympics"})
    (ctx.work_dir / "words.json").write_text(json.dumps({"words": words}))
    (ctx.work_dir / "shots.json").write_text(json.dumps({
        "slug": ctx.slug, "title": "Los Fallos De Gimnasia", "durationSeconds": clock, "context": "", "subject": "",
        "events": [], "chapters": [{"title": "X", "startWord": 0, "fromScript": False, "showTitle": False}], "shots": shots}))
    (ctx.work_dir / "selection.json").write_text(json.dumps({"slug": ctx.slug, "selections": selections, "stats": {}}))


def test_teaser_takes_the_clips_of_the_strongest_moments(tmp_path):
    ctx = _ctx(tmp_path, {"judge": {}})
    _story(ctx)
    with patch("pipeline.coldopen.complete_json", return_value={"shots": [{"shot": 2}, {"shot": 3}]}) as llm:
        picks = coldopen.pick_teaser(ctx, 2)
    assert "Los Fallos De Gimnasia" in llm.call_args.kwargs["system"]
    assert [(sel.candidateId, start) for sel, start in picks] == [("yt:V2", 12.0), ("yt:V3", 13.0)]
    (tmp_path / "out" / "_errores").mkdir(parents=True)                  # marked wrong in the studio: not in the teaser
    (tmp_path / "out" / "_errores" / "etiquetas.json").write_text(json.dumps({"Fallos/s003": {
        "verdict": "incorrecta", "reason": "roto", "candidateId": "yt:V2", "start": 12.0, "end": 15.0}}))
    with patch("pipeline.coldopen.complete_json", return_value={"shots": [{"shot": 2}, {"shot": 3}]}):
        picks = coldopen.pick_teaser(ctx, 2)
    assert picks[0][0].candidateId != "yt:V2" and "yt:V3" in [sel.candidateId for sel, _ in picks]
