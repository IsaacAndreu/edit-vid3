"""The paper graphics (from the Messi reference): search engine, highlighter over newspaper, magnifying glass,
parchment, news item with the person, red-sun poster and the old map with pinned polaroids."""

from __future__ import annotations

from pathlib import Path

from pipeline import graphics, places
from pipeline.context import RunContext

TEXT = ("¿Messi es el mejor jugador de la historia? Muchos le llaman el mejor de todos los tiempos. Tiene 8 Balones "
        "de Oro. Nació en Rosario en 1987. El 18 de diciembre de 2022, Messi levanta la Copa del Mundo en Qatar: "
        "Argentina vence a Francia por penaltis en una final que muchos llaman la mejor de la historia. Talento, "
        "sacrificio y gloria. Para muchos, el GOAT. Lo contó el Diario Deportivo.")


def clean(kind, data):
    return graphics.clean(kind, data, TEXT, None, set())


def test_search_and_marker_only_with_the_scripts_words():
    assert clean("search", {"question": "¿Messi es el mejor jugador de la historia?"}) == {
        "type": "search", "question": "¿Messi es el mejor jugador de la historia?"}
    assert clean("search", {"question": "¿Cuánto cobra Messi en Miami cada temporada?"}) is None
    assert clean("marker", {"text": "«el mejor de todos los tiempos»"}) == {"type": "marker", "text": "el mejor de todos los tiempos"}
    assert clean("marker", {"text": "el futbolista más rico del planeta"}) is None


def test_the_lens_needs_a_figure_that_was_said():
    assert clean("lens", {"text": "8 Balones de Oro"}) == {"type": "lens", "text": "8 Balones de Oro"}
    assert clean("lens", {"text": "9 Balones de Oro"}) is None                 # not the figure in the script
    assert clean("lens", {"text": "Balones de Oro"}) is None                   # no figure: nothing to look at


def test_the_scroll_keeps_its_place_and_year_only_if_said():
    assert clean("scroll", {"title": "La leyenda de Rosario", "subtitle": "Rosario, 1987"}) == {
        "type": "scroll", "title": "La leyenda de Rosario", "subtitle": "Rosario, 1987"}
    assert clean("scroll", {"title": "La leyenda de Rosario", "subtitle": "Rosario, 1986"})["subtitle"] is None


def test_news_and_poster_name_a_person_of_the_script():
    news = clean("news", {"date": "18 dic 2022", "headline": "Messi levanta la Copa del Mundo en Qatar",
                          "body": "Argentina vence a Francia por penaltis en una final que muchos llaman la mejor de la historia.",
                          "outlet": "Diario Deportivo", "person": "Messi"})
    assert news["date"] == "18 dic 2022" and news["outlet"] == "Diario Deportivo" and news["person"] == "Messi"
    assert clean("news", {"date": "19 dic 2022", "headline": "Messi levanta la Copa del Mundo en Qatar", "outlet": "Marca"}) == {
        "type": "news", "date": None, "headline": "Messi levanta la Copa del Mundo en Qatar", "body": None, "outlet": None, "person": None}
    poster = clean("poster", {"person": "Messi", "words": ["Talento", "Sacrificio", "Humildad"], "big": "GOAT"})
    assert poster == {"type": "poster", "person": "Messi", "words": ["Talento", "Sacrificio"], "big": "GOAT"}
    assert clean("poster", {"person": "Cristiano", "words": ["Talento", "Sacrificio"]}) is None


def test_every_channel_may_use_the_paper_graphics_unless_it_says_no(tmp_path, monkeypatch):
    asked = {}

    def fake(ctx, **kwargs):
        asked["system"] = kwargs["system"]
        return {"graphics": []}

    monkeypatch.setattr(graphics, "complete_json", fake)
    (tmp_path / "config.yaml").write_text("graphics:\n  types: [map, chart]\n")
    ctx = RunContext.create("v", root=tmp_path)
    sents = [{"n": i, "start": i * 5.0, "end": i * 5.0 + 4.5, "text": "Frase."} for i in range(40)]
    graphics.plan(ctx, sents, 200.0)
    assert "Tipos permitidos en este canal: map, chart, search, marker, lens, scroll, news, poster." in asked["system"]
    (tmp_path / "config.yaml").write_text("graphics:\n  types: [map, chart]\n  extra_types: []\n")
    graphics.plan(RunContext.create("v", root=tmp_path), sents, 200.0)
    assert "Tipos permitidos en este canal: map, chart." in asked["system"]


def test_a_place_photo_is_fetched_once_and_cached(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    ctx = RunContext.create("v", root=tmp_path)
    calls = []

    class Response:
        def __init__(self, payload=None, content=b""):
            self.payload, self.content = payload, content

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class Session:
        def get(self, url, params=None, **_):
            calls.append(url)
            if params:
                return Response({"query": {"pages": {"1": {"thumbnail": {"source": "https://upload.example/barcelona.jpg"}}}}})
            return Response(content=b"jpeg")

    media = places.photo(ctx, "Barcelona, Spain", Session())
    assert media["src"].startswith("graphics/places/") and (ctx.work_dir / media["src"]).read_bytes() == b"jpeg"
    assert places.photo(ctx, "Barcelona, Spain", Session()) == media and len(calls) == 2      # from the cache
