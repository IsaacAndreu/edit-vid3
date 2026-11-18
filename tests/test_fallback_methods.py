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
