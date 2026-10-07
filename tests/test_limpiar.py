"""python main.py --limpiar: the uploaded videos' heavy files go now."""

from __future__ import annotations

import json
import sys

import main


def test_limpiar_frees_uploaded_videos_only(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    for slug, up in (("subido", True), ("pendiente", False)):
        (tmp_path / "materiales" / slug).mkdir(parents=True)
        (tmp_path / "materiales" / slug / "guion.txt").write_text("Hola.", encoding="utf-8")
        out = tmp_path / "out" / slug
        out.mkdir(parents=True)
        (out / "video-final.mp4").write_bytes(b"x" * 1000)
        if up:
            (out / "publicado.json").write_text(json.dumps({"at": "2026-10-06T18:00:00", "url": ""}))
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "--limpiar"])
    main.main()
    assert not (tmp_path / "out" / "subido" / "video-final.mp4").exists()
    assert (tmp_path / "out" / "pendiente" / "video-final.mp4").is_file()


def test_whole_sources_go_and_the_folder_stays_under_its_cap(tmp_path):
    import os
    import time

    from pipeline import housekeeping
    from pipeline.context import RunContext

    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    ctx = RunContext.create("_x", root=tmp_path, config={"cleanup": {"videos_max_gb": 0.000002}})
    videos = tmp_path / "cache" / "videos"
    old = time.time() - 3 * 86400

    def put(rel, size, mtime=old):
        path = videos / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        os.utime(path, (mtime, mtime))
        return path

    whole = put("a/full_hd.mp4", 5000)
    fresh_whole = put("b/full_hd.mp4", 5000, time.time())
    sheet = put("a/sb/000.jpg", 10)
    clip = put("a/hd_1.000_3.000.mp4", 1000)
    analysis = put("c/win_1.000_3.000.mp4", 1000)
    scores = tmp_path / "work" / "v1" / "scores"
    scores.mkdir(parents=True)
    (scores / "s001.json").write_text(json.dumps({"options": [{"analysisPath": "cache/videos/c/win_1.000_3.000.mp4"}]}))
    housekeeping.trim_videos(ctx)
    assert not whole.exists() and fresh_whole.exists() and sheet.exists()
    assert not clip.exists() and analysis.exists()              # an unfinished video still needs its analysis
