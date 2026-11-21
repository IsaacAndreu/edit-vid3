"""«Nuevo vídeo» desde un título: reference links read for the script, the sentences without an image rewritten."""

from pathlib import Path
from types import SimpleNamespace

from pipeline import imagen_guion, referencias


def _ctx(tmp_path):
    return SimpleNamespace(root=tmp_path, section=lambda name: {"language": "es"} if name == "align" else {})


def test_links_split_into_youtube_and_pages_capped():
    videos, pages = referencias.split_links("https://youtu.be/aBrmCgCuwno\nhttps://es.wikipedia.org/wiki/Simone_Biles\n"
                                            "https://www.youtube.com/watch?v=aBrmCgCuwno  https://x.com/a")
    assert videos == ["aBrmCgCuwno"] and pages == ["https://es.wikipedia.org/wiki/Simone_Biles", "https://x.com/a"]
    many = " ".join(f"https://example.com/{i}" for i in range(10))
    assert len(referencias.split_links(many)[1]) == referencias.MAX_LINKS


def test_a_page_keeps_its_sentences_not_its_menus():
    raw = ("<html><script>var x=1</script><nav>Inicio Contacto</nav><p>Simone Biles ganó cuatro oros en Río de Janeiro "
           "en 2016.</p><footer>Aviso legal y cookies del sitio</footer></html>")
    assert referencias.page_text(raw) == "Simone Biles ganó cuatro oros en Río de Janeiro en 2016."


def test_reading_subtitles_and_pages_once_cached(tmp_path):
    vtt = tmp_path / "subs.es.vtt"
    vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nSimone llegó a Houston con seis años\n", encoding="utf-8")
    asked = []
    youtube = SimpleNamespace(subtitle_file=lambda vid, lang: asked.append((vid, lang)) or vtt)
    pages = []
    get = lambda url: pages.append(url) or "<p>La excursión de la guardería fue al gimnasio Bannon's en 2003.</p>"
    links = "https://youtu.be/aBrmCgCuwno https://example.com/biles"
    text = referencias.read(_ctx(tmp_path), links, youtube=youtube, get=get)
    assert "Simone llegó a Houston con seis años" in text and "Bannon's" in text
    referencias.read(_ctx(tmp_path), links, youtube=youtube, get=get)
    assert len(asked) == 1 and len(pages) == 1                         # the second time from cache/referencias/
    assert referencias.read(_ctx(tmp_path), "") == ""


def test_the_draft_reads_the_info_and_the_references(tmp_path: Path, monkeypatch):
    from pipeline import organizar
    from tests.test_organizar import _site

    root = _site(tmp_path)
    seen = {}

    def fake(ctx, **kwargs):
        seen.update(kwargs)
        return {"title": "T", "script": "Frase del guion. " * 250}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    monkeypatch.setattr(referencias, "read", lambda ctx, links: "[Página x] Ganó en 2016 en Río.")
    organizar.draft_script(root, "negocios", {"title": "Booking", "info": "la multa de 2024",
                                              "references": "https://example.com/x"})
    assert "INFORMACIÓN DEL VÍDEO: la multa de 2024" in seen["user"]
    assert "MATERIAL DE REFERENCIA" in seen["user"] and "Ganó en 2016 en Río." in seen["user"]


def test_fix_rewrites_only_the_sentences_without_an_image_and_reads_again():
    script = "## Uno\nSimone ganó en Río.\nImagina que\nnadie la viera. Luego fue a París."
    rows = [{"n": 2, "text": "Imagina que nadie la viera.", "idea": "di dónde estaba"}]
    looks = []

    def review(ctx, text, title):
        looks.append(text)
        sin = 30 if "Imagina" in text else 0
        return {"shares": {"sin_imagen": sin}, "verdict": f"{sin} %", "sinImagen": rows if sin else []}

    answer = {"cambios": [{"n": 2, "nueva": "En el pabellón de Houston nadie la veía."}, {"n": 9, "nueva": "x"}]}
    r = imagen_guion.fix(None, script, "t", review_fn=review, ask=lambda user: answer)
    assert r["changed"] == 1 and "En el pabellón de Houston nadie la veía." in r["script"]
    assert "## Uno\nSimone ganó en Río." in r["script"] and r["script"].endswith("Luego fue a París.")
    assert r["before"]["shares"]["sin_imagen"] == 30 and r["after"]["shares"]["sin_imagen"] == 0
    nothing = imagen_guion.fix(None, "Todo bien.", review_fn=lambda *a: {"shares": {"sin_imagen": 0}, "verdict": "ok",
                                                                       "sinImagen": []}, ask=lambda u: 1 / 0)
    assert nothing["changed"] == 0


def test_the_video_keeps_its_reference_links(tmp_path):
    from pipeline import web
    from tests.test_organizar import _site

    root = _site(tmp_path)
    made = web.create_video(root, {"name": "refs1", "channel": "negocios", "script": "Frase del guion. " * 30,
                                   "references": "https://example.com/x"})
    folder = root / "materiales" / "negocios" / "refs1"
    assert (folder / "referencias.txt").read_text("utf-8").strip() == "https://example.com/x" and made
