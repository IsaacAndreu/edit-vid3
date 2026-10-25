"""The fallback's pool of the same story event (pipeline/fallback.event_pool): never a neighbour's footage of another
person this shot does not name, and the second searches of its siblings are shared."""

from __future__ import annotations

from types import SimpleNamespace

from pipeline import fallback
from pipeline.context import RunContext
from pipeline.schemas import Candidate, Option, Shot, ShotCandidates, ShotScores


def _shot(n: int, entities: list[str]) -> Shot:
    return Shot.model_validate({
        "id": f"s{n:03d}", "type": "broll", "startWord": n * 4, "endWord": n * 4 + 3, "start": n * 3.0, "end": n * 3.0 + 3,
        "text": "Frase.", "chapter": 0, "broll": {"visualIntent": "skating", "queriesEn": ["Mao Asada Sochi", "Asada free skate", "Sochi 2014"], "queriesEs": ["x"],
                                                   "entities": entities, "mustContain": [], "avoid": [], "preferredShot": "medium",
                                                   "event": "Mao Asada Sochi 2014 free skate"}})


def _write(ctx: RunContext, folder: str, shot_id: str, videos: list[tuple[str, str]]) -> None:
    cands = [Candidate.model_validate({"id": vid, "source": "youtube", "kind": "video", "url": "u", "title": title, "channel": "c",
                                       "license": "youtube-standard", "credit": "Fuente: c", "attribution": "c", "query": "q", "rankScore": 0.5,
                                       "storyboard": {"sheets": ["s.jpg"], "columns": 3, "rows": 3, "tileWidth": 320, "tileHeight": 180,
                                                      "interval": 2.0, "frames": 9}})
             for vid, title in videos]
    opts = [Option.model_validate({"candidateId": vid, "source": "youtube", "kind": "video", "pass": "fine", "start": 10.0, "end": 13.0,
                                   "scores": {"clip": 0.5}, "total": 0.5}) for vid, _ in videos]
    ctx.write_json(f"{folder}/candidates/{shot_id}.json", ShotCandidates(shotId=shot_id, specHash="h", queries={}, candidates=cands)
                   .model_dump(exclude_none=True))
    ctx.write_json(f"{folder}/scores/{shot_id}.json", ShotScores(shotId=shot_id, inputsHash="h", needed=3.0, prompts=[], options=opts)
                   .model_dump(exclude_none=True, by_alias=True))


def _ctx(tmp_path) -> RunContext:
    (tmp_path / "config.yaml").write_text("judge:\n  min_accept: 0.22\n")
    return RunContext.create("v", root=tmp_path)


def test_a_neighbours_footage_of_another_person_is_not_this_shots(tmp_path):
    ctx = _ctx(tmp_path)
    shots = [_shot(1, ["Mao Asada"]), _shot(2, ["Midori Ito", "Mao Asada"]), _shot(3, ["Mao Asada"])]
    story = SimpleNamespace(subject="Mao Asada · patinaje", shots=shots)
    _write(ctx, ".", "s003", [("yt:ito", "Midori Ito Albertville 1992 free skate"), ("yt:mao", "Asada Sochi 2014 FS"),
                              ("yt:both", "Midori Ito and Mao Asada triple axels")])
    options, _ = fallback.event_pool(ctx, story, shots[0])
    assert {o.candidateId for o in options} == {"yt:mao", "yt:both"}
    options, _ = fallback.event_pool(ctx, story, shots[1])                  # the shot that names Ito may use it
    assert "yt:ito" in {o.candidateId for o in options}


def test_a_siblings_second_search_serves_the_whole_event(tmp_path):
    ctx = _ctx(tmp_path)
    shots = [_shot(1, ["Mao Asada"]), _shot(2, ["Mao Asada"])]
    story = SimpleNamespace(subject="Mao Asada", shots=shots)
    _write(ctx, "research/s002", "s002", [("yt:new", "Mao Asada Sochi free skate full")])
    assert fallback.event_pool(ctx, story, shots[0])[0] == []
    assert [o.candidateId for o in fallback.event_pool(ctx, story, shots[0], research=True)[0]] == ["yt:new"]
