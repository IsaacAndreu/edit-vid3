"""planner.cobertura (segunda tanda, points 1 and 3): a key event told by function — one search per function, the
judge told which, never two takes of the same function in a row, a reaction or testimony held as one shot."""

from types import SimpleNamespace

from pipeline import cobertura
from pipeline.schemas import Shot


def _shot(n, start, end, idea="i001", text="t"):
    return {"id": f"s{n:03d}", "type": "broll", "startWord": n * 10, "endWord": n * 10 + 9, "start": start, "end": end,
            "text": f"{text} {n}", "chapter": 0, "idea": {"id": idea, "kind": "ambiente", "summary": "gol"},
            "broll": {"visualIntent": "the goal", "queries": ["messi goal betis", "messi betis", "messi"], "queriesLocal": ["gol de messi"]}}


ANSWER = {"events": [{"id": "k1", "name": "gol de Messi al Betis", "ideas": ["i001"],
                      "functions": [{"role": "accion", "query": "Messi gol Betis Villamarín"},
                                    {"role": "reaccion", "query": "ovación afición Betis Messi"},
                                    {"role": "testimonio", "query": "Pellegrini rueda de prensa Messi"},
                                    {"role": "inventada", "query": "x"}]},
                     {"id": "zz", "functions": [{"role": "accion", "query": "q"}]}],
          "shots": [{"id": "s001", "event": "k1", "role": "accion"}, {"id": "s002", "event": "k1", "role": "accion"},
                    {"id": "s003", "event": "k1", "role": "reaccion", "sound": True},
                    {"id": "s004", "event": "k9", "role": "accion"}, {"id": "s005", "event": "k1", "role": "inventada"}]}


def test_functions_are_checked_balanced_and_lead_the_search():
    shots = [_shot(1, 0, 3), _shot(2, 3, 6), _shot(3, 6, 9), _shot(4, 9, 12), _shot(5, 12, 15)]
    counts = cobertura.assign(shots, ANSWER)
    assert counts == {"k1": 3} and "coverage" not in shots[3] and "coverage" not in shots[4]
    assert shots[2]["coverage"]["sound"] is True
    assert cobertura.balance(shots) == 1                       # s001 accion, s002 accion → s002 takes the reaction
    assert [s["coverage"]["role"] for s in shots[:3]] == ["accion", "reaccion", "accion"]
    cobertura.lead_with_function_query(shots)
    assert shots[1]["broll"]["queries"][0] == "ovación afición Betis Messi" and len(shots[1]["broll"]["queries"]) == 3


def test_a_reaction_holds_its_whole_idea_up_to_the_limit():
    shots = [_shot(1, 0, 2.5), _shot(2, 2.5, 5.0), _shot(3, 5.0, 7.5), _shot(4, 7.5, 10)]
    for s in shots[:3]:
        s["coverage"] = {"event": "k1", "name": "x", "role": "reaccion", "query": "q", "sound": False}
    shots[3]["coverage"] = {"event": "k1", "name": "x", "role": "accion", "query": "q", "sound": False}
    assert cobertura.hold(shots, max_seconds=6.0) == 1          # 0-5 s as one shot; a third would pass 6 s
    assert [(s["id"], s["start"], s["end"]) for s in shots] == [("s001", 0, 5.0), ("s003", 5.0, 7.5), ("s004", 7.5, 10)]
    assert shots[0]["text"] == "t 1 t 2" and shots[0]["endWord"] == 29


def test_apply_end_to_end_and_the_shot_schema():
    shots = [_shot(1, 0, 3), _shot(2, 3, 6), _shot(3, 6, 9)]
    ctx = SimpleNamespace(section=lambda name: {"max_third_party_seconds": 12} if name == "content" else {})
    got = cobertura.apply(ctx, shots, "header", ask=lambda text: ANSWER)
    assert got["events"] == 1 and got["shots"] == 3
    shot = Shot.model_validate(shots[0])
    assert shot.coverage.role == "accion" and shot.coverage.event == "k1"
    plain = Shot.model_validate({k: v for k, v in _shot(9, 0, 3).items()})
    assert "coverage" not in plain.model_dump()                # old shots hash as before (_late)


def test_the_judge_is_told_which_function():
    from pipeline.judge import shot_brief

    shots = [_shot(1, 0, 3)]
    cobertura.assign(shots, {**ANSWER, "shots": [{"id": "s001", "event": "k1", "role": "reaccion"}]})
    brief = shot_brief(Shot.model_validate(shots[0]))
    assert "REACTION" in brief and "gol de Messi al Betis" in brief and "not the play itself" in brief
