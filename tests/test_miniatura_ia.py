"""Thumbnails by OpenAI's image model from reference thumbnails, adapted to our video (pipeline/miniatura_ia.py)."""

import base64
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from pipeline import miniatura_ia
from pipeline.context import RunContext


def _jpg(path, colour=(0, 0, 255), size=(640, 360)):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.full((size[1], size[0], 3), colour, np.uint8))
    return path


class FakeImages:
    def __init__(self, refuse_after=None):
        self.calls = []
        self.refuse_after = refuse_after

    def edit(self, **kwargs):
        self.calls.append({**kwargs, "names": [f.name for f in kwargs["image"]]})
        if self.refuse_after is not None and len(self.calls) > self.refuse_after:
            raise RuntimeError("moderation_blocked")
        ok, png = cv2.imencode(".png", np.full((1024, 1536, 3), (0, 200, 255), np.uint8))
        usage = SimpleNamespace(input_tokens=3000, output_tokens=1000,
                                input_tokens_details=SimpleNamespace(image_tokens=2800, text_tokens=200))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(png.tobytes()).decode())], usage=usage)


def _ctx(tmp_path, **miniaturas):
    ctx = RunContext.create("newgym5", root=tmp_path, config={"canal": "gimnasia", "align": {"language": "es"},
                                                              "miniaturas": {"ia_count": 2, **miniaturas}})
    _jpg(ctx.out_dir / "fotogramas" / "fotograma-1.jpg")
    _jpg(ctx.out_dir / "fotogramas" / "fotograma-2.jpg")
    _jpg(ctx.out_dir / "fotogramas" / "fotograma-3.jpg")
    cv2.imwrite(str(ctx.out_dir / "fotogramas" / "recorte.png"), np.zeros((300, 200, 4), np.uint8))
    ctx.materials_dir.mkdir(parents=True, exist_ok=True)
    (ctx.materials_dir / "guion.txt").write_text("Simone Biles.", encoding="utf-8")
    (ctx.materials_dir / "titulo.txt").write_text("La caída de Simone Biles", encoding="utf-8")
    return ctx


def test_references_then_our_frames_one_thumbnail_per_text(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    _jpg(tmp_path / "referencias" / "miniaturas" / "gimnasia" / "a.jpg")
    _jpg(ctx.materials_dir / "referencias-miniatura" / "b.png")
    monkeypatch.setattr(miniatura_ia, "youtube_thumbnail",
                        lambda ctx, vid: _jpg(ctx.cache_dir / "miniaturas" / f"{vid}.jpg"))
    monkeypatch.setattr(miniatura_ia, "texts", lambda ctx, given="": ["¿EL FIN?", "NADIE LO VIO"])
    fake = FakeImages()
    client = SimpleNamespace(images=fake)
    made = miniatura_ia.run(ctx, refs=["https://www.youtube.com/watch?v=aaaaaaaaaaa"], client=client)
    assert [p.name for p in made] == ["miniatura-ia-1.jpg", "miniatura-ia-2.jpg"]
    assert cv2.imread(str(made[0])).shape == (720, 1280, 3)
    first = fake.calls[0]
    # references first (the link, the video's folder, the channel's), then ours (2 best stills + the cutout)
    assert first["names"][:3] == [str(ctx.cache_dir / "miniaturas" / "aaaaaaaaaaa.jpg"),
                                  str(ctx.materials_dir / "referencias-miniatura" / "b.png"),
                                  str(tmp_path / "referencias" / "miniaturas" / "gimnasia" / "a.jpg")]
    assert [n.rsplit("/", 1)[-1] for n in first["names"][3:]] == ["fotograma-1.jpg", "fotograma-2.jpg", "recorte.png"]
    assert first["quality"] == "medium" and first["size"] == "1536x1024"
    assert "first 3 image(s) are REFERENCE" in first["prompt"] and "«¿EL FIN?»" in first["prompt"]
    assert "La caída de Simone Biles" in first["prompt"] and "Spanish" in first["prompt"]
    assert "«NADIE LO VIO»" in fake.calls[1]["prompt"]
    import json

    costs = json.loads((ctx.work_dir / "costs.json").read_text("utf-8"))["entries"]
    usd = (200 * 5.0 + 2800 * 10.0 + 1000 * 40.0) / 1e6
    assert [round(e["usd"], 4) for e in costs] == [round(usd, 4)] * 2


def test_without_references_it_says_where_to_put_them(tmp_path):
    ctx = _ctx(tmp_path)
    with pytest.raises(FileNotFoundError, match="referencias/miniaturas/gimnasia"):
        miniatura_ia.run(ctx, client=SimpleNamespace(images=FakeImages()))


def test_one_refused_does_not_lose_the_other(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ref = _jpg(tmp_path / "ref.jpg")
    monkeypatch.setattr(miniatura_ia, "texts", lambda ctx, given="": [given] if given else ["A", "B"])
    made = miniatura_ia.run(ctx, refs=[str(ref)], client=SimpleNamespace(images=FakeImages(refuse_after=1)))
    assert [p.name for p in made] == ["miniatura-ia-1.jpg"]
    made = miniatura_ia.run(ctx, refs=[str(ref)], text="MI TEXTO", count=1, client=SimpleNamespace(images=FakeImages()))
    assert len(made) == 1


def test_package_makes_none_unless_switched_on(tmp_path, monkeypatch):
    from pipeline import package

    ctx = _ctx(tmp_path)
    monkeypatch.setattr(miniatura_ia, "run", lambda ctx: (_ for _ in ()).throw(AssertionError("off by default")))
    assert package.ai_thumbnails(ctx) == []
    on = _ctx(tmp_path / "on", ia=True)
    monkeypatch.setattr(miniatura_ia, "run", lambda ctx: (_ for _ in ()).throw(FileNotFoundError("sin referencias")))
    assert package.ai_thumbnails(on) == []                       # never fails the video


def test_youtube_ids_from_links():
    assert miniatura_ia.video_id("https://youtu.be/abcdefghijk?t=3") == "abcdefghijk"
    assert miniatura_ia.video_id("abcdefghijk") == "abcdefghijk"
    assert miniatura_ia.video_id("ref.jpg") is None


def test_the_studio_button_runs_the_command_in_the_background(tmp_path, monkeypatch):
    from pipeline import web

    folder = tmp_path / "materiales" / "newgym5"
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="aún no está hecho"):
        web.ai_thumbnail(tmp_path, "newgym5", {})
    (tmp_path / "out" / "newgym5").mkdir(parents=True)
    (tmp_path / "out" / "newgym5" / "video-final.mp4").write_bytes(b"x")
    started = []
    monkeypatch.setattr(web, "background", lambda root, name, args: started.append((name, args)) or {"running": True})
    web.ai_thumbnail(tmp_path, "newgym5", {"refs": "https://youtu.be/aaaaaaaaaaa\nbbbbbbbbbbb, x y z", "text": " SU CAÍDA ",
                                           "count": 9})
    name, args = started[0]
    assert name == "miniatura-ia-newgym5"
    assert args == ["--miniatura-ia=newgym5", "--ref=aaaaaaaaaaa", "--ref=bbbbbbbbbbb",   # «x»: not a YouTube link
                    "--cuantas=4", "--texto=SU CAÍDA"]
    assert web.partner_may(tmp_path, ["gimnasia"], "POST", "/api/video/newgym5/miniatura-ia") is False   # not their channel
