"""Fase 1.1-1.2: clips that are never truncated under their final name, and shared JSON state under a file lock."""

from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import time
from pathlib import Path

import pytest

from pipeline import fileio
from pipeline.sourcing.youtube import YouTubeSource


def _clip(path: Path, seconds: float = 2.0) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=10:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_a_whole_clip_passes_and_a_truncated_one_does_not(tmp_path):
    good = _clip(tmp_path / "good.mp4", 2.0)
    assert fileio.media_problem(good, seconds=2.0) is None
    cut = tmp_path / "cut.mp4"
    cut.write_bytes(good.read_bytes()[: good.stat().st_size // 3])        # an ffmpeg killed half way
    assert fileio.media_problem(cut, seconds=2.0) is not None
    (tmp_path / "empty.mp4").write_bytes(b"")
    assert fileio.media_problem(tmp_path / "empty.mp4") == "vacío"
    assert "dura" in fileio.media_problem(good, seconds=10.0)


def test_publish_renames_only_a_good_clip(tmp_path):
    part = _clip(tmp_path / ".part1-2-hd_0.000_2.000.mp4", 2.0)
    fileio.publish(part, tmp_path / "hd_0.000_2.000.mp4", seconds=2.0)
    assert (tmp_path / "hd_0.000_2.000.mp4").is_file() and not part.exists()
    bad = tmp_path / ".part1-2-hd_5.000_7.000.mp4"
    bad.write_bytes(b"garbage")
    with pytest.raises(RuntimeError, match="incompleto"):
        fileio.publish(bad, tmp_path / "hd_5.000_7.000.mp4", seconds=2.0)
    assert not bad.exists() and not (tmp_path / "hd_5.000_7.000.mp4").exists()


def test_the_library_drops_a_truncated_legacy_range_and_ignores_parts(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    folder = tmp_path / "videos" / "vid00000000"
    folder.mkdir(parents=True)
    good = _clip(folder / "hd_10.000_12.000.mp4", 2.0)
    broken = folder / "hd_20.000_22.000.mp4"
    broken.write_bytes(good.read_bytes()[:200])                  # left by a restart before the atomic writes
    _clip(folder / f".part{os.getpid()}-1-hd_30.000_32.000.mp4", 2.0)     # being written right now
    assert yt._library_range(folder, "hd", ".mp4", 10.5, 11.5, None) == good
    assert yt._range_sidecar(good)["checked"] is True               # checked once, not again
    assert yt._library_range(folder, "hd", ".mp4", 20.5, 21.5, None) is None
    assert not broken.exists()
    assert yt._library_range(folder, "hd", ".mp4", 30.5, 31.5, None) is None
    yt.close()


def test_leftovers_of_dead_processes_are_cleaned_at_start(tmp_path):
    folder = tmp_path / "videos" / "vid00000000"
    folder.mkdir(parents=True)
    dead = folder / ".part999999-1-hd_0.000_2.000.mp4"
    dead.write_bytes(b"x")
    mine = folder / f".part{os.getpid()}-1-hd_0.000_2.000.mp4"
    mine.write_bytes(b"x")
    old = folder / "wip_hd.f137.mp4"
    old.write_bytes(b"x")
    os.utime(old, (time.time() - 7 * 3600,) * 2)
    from pipeline.sourcing import youtube

    youtube._CLEANED.discard(str(tmp_path / "videos"))
    youtube._clean_leftovers(tmp_path / "videos")
    assert not dead.exists() and mine.exists() and not old.exists()


def _add(path: str, n: int) -> None:
    for i in range(n):
        fileio.update_json(Path(path), lambda d: {**d, f"{os.getpid()}-{i}": i}, {})


def test_update_json_loses_nothing_between_processes(tmp_path):
    path = tmp_path / "rechazados.json"
    procs = [multiprocessing.get_context("fork").Process(target=_add, args=(str(path), 40)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    assert len(json.loads(path.read_text())) == 160


def test_a_corrupt_state_file_is_kept_aside_not_taken_for_empty_in_silence(tmp_path, capsys):
    path = tmp_path / ".rechazados.json"
    path.write_text('{"abc": [1, "bot"')
    assert fileio.read_json(path, {}) == {}
    aside = list(tmp_path.glob(".rechazados.json.corrupto-*"))
    assert aside and aside[0].read_text() == '{"abc": [1, "bot"'
    assert "roto" in capsys.readouterr().out


def test_refusals_of_another_process_are_seen_and_none_is_lost(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    one = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    two = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    assert not one.refused("aaaaaaaaaaa")                    # cached empty in `one`
    two._refuse("aaaaaaaaaaa", "vpn")
    os.utime(two._refused_path(), ns=(time.time_ns() + 10**9,) * 2)   # a later mtime, as another process would leave
    assert one.refused_why("aaaaaaaaaaa") == "vpn"            # reloaded by mtime
    one._refuse("bbbbbbbbbbb", "sin-hls")
    assert set(json.loads(one._refused_path().read_text())) == {"aaaaaaaaaaa", "bbbbbbbbbbb"}   # not overwritten
    one.close()
    two.close()


def test_a_quarantine_is_never_shortened_by_another_process(tmp_path, monkeypatch):
    from pipeline.sourcing.youtube import quarantined_until

    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never",
                                                                  "bot_quarantine_minutes": 10})
    far = time.time() + 5 * 3600
    path = tmp_path / "videos"
    path.mkdir(parents=True, exist_ok=True)
    from pipeline.sourcing.youtube import quarantine_file

    quarantine_file(tmp_path, "").write_text(f"{far:.0f}")
    yt._quarantine(0)
    assert quarantined_until(tmp_path, "") >= far - 1
    yt.close()


def test_whole_downloads_carry_a_deadline_and_crawl_detection(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    unknown = yt._whole_deadline(0)
    assert unknown["throttledratelimit"] == 100 * 1024 and unknown["fragment_retries"] == 5
    assert "progress_hooks" not in unknown
    options = yt._whole_deadline(20e6)
    hook = options["progress_hooks"][0]
    hook({"status": "downloading"})                     # in time: nothing
    clock = time.monotonic() + 10_000
    monkeypatch.setattr(time, "monotonic", lambda: clock)
    with pytest.raises(RuntimeError, match="se corta"):
        hook({"status": "downloading"})
    yt.close()
