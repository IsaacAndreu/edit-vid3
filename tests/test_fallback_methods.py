"""«Que el clip sea…» 1: the protagonist's photo for a moment nobody filmed could never be saved — its method was
not in FallbackItem's Literal, the validation error was swallowed and the shot ended as a title card."""

import inspect
import re

from pipeline import fallback
from pipeline.schemas import FallbackItem


def test_every_method_fallback_uses_is_valid():
    used = set(re.findall(r'vet_and_materialise\([^)]*?"([a-z-]+)"', inspect.getsource(fallback), re.S))
    used |= set(re.findall(r'method="([a-z-]+)"', inspect.getsource(fallback)))
    allowed = set(FallbackItem.model_fields["method"].annotation.__args__)
    assert "protagonist-photo" in used
    assert used <= allowed, used - allowed


def test_a_protagonist_photo_item_validates():
    FallbackItem(shotId="s1", reason="r", method="protagonist-photo", kind="image", path="work/x/a.jpg",
                 source="wikimedia", candidateId="wm:1", credit="Fuente: Wikimedia", specHash="h")


def test_the_judges_other_accepted_options_are_kept_for_the_fallback():
    from pipeline.schemas import Selection

    s = Selection(shotId="s1", status="selected", decidedBy="judge", candidateId="yt:a", source="youtube", kind="video",
                  start=1.0, end=3.0, credit="Fuente: c", url="u", alternatives=[("yt:b", 10.0, 12.0)])
    again = Selection.model_validate(s.model_dump())
    assert again.alternatives == [("yt:b", 10.0, 12.0)]
    assert "alternatives" not in Selection(shotId="s1", status="fallback", decidedBy="fallback").model_dump()


def test_the_fallback_tries_the_judges_accepted_options_first():
    source = inspect.getsource(fallback)
    first = source.index("selections[shot_id].alternatives")
    assert first < source.index("ranked(scores.options", first)    # before reordering anything by CLIP
    assert source.index("1b. Protagonist first") > source.index("ranked(scores.options", first)
    assert "judge_pexels" in source and "judge_filler" in source


def test_the_same_seconds_of_a_source_are_never_on_screen_twice():
    """newgym3: protagonist-filler put 58-60 s of one training video in seven shots (0:07, 0:09, 0:10, 0:14, 0:41,
    6:53, 6:56) and «protagonist» one stretch three or four times in a row. Any overlap with what is on screen goes."""

    from types import SimpleNamespace

    from pipeline.fallback import same_stretch

    used = [SimpleNamespace(candidateId="yt:uXjKbxrlQyM", start=58.0, end=60.0)]
    assert same_stretch("yt:uXjKbxrlQyM", 58.4, 60.4, used)          # the newgym3 case
    assert same_stretch("yt:uXjKbxrlQyM", 60.5, 62.5, used)          # touching it (within a second)
    assert not same_stretch("yt:uXjKbxrlQyM", 64.0, 66.0, used)      # another moment of the same video: fine
    assert not same_stretch("yt:otro", 58.0, 60.0, used)              # another video
    assert not same_stretch("yt:uXjKbxrlQyM", None, None, used)       # a photo has no stretch
    assert same_stretch("yt:uXjKbxrlQyM", 56.0, None, used, needed=3.0)   # no end: as long as the shot needs


def test_an_ambient_shot_runs_on_with_its_neighbours_clip_after_a_jump():
    """Bloque 2.3: the shot next to it in the same idea took 40-43 s of a video: this one takes 44.5 s on (a 1.5 s
    jump: never one excerpt over 5 s with it); a neighbour of another idea is not used."""

    from types import SimpleNamespace

    from pipeline.fallback import JUMP, neighbour_option
    from pipeline.schemas import Candidate

    def shot(sid, idea):
        return SimpleNamespace(id=sid, idea=SimpleNamespace(id=idea, kind="ambiente"))

    story = [shot("s001", "i001"), shot("s002", "i001"), shot("s003", "i002")]
    used = [SimpleNamespace(shotId="s001", kind="video", candidateId="yt:A", start=40.0, end=43.0)]
    board = {"sheets": ["sb.jpg"], "columns": 10, "rows": 1, "tileWidth": 160, "tileHeight": 90, "interval": 10.0, "frames": 10}
    video = Candidate.model_validate({"id": "yt:A", "source": "youtube", "kind": "video", "url": "u", "title": "t",
                                      "channel": "c", "license": "l", "credit": "Fuente: c", "attribution": "a", "query": "q",
                                      "rankScore": 0.1, "durationSeconds": 100, "storyboard": board})
    options, found, continued = neighbour_option(story, story[1], used, 2.5, {"yt:A": video}.get)   # cap 5 s
    assert [(o.candidateId, o.start, o.end) for o in options] == [("yt:A", 43.0 + JUMP, 43.0 + JUMP + 2.5)] and "yt:A" in found
    assert continued is None
    # content.max_third_party_seconds 12: 3 + 2.5 s fit, so the idea runs on without a jump (one clip cut in two)
    options, _, continued = neighbour_option(story, story[1], used, 2.5, {"yt:A": video}.get, cap=12.0)
    assert [(o.start, o.end) for o in options] == [(43.0, 45.5)] and continued == "s001"
    assert neighbour_option(story, story[2], used, 2.5, {"yt:A": video}.get) == ([], {}, None)       # another idea
    assert neighbour_option(story, story[1], used, 2.5, {}.get) == ([], {}, None)                     # unknown source


def test_an_item_kept_from_an_earlier_run_counts_as_on_screen():
    """newgym3-ideas2: 5 pairs showed the same seconds of one source (s062/s128 both at 157.21 s of u2pccsI08v4) — one
    item kept from the earlier run, the other searched again beside it, because the kept one was never in `used`."""

    from pipeline.fallback import reused_selection, same_stretch

    kept = FallbackItem(shotId="s062", reason="r", method="protagonist", kind="video", path="work/x/s062.mp4",
                        source="youtube", candidateId="yt:u2pccsI08v4", start=157.21, end=160.177, durationSeconds=2.967,
                        credit="Fuente: Faith Productions", specHash="h")
    used = [reused_selection(kept)]
    assert used[0].status == "selected" and used[0].shotId == "s062"
    assert same_stretch("yt:u2pccsI08v4", 157.21, 160.343, used)       # s128: now refused
    assert not same_stretch("yt:u2pccsI08v4", 170.0, 173.0, used)

    source = inspect.getsource(fallback)
    reuse = source.index("items.append(old)")
    assert "used.append(reused_selection(old))" in source[reuse:reuse + 400]
    assert "same_stretch(old.candidateId" in source[reuse - 600:reuse]   # a kept item over a judge's pick goes too


def test_photo_before_another_clip_for_literal_ideas_and_for_ambient_only_when_asked():
    from types import SimpleNamespace as NS

    from pipeline.fallback import photo_first

    assert photo_first(NS(kind="literal"), {}) and not photo_first(NS(kind="literal"), {"literal_ambient": False})
    assert not photo_first(NS(kind="ambiente"), {}) and photo_first(NS(kind="ambiente"), {"ambient_photo_first": True})
    assert not photo_first(None, {"ambient_photo_first": True}) and not photo_first(NS(kind="rotulo"), {})


def test_burned_text_from_another_channel_keeps_a_fallback_clip_out():
    from pipeline.content_check import text_verdict

    assert text_verdict([0.02, 0.15, 0.20], "video", {}) == "texto ajeno en pantalla (20%)"   # a news ticker, 2 of 3
    assert text_verdict([0.02, 0.15, 0.01], "video", {}) == ""        # one frame of a passing title: it stays
    assert text_verdict([0.10], "image", {}) == "" and text_verdict([0.10], "video", {}) != ""
    assert text_verdict([0.30, 0.30, 0.30], "video", {"max_text_area": 0.5}) == ""


def test_a_photo_of_the_person_is_searched_for_the_ideas_time_first():
    from pipeline.fallback import photo_broll
    from pipeline.schemas import BrollSpec
    from pipeline.sourcing.images import web_queries

    broll = BrollSpec(visualIntent="una gimnasta", queries=["gimnasta salto", "gimnasta suelo", "gimnasta viga"], queriesLocal=["g h"], entities=["Otra"], event=None)
    queries = [q for q, _ in web_queries(photo_broll(broll, "Simone Biles", "adolescencia, 2011"))]
    assert queries == ["Simone Biles adolescencia, 2011", "Simone Biles"]
    assert [q for q, _ in web_queries(photo_broll(broll, "Simone Biles"))] == ["Simone Biles"]


def test_a_muted_talking_head_keeps_a_fallback_clip_out():
    from pipeline.content_check import head_verdict

    assert head_verdict([(0.09, 0.5), (0.08, 0.45), (0.0, 0.0)], {}).startswith("busto parlante")
    assert head_verdict([(0.09, 0.5), (0.01, 0.5), (0.0, 0.0)], {}) == ""     # a face passing by
    assert head_verdict([(0.09, 0.1), (0.09, 0.9), (0.09, 0.95)], {}) == ""   # big, but at the side: not to camera
    assert head_verdict([], {}) == ""
