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
    assert ideas[1]["kind"] == "ambiente"                          # the split part: no narrated moment, not literal
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
    shots[0]["broll"]["moment"] = "jumps off the podium"           # a narrated action: literal stays literal
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
    # the donor is not the shot right next to it (that file is never lent to its neighbour: 27-11)
    shots = [TimelineShot.model_validate({"id": "s001", "type": "broll", "from": 0, "durationInFrames": 60, "text": "SECRETO 4"}),
             TimelineShot.model_validate({"id": "s002", "type": "broll", "from": 60, "durationInFrames": 60, "text": "x",
                                          "media": {**media, "src": "media/b.mp4"}}),
             TimelineShot.model_validate({"id": "s003", "type": "broll", "from": 120, "durationInFrames": 60, "text": "x",
                                          "media": media})]
    fill_empty_shots(shots, [], 30, skip={"s001"})
    assert shots[0].media is None                                  # stays for the key-word board
    fill_empty_shots(shots, [], 30)
    assert shots[0].media is not None                              # without the idea: borrowed, as before


def _idea_shot(kind, **idea):
    from pipeline.schemas import Shot

    return Shot.model_validate({"id": "s001", "type": "broll", "startWord": 0, "endWord": 1, "start": 0, "end": 2,
                                "text": "las abejas", "chapter": 0,
                                "broll": {"visualIntent": "a bee", "queries": ["a", "b", "c"], "queriesLocal": ["d"]},
                                "idea": {"id": "i001", "kind": kind, **idea}})


def test_the_judge_reads_the_label_who_must_and_must_not_be_seen_and_the_time():
    from pipeline.judge import shot_brief

    literal = shot_brief(_idea_shot("literal", mustShow=["Simone Biles"], mustNotShow=["Jordan Chiles"], era="Río 2016"))
    assert "LITERAL" in literal and "Must be on screen: Simone Biles" in literal
    assert "Must NOT be on screen (reject if clearly shown): Jordan Chiles" in literal and "Río 2016" in literal
    assert "AMBIENT" in shot_brief(_idea_shot("ambiente"))


def test_ideas_group_the_search_and_the_master_video():
    from pipeline.judge import _event_key
    from pipeline.sourcing.scenes import group_ideas

    a, b = _idea_shot("literal"), _idea_shot("literal").model_copy(update={"id": "s002"})
    c = _idea_shot("ambiente").model_copy(update={"id": "s003"})
    c = c.model_copy(update={"idea": c.idea.model_copy(update={"id": "i002"})})
    assert [[s.id for s in scene] for scene in group_ideas([a, b, c])] == [["s001", "s002"], ["s003"]]
    assert _event_key(a) == _event_key(b) == "idea:i001" != _event_key(c)


def test_a_stronger_model_only_for_literal_ideas(tmp_path, monkeypatch):
    import numpy as np

    from pipeline import judge
    from pipeline.context import RunContext

    (tmp_path / "config.yaml").write_text("judge: {model: barato, model_literal: fuerte}\n")
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path)
    used = []
    monkeypatch.setattr(judge, "cached_json", lambda path, produce: used.append(path) or {"ranking": ["A"], "reason": ""})
    sheet = np.zeros((10, 10, 3), np.uint8)
    judge.call_judge(ctx, _idea_shot("literal"), sheet, "A")
    judge.call_judge(ctx, _idea_shot("ambiente"), sheet, "A")
    assert used[0] != used[1]                                       # another model, another cache entry
    ctx.config["judge"]["model_literal"] = None
    judge.call_judge(ctx, _idea_shot("literal"), sheet, "A")
    assert used[2] != used[0]


def test_an_ideas_line_and_its_fact_go_on_screen(tmp_path):
    """Bloque 2.1-2.2: the planner's line for an ambient idea over its first seconds, the key word marked; never over
    another graphic; the idea's first fact as a label on its first shot."""

    import json

    from pipeline.context import RunContext
    from pipeline.schemas import ShotsFile, TimelineGroup, TimelineShot
    from pipeline.timeline import fact_kind, idea_lines, place_labels

    assert [fact_kind(f) for f in ("Guarulhos", "Río 2016", "14.166", "19 años")] == ["place", "date", "score", "score"]
    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={})
    broll = {"visualIntent": "a view", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}
    planned = []
    for n in range(4):
        idea = {"id": "i001", "kind": "ambiente", "screenLine": "*11* medallas olímpicas", "facts": ["Río 2016"]} if n < 2 \
            else {"id": "i002", "kind": "literal", "screenLine": "la caída"}
        planned.append({"id": f"s00{n + 1}", "type": "broll", "startWord": n, "endWord": n, "start": 3.0 * n,
                        "end": 3.0 * n + 3, "text": f"frase {n}", "chapter": 0, "broll": broll, "idea": idea})
    ctx.write_json("shots.json", {"slug": "v", "title": "t", "durationSeconds": 12, "chapters": [{"title": "c", "startWord": 0, "fromScript": False, "showTitle": False}],
                                  "shots": planned})
    media = {"src": "m.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: x"}
    shots = [TimelineShot.model_validate({"id": f"s00{n + 1}", "type": "broll", "from": 90 * n, "durationInFrames": 90,
                                          "text": "x", "media": media}) for n in range(4)]
    lines = idea_lines(ctx, shots, [], 30)
    assert [(g.from_, g.graphic["lines"]) for g in lines] == [(4, ["*11* medallas olímpicas"])]   # literal: not by default
    ctx.config.setdefault("timeline", {})["idea_lines"] = "siempre"
    assert len(idea_lines(ctx, shots, [], 30)) == 1                  # the literal one is too close (12 s apart at most)
    busy = TimelineGroup.model_validate({"id": "g", "kind": "graphic", "from": 0, "durationInFrames": 60,
                                         "graphic": {"type": "kinetic", "lines": ["x"]}})
    ctx.config["timeline"]["idea_lines"] = "ambiente"
    assert idea_lines(ctx, shots, [busy], 30) == []                   # never over another graphic
    ctx.config["timeline"]["idea_lines"] = "no"
    assert idea_lines(ctx, shots, [], 30) == []
    labels = place_labels(ShotsFile.model_validate(json.loads((ctx.work_dir / "shots.json").read_text())), shots, [], 30, {})
    assert [(l.kind, l.text) for l in labels] == [("date", "Río 2016")]


def test_a_concept_search_only_for_ambient_ideas():
    """Bloque 2.4: faceless concept stock («hands cleaning with rubber gloves») is written only for ambient ideas."""

    shots = [_shot(1, "Su madre limpiaba casas"), _shot(2, "Se cayó en Tokio")]
    ideas = agrupar.assign(shots, {"ideas": [
        {"shots": ["s001"], "kind": "ambiente", "concept": "hands cleaning with rubber gloves"},
        {"shots": ["s002"], "kind": "literal", "concept": "a fall"}]})
    assert ideas[0]["concept"] == "hands cleaning with rubber gloves" and ideas[1]["concept"] is None


def test_literal_only_where_an_action_must_be_seen():
    """newgym3-ideas: the model called 120 of 229 shots literal and 92 ended as text. An idea is literal only where
    the planner heard an action that must be seen (broll.moment); talking about a competition or a title is ambient."""

    shots = [_shot(1, "tiene seis títulos mundiales"), _shot(2, "bajó del podio de un salto", broll={"moment": "jumps off"})]
    ideas = agrupar.assign(shots, {"ideas": [{"shots": ["s001"], "kind": "literal"}, {"shots": ["s002"], "kind": "literal"}]})
    assert [i["kind"] for i in ideas] == ["ambiente", "literal"]


def test_more_labels_per_idea_and_its_quote_as_a_card_when_asked(tmp_path):
    import json

    from pipeline.context import RunContext
    from pipeline.schemas import ShotsFile, TimelineShot
    from pipeline.timeline import idea_quotes, place_labels

    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={})
    broll = {"visualIntent": "a view", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}
    idea = {"id": "i001", "kind": "ambiente", "facts": ["Río 2016", "14.166"], "mustShow": ["Simone Biles"]}
    texts = ["Aquel día en Río Biles lo dijo claro:", "«Ya no disfruto de este deporte, solo quiero acabar», confesó.",
             "Y nadie la creyó."]
    planned = [{"id": f"s00{n + 1}", "type": "broll", "startWord": n, "endWord": n, "start": 4.0 * n, "end": 4.0 * n + 4,
                "text": t, "chapter": 0, "broll": broll, "idea": idea} for n, t in enumerate(texts)]
    ctx.write_json("shots.json", {"slug": "v", "title": "t", "durationSeconds": 12, "chapters": [
        {"title": "c", "startWord": 0, "fromScript": False, "showTitle": False}], "shots": planned})
    media = {"src": "m.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: x"}
    shots = [TimelineShot.model_validate({"id": f"s00{n + 1}", "type": "broll", "from": 120 * n, "durationInFrames": 120,
                                          "text": "x", "media": media}) for n in range(3)]
    shots_file = ShotsFile.model_validate(json.loads((ctx.work_dir / "shots.json").read_text()))
    assert [l.text for l in place_labels(shots_file, shots, [], 30, {})] == ["Río 2016"]
    assert [l.text for l in place_labels(shots_file, shots, [], 30, {"idea_facts_max": 2})] == ["Río 2016", "14.166"]
    assert idea_quotes(ctx, shots, [], 30) == []                                   # off by default
    ctx.config["timeline"] = {"idea_quotes": True}
    cards = idea_quotes(ctx, shots, [], 30, lambda name: {"src": f"{name}.png"})
    assert len(cards) == 1 and cards[0].from_ == 122
    assert cards[0].graphic["text"] == "Ya no disfruto de este deporte, solo quiero acabar"
    assert cards[0].graphic["speaker"] == "Simone Biles"
