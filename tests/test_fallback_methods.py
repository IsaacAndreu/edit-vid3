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
