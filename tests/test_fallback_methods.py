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
