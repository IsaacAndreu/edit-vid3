"""fallback.protagonist_first (off): the protagonist's clip and photo, both judged (the judge sees the idea's time),
before anonymous stock. Off: the order and the judge as always. Checked on the code's order: running the whole
fallback stage with doubles would test the doubles."""

from __future__ import annotations

import inspect

from pipeline import fallback


def test_with_the_option_the_protagonist_comes_before_the_stock_and_is_judged():
    source = inspect.getsource(fallback)
    first = source.index('if item is None and cfg.get("protagonist_first", False):')
    stock = source.index("# 2. Pexels (video, then photo), picked by CLIP")
    usual = source.index('if item is None and not cfg.get("protagonist_first", False):')
    assert first < stock < usual                                          # on: before the stock; off: after it
    assert "protagonist_steps(item, judged=True)" in source[first:stock]
    assert "protagonist_steps(item, judged=False)" in source[usual:usual + 200]
    steps = source[source.index("def protagonist_steps("):first]
    assert 'vet=judged)' in steps                                          # the photo: judged when asked
    assert "vet=judged or literal" in steps                                # the filler too


def test_off_by_default():
    from pathlib import Path

    import yaml

    cfg = yaml.safe_load(Path("config.yaml").read_text())
    assert not (cfg.get("fallback") or {}).get("protagonist_first", False)
