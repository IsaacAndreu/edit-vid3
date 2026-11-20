"""planner.ideas (bloque 1): consecutive shots grouped into ideas labelled literal / ambiente / rotulo; the model's
answer is checked, never trusted, and a title read aloud is never searched nor covered with footage."""

from __future__ import annotations

from types import SimpleNamespace

from pipeline import agrupar


def _shot(n: int, text: str, seconds: float = 3.0, **extra):
    return {"id": f"s{n:03d}", "start": (n - 1) * seconds, "end": n * seconds, "text": text,
            "broll": {"visualIntent": "x", **extra.pop("broll", {})}, **extra}


def test_the_models_ideas_are_kept_when_they_make_sense():
    shots = [_shot(1, "Simone Biles"), _shot(2, "tiene once medallas olímpicas,"), _shot(3, "siete de ellas de oro."),
             _shot(4, "SECRETO 4: SUS PADRES SON SUS ABUELOS")]
    answer = {"ideas": [{"shots": ["s001", "s002", "s003"], "kind": "ambiente", "mustShow": ["Simone Biles"],
                         "screenLine": "11 medallas olímpicas", "facts": ["11", "7 oros"]},
                        {"shots": ["s004"], "kind": "rotulo"}]}
    ideas = agrupar.assign(shots, answer)
    assert [i["shots"] for i in ideas] == [["s001", "s002", "s003"], ["s004"]]
    assert ideas[0]["kind"] == "ambiente" and ideas[0]["mustShow"] == ["Simone Biles"] and ideas[1]["kind"] == "rotulo"


def test_ideas_are_checked_chapters_length_gaps_and_leftovers():
    shots = [_shot(n, f"frase {n}") for n in range(1, 8)]
    shots[3]["chapterTitle"] = "SU INFANCIA"                       # s004 starts a chapter
    shots[6]["broll"]["moment"] = "falls off the beam"             # a narrated moment the model forgot
    answer = {"ideas": [{"shots": ["s001", "s002", "s003", "s004", "s005"], "kind": "literal"},   # across the chapter
                        {"shots": ["s006", "s009"], "kind": "ambiente"}]}                        # an unknown shot
    ideas = agrupar.assign(shots, answer)
    assert [i["shots"] for i in ideas] == [["s001", "s002", "s003"], ["s004", "s005"], ["s006"], ["s007"]]
    assert ideas[1]["kind"] == "literal"                           # the split part keeps the model's label
    assert ideas[3]["kind"] == "literal"                           # left out, with a moment: literal by rule
    long = [_shot(n, f"frase {n}", seconds=4.0) for n in range(1, 6)]
    split = agrupar.assign(long, {"ideas": [{"shots": [s["id"] for s in long], "kind": "ambiente"}]})
    assert [len(i["shots"]) for i in split] == [3, 2]              # 20 s is too long for one idea: ≤ 14 s each


def test_simple_rules_when_the_model_does_not_answer():
    assert agrupar.guess_kind({"text": "SECRETO 7: LE TIENE PÁNICO A LAS ABEJAS"}) == "rotulo"
    assert agrupar.guess_kind({"text": "Y si te ha gustado, suscríbete"}) == "rotulo"
    assert agrupar.guess_kind({"text": "Error número 3: comprar la casa demasiado pronto"}) == "rotulo"
    assert agrupar.guess_kind({"text": "con unos quince años dejó el instituto", "broll": {}}) == "ambiente"


def test_apply_numbers_ideas_over_the_whole_video_and_sets_each_shot():
    shots = [_shot(n, f"frase {n}") for n in range(1, 5)]
    ctx = SimpleNamespace(section=lambda name: {})
    asked = []

    def ask(text):
        asked.append(text)
        return {"ideas": [{"shots": ["s001", "s002"], "kind": "literal", "era": "Río 2016", "summary": "la final"}]}

    counts = agrupar.apply(ctx, shots, "TÍTULO: x", ask=ask)
    assert counts == {"literal": 1, "ambiente": 2, "rotulo": 0}
    assert shots[0]["idea"] == shots[1]["idea"] == {"id": "i001", "kind": "literal", "summary": "la final", "era": "Río 2016"}
    assert shots[2]["idea"]["id"] == "i002" and shots[3]["idea"]["id"] == "i003"
    assert "s001 (3.0 s): «frase 1»" in asked[0]


def test_a_title_read_aloud_is_not_searched_nor_covered_with_footage():
    from pipeline.schemas import Shot
    from pipeline.sourcing import needs_footage

    base = {"type": "broll", "startWord": 0, "endWord": 1, "start": 0, "end": 2, "text": "SECRETO 4", "chapter": 0,
            "broll": {"visualIntent": "a view", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}}
    rotulo = Shot.model_validate({**base, "id": "s001", "idea": {"id": "i001", "kind": "rotulo"}})
    plain = Shot.model_validate({**base, "id": "s002"})
    assert not needs_footage(rotulo) and needs_footage(plain)
    assert "idea" not in plain.model_dump()                        # old shots dump as before: nothing re-done

    from pipeline.schemas import TimelineShot
    from pipeline.timeline import fill_empty_shots

    media = {"src": "media/a.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: x"}
    shots = [TimelineShot.model_validate({"id": "s001", "type": "broll", "from": 0, "durationInFrames": 60, "text": "SECRETO 4"}),
             TimelineShot.model_validate({"id": "s002", "type": "broll", "from": 60, "durationInFrames": 60, "text": "x",
                                          "media": media})]
    fill_empty_shots(shots, [], 30, skip={"s001"})
    assert shots[0].media is None                                  # stays for the key-word board
    fill_empty_shots(shots, [], 30)
    assert shots[0].media is not None                              # without the idea: borrowed, as before
