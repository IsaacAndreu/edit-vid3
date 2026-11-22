"""objetivo-videos-referencia.md: any video measured with the figures of the references."""

import numpy as np

from pipeline import medir_video as mv

RNG = np.random.default_rng(1)


def _bg(colour=(20, 30, 90)):
    return np.full((90, 160, 3), colour, dtype=np.uint8)


def _footage(seed):
    return np.random.default_rng(seed).integers(0, 255, (90, 160, 3), dtype=np.uint8)


def _card():
    f = _bg()
    f[20:70, 35:125] = _footage(7)[20:70, 35:125]
    return f


def _text():
    f = _bg()
    f[40:48, 30:130] = 255                 # a line of big letters
    return f


def test_frames_are_told_apart():
    assert mv.classify(np.full((90, 160, 3), 3, dtype=np.uint8)) == "blank"
    assert mv.classify(_footage(1)) == "full"
    assert mv.classify(_card()) == "card"
    assert mv.classify(_text()) == "text"


def test_figures_from_frames_cuts_first_picture_text_and_cards():
    frames = [_text()] * 8 + [_footage(1)] * 8 + [_footage(2)] * 8 + [_card()] * 8   # 8 s at 4 frames a second
    m = mv.from_frames(frames)
    assert m["seconds"] == 8.0 and m["firstImage"] == 2.0
    assert m["textShare"] == 25.0 and m["cardShare"] == 25.0
    assert m["cutSeconds"] == 2.0                                                    # three cuts in 8 s


def test_our_video_is_measured_exactly_from_its_edit():
    def shot(start, frames, src=None, layout="full", kind="video"):
        media = {"src": src, "kind": kind, "layout": layout} if src else None
        return {"id": f"s{start}", "type": "broll", "from": start, "durationInFrames": frames, "media": media}

    timeline = {"fps": 30, "durationInFrames": 600, "groups": [{"kind": "datacard", "from": 0, "durationInFrames": 30}],
                "shots": [shot(0, 90), shot(90, 90, "a.mp4"), shot(180, 90, "a.mp4"), shot(270, 150, "p.jpg", "card", "image"),
                          shot(420, 180, "b.mp4")]}
    m = mv.from_timeline(timeline)
    assert m["firstImage"] == 3.0 and m["textShare"] == 15.0 and m["cardShare"] == 25.0
    assert m["cutSeconds"] == 5.0 and m["labelsPerMinute"] == 3.0                    # same clip twice: not a cut
    table = mv.table([("nuestro", m), ("ref", m)], {"cut_seconds": 3.1, "text_share": 0.0})
    assert "| Segundos por corte | 5.0 s | 5.0 s | 3.1 s |" in table


def test_a_channel_reference_is_read_from_its_cache_only(tmp_path):
    folder = tmp_path / mv.REFERENCES / "gimnasia"
    folder.mkdir(parents=True)
    (folder / "andrade.mp4").write_bytes(b"x")
    assert mv.channel_reference(tmp_path, "gimnasia") is None          # never measured in a page request
    (folder / "andrade.mp4.medidas.json").write_text('{"stamp": "1:1", "measures": {"cutSeconds": 3.1}}')
    assert mv.channel_reference(tmp_path, "gimnasia") == {"file": "andrade.mp4", "cutSeconds": 3.1}
