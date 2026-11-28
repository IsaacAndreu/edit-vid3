"""A recorded voice put over a video that once had a synthetic one is never taken for the program's and deleted."""

from __future__ import annotations

import json
import os
import time

from pipeline import imagen_guion
from tests.test_arreglo_guion import ctx, fix  # noqa: F401  (fixture)


def _age(path, hours):
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


def test_a_recording_uploaded_after_a_synthetic_voice_is_kept(ctx):  # noqa: F811
    folder = ctx.materials_dir
    _age(folder / "voz.genaipro.json", 5)                   # the synthetic voice of five hours ago…
    (folder / "voz.mp3").write_bytes(b"my own recording")   # …and your recording, now (not via the studio)
    told = []
    assert imagen_guion.rescue(ctx, "40 % sin imagen", fix_fn=fix, send=told.append) == ""
    assert (folder / "voz.mp3").read_bytes() == b"my own recording"
    assert "Río" not in (folder / "guion.txt").read_text() and "tuya grabada" in told[0]


def test_a_remembered_synthetic_voice_counts_only_for_that_voice(ctx):  # noqa: F811
    folder = ctx.materials_dir
    gate = ctx.work_dir / imagen_guion.GATE_FILE
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(json.dumps({"synthetic": True, "voice": "otra voz de antes"}))
    (folder / "voz.genaipro.json").unlink()
    (folder / "voz.mp3").write_bytes(b"my own recording")
    told = []
    assert imagen_guion.rescue(ctx, "40 % sin imagen", fix_fn=fix, send=told.append) == ""
    assert (folder / "voz.mp3").read_bytes() == b"my own recording"


def test_a_synthetic_voice_whose_pauses_were_cut_is_still_synthetic(ctx):  # noqa: F811
    folder = ctx.materials_dir
    (folder / "voz.original.mp3").write_bytes(b"synthetic, as made")
    _age(folder / "voz.original.mp3", 2)                    # copied with its time by the pause cut
    _age(folder / "voz.genaipro.json", 2)
    (folder / "voz.mp3").write_bytes(b"synthetic, pauses cut")   # newer: the cut
    assert imagen_guion.is_synthetic(folder, {}) is True


def test_a_rewritten_script_leaves_no_copy_of_the_old_voice(ctx):  # noqa: F811
    folder = ctx.materials_dir
    (folder / "voz.original.mp3").write_bytes(b"the old synthetic voice")
    (folder / "voz.sin-pausas.mp3").write_bytes(b"half made")
    import pytest

    with pytest.raises(imagen_guion.ScriptRewritten):
        imagen_guion.rescue(ctx, "38 % sin imagen", fix_fn=fix,
                            ensure_voice=lambda c: (c.materials_dir / "voz.mp3").write_bytes(b"new"), send=lambda t: None)
    assert not (folder / "voz.original.mp3").exists() and not (folder / "voz.sin-pausas.mp3").exists()
