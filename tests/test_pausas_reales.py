"""The pause cut only takes what is really silent and unheard: a sentence said that is not in guion.txt stays, and a
new upload keeps its own copy and clears what was made from the voice before it."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import align, web
from pipeline.context import RunContext
from tests.test_align import PauseTests, _build, _raw

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")


def voice(path: Path, parts: list[tuple[str, float]]) -> None:
    """An mp3 of tone («t») and silence («s») stretches, in order."""

    inputs, labels = [], []
    for n, (kind, seconds) in enumerate(parts):
        source = f"sine=f=440:d={seconds}" if kind == "t" else f"anullsrc=r=44100:cl=mono:d={seconds}"
        inputs += ["-f", "lavfi", "-t", str(seconds), "-i", source]
        labels.append(f"[{n}:a]")
    graph = "".join(labels) + f"concat=n={len(parts)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
                    "-ar", "44100", "-ac", "1", str(path)], check=True)


def _ctx(tmp_path, **align_cfg):
    ctx = RunContext.create("t", root=tmp_path, config={"align": {"min_match_ratio": 0.5, **align_cfg}})
    ctx.materials_dir.mkdir(parents=True, exist_ok=True)
    return ctx


@needs_ffmpeg
def test_a_sentence_said_that_is_not_in_the_script_is_never_cut(tmp_path):
    ctx = _ctx(tmp_path)
    # script words at 0-4.9 and 32-37; between them 10-20 s someone speaks words that are not in guion.txt
    voice(ctx.materials_dir / "voz.mp3", [("t", 5), ("s", 5), ("t", 10), ("s", 12), ("t", 5)])
    words = PauseTests()._words()
    heard = [{"word": "fuera", "start": 10.0 + i, "end": 10.8 + i} for i in range(10)]
    align._finish(ctx, words, heard=heard)
    saved = json.loads((ctx.work_dir / align.OUTPUT).read_text())
    seconds = align._seconds(ctx.materials_dir / "voz.mp3")
    # only the two silent stretches lost time (5 s → 1, 12 s → 1): the 10 s spoken in between stay whole
    assert seconds == pytest.approx(37 - 4 - 11, abs=0.4)
    assert saved["words"][10]["start"] == pytest.approx(32 - 15, abs=0.4)


@needs_ffmpeg
def test_what_whisper_heard_stays_even_when_quiet(tmp_path):
    ctx = _ctx(tmp_path)
    voice(ctx.materials_dir / "voz.mp3", [("t", 5), ("s", 27), ("t", 5)])          # quiet, but…
    heard = [{"word": "susurro", "start": 15.0, "end": 15.6}]                          # …Whisper heard a word
    align._finish(ctx, PauseTests()._words(), heard=heard)
    seconds = align._seconds(ctx.materials_dir / "voz.mp3")
    assert seconds < 37 - 15 and seconds > 37 - 26.1 + 0.5      # cut around the word, not through it


def test_without_knowing_where_the_silence_is_nothing_is_cut_and_it_is_not_redone(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    (ctx.materials_dir / "voz.mp3").write_bytes(b"not really audio")
    monkeypatch.setattr(align, "silent_spans", lambda audio, db, seconds: None)          # silencedetect failed
    align._finish(ctx, PauseTests()._words())
    assert not (ctx.materials_dir / "voz.original.mp3").exists()                         # the voice untouched
    monkeypatch.setattr(align, "_seconds", lambda path: 37.0)
    assert align.validate(ctx) is True                       # the pause it kept is known: no new alignment each run


@needs_ffmpeg
def test_how_much_of_a_pause_stays_is_an_option(tmp_path):
    ctx = _ctx(tmp_path, pause_keep_seconds=4)
    voice(ctx.materials_dir / "voz.mp3", [("t", 4.9), ("s", 27.1), ("t", 5)])
    align._finish(ctx, PauseTests()._words())
    saved = json.loads((ctx.work_dir / align.OUTPUT).read_text())
    assert saved["words"][10]["start"] - saved["words"][9]["end"] == pytest.approx(4.0, abs=0.05)


def test_each_upload_keeps_its_own_copy_and_clears_what_came_from_the_last(tmp_path):
    folder = tmp_path / "materiales" / "v1"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("hola")
    first, second = b"ID3" + b"a" * 20000, b"ID3" + b"b" * 20000
    web.save_voice(tmp_path, "v1", first)
    for derived in ("voz.sin-pausas.mp3", "voz.palabras.json", "voz.error.json", "voz.genaipro.json"):
        (folder / derived).write_text("de la voz anterior")
    (folder / "voz.original.mp3").write_bytes(first)
    web.save_voice(tmp_path, "v1", second)
    assert (folder / "voz.mp3").read_bytes() == second
    assert (folder / "voz.original.mp3").read_bytes() == second           # the copy is of the new one
    kept = sorted((folder / "voces-anteriores").iterdir())
    assert any(p.read_bytes() == first for p in kept)                     # the one before, kept apart
    for derived in ("voz.sin-pausas.mp3", "voz.palabras.json", "voz.error.json", "voz.genaipro.json"):
        assert not (folder / derived).exists(), derived
    for n in range(5):                                                    # only the last few are kept
        web.save_voice(tmp_path, "v1", b"ID3" + bytes([n]) * 20000)
    assert len([p for p in (folder / "voces-anteriores").iterdir() if p.suffix == ".mp3"]) <= 3
