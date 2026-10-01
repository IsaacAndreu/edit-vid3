"""Choosing among the LLM's candidate graphics: variety, spacing, best footage kept clear, reading time."""

from pipeline.graphics import choose, reading_seconds


def cand(kind, start, weak=0, strong=False):
    return {"start": start, "end": start + 6, "graphic": {"type": kind, "title": "x"}, "weak": weak, "strong": strong}


def test_variety_spacing_and_best_footage():
    candidates = [cand("chart", 30), cand("chart", 70), cand("map", 110, strong=True), cand("compare", 150),
                  cand("chart", 190), cand("replay", 230, strong=True), cand("timeline", 270, weak=2)]
    out = choose(candidates, 5, 300.0, {}, [])
    kinds = [o["graphic"]["type"] for o in sorted(out, key=lambda o: o["start"])]
    assert "map" not in kinds                                    # would cover the best footage
    assert "replay" in kinds and "timeline" in kinds             # shows that footage / covers weak footage
    assert all(a != b for a, b in zip(kinds, kinds[1:]))         # never the same kind twice in a row
    assert kinds.count("chart") <= 2
    starts = sorted(o["start"] for o in out)
    assert all(b - a >= 31 for a, b in zip(starts, starts[1:]))  # 6 s long + 25 s apart


def test_reading_time_grows_with_content():
    short = {"type": "kinetic", "lines": ["Nadie lo vio venir"]}
    long = {"type": "specs", "name": "Olga Korbut", "specs": [{"label": f"dato {i}", "value": str(i)} for i in range(6)]}
    assert reading_seconds(short) < 4 < reading_seconds(long)
