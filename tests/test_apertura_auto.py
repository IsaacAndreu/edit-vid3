"""apertura.auto: a real moment with its own sound opens the video when no one chose one — once per video."""

import json

from pipeline import apertura


class Ctx:
    def __init__(self, tmp_path, cfg):
        self.cfg, self.materials_dir, self.work_dir = cfg, tmp_path / "materiales" / "pike", tmp_path / "work" / "pike"
        self.materials_dir.mkdir(parents=True)
        (self.materials_dir / "titulo.txt").write_text("Condenada a muerte con 18 años\n", "utf-8")
        (self.materials_dir / "guion.txt").write_text("Christa Pike escucha su condena…", "utf-8")

    def section(self, name):
        return self.cfg if name == "apertura" else {}


CANDIDATE = {"id": "abcdefghijk", "url": "https://www.youtube.com/watch?v=abcdefghijk", "title": "Sentencia",
             "channel": "WBIR", "start": 12.0, "end": 24.5, "why": "la jueza lee la sentencia", "speaker": "La jueza",
             "role": None, "lines": [{"from": 12.5, "to": 15.0, "original": "…", "text": "Será condenada a muerte"}]}


def test_the_opening_is_found_and_saved_once(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(apertura, "search", lambda ctx, **k: asked.append(k) or {"plan": {}, "candidates": [CANDIDATE]})
    ctx = Ctx(tmp_path, {"auto": True, "auto_ask": "la lectura de la sentencia"})
    data = apertura.auto(ctx, youtube=None)
    assert data["id"] == "abcdefghijk" and data["start"] == 12.0 and data["auto"] is True
    assert asked[0]["ask"] == "la lectura de la sentencia" and asked[0]["title"].startswith("Condenada")
    assert json.loads((ctx.materials_dir / apertura.FILE).read_text())["subtitles"]          # you see it in the studio
    assert apertura.auto(ctx, youtube=None) is None and len(asked) == 1                       # never twice


def test_nothing_without_the_setting_or_with_one_chosen_by_hand(tmp_path, monkeypatch):
    monkeypatch.setattr(apertura, "search", lambda ctx, **k: (_ for _ in ()).throw(AssertionError("no search")))
    assert apertura.auto(Ctx(tmp_path, {}), youtube=None) is None
    ctx = Ctx(tmp_path / "b", {"auto": True})
    (ctx.materials_dir / apertura.FILE).write_text(json.dumps({"id": "zzzzzzzzzzz", "url": "https://youtu.be/zzzzzzzzzzz"}))
    assert apertura.auto(ctx, youtube=None) is None


def test_no_moment_found_means_the_voice_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(apertura, "search", lambda ctx, **k: {"plan": {}, "candidates": []})
    ctx = Ctx(tmp_path, {"auto": True})
    assert apertura.auto(ctx, youtube=None) is None and not (ctx.materials_dir / apertura.FILE).is_file()
    assert json.loads((ctx.work_dir / apertura.AUTO_MARK).read_text())["found"] is False
