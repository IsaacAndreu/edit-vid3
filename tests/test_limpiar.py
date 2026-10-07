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
