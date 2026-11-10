"""«Experimentos»: what each video tried, its 7-day views against its channel, and the verdicts."""

import pytest

from pipeline import experimentos


def _row(slug, channel, score, **tried):
    return {"slug": slug, "channel": channel, "score": score, "tried": tried, "tags": []}


def test_a_verdict_needs_three_videos_a_side_and_a_clear_gap():
    rows = [_row(f"a{i}", "patinaje", 1.5, Formato="caida-y-regreso") for i in range(3)] + \
           [_row(f"b{i}", "patinaje", 1.0, Formato="historia") for i in range(3)]
    [c] = experimentos.compare(rows)
    assert c["verdict"]["kind"] == "gana" and "caida-y-regreso" in c["verdict"]["text"]
    rows[0]["score"] = None                                   # only 2 with a result on one side
    assert experimentos.compare(rows)[0]["verdict"]["kind"] == "falta"
    rows = [_row(f"a{i}", "patinaje", 1.1, Formato="x") for i in range(3)] + [_row(f"b{i}", "patinaje", 1.0, Formato="y") for i in range(3)]
    assert experimentos.compare(rows)[0]["verdict"]["kind"] == "empate"


def test_a_label_is_compared_with_the_same_channels_videos_without_it():
    rows = [_row("a", "patinaje", 2.0), _row("b", "patinaje", 1.0), _row("c", "robots", 1.0)]
    rows[0]["tags"] = ["miniatura con cara"]
    [c] = experimentos.compare(rows)
    sides = {o["option"]: o["slugs"] for o in c["options"]}
    assert c["factor"] == "Etiqueta «miniatura con cara»" and sides == {"con": ["a"], "sin": ["b"]}


def test_notes_keep_labels_and_studio_numbers(tmp_path):
    assert experimentos.set_notes(tmp_path, "pati1", {"tags": "Miniatura con cara, , gancho pregunta", "ctr": "5,2"}) == \
        {"tags": ["miniatura con cara", "gancho pregunta"], "ctr": 5.2}
    assert experimentos.set_notes(tmp_path, "pati1", {"ctr": ""}) == {"tags": ["miniatura con cara", "gancho pregunta"]}
    with pytest.raises(ValueError):
        experimentos.set_notes(tmp_path, "pati1", {"retentionAvg": "140"})
