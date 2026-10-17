"""The «caída y regreso» format: its settings, the quote card, the black-and-white low moments, the comeback news."""

from pathlib import Path

from pipeline import graphics, noticias, planner
from pipeline.context import RunContext
from pipeline.render import shot_filter

ROOT = Path(__file__).resolve().parents[1]


def test_the_format_brings_her_voice_and_the_low_moments(tmp_path):
    (tmp_path / "config.yaml").write_text("canal: null\n")
    video = tmp_path / "materiales" / "trusova"
    video.mkdir(parents=True)
    (video / "config.yaml").write_text("format: caida-y-regreso\n")
    ctx = RunContext.create("trusova", root=tmp_path)
    assert ctx.section("quotes")["count"] == 6 and "30 segundos" in ctx.section("quotes")["hint"]
    assert ctx.section("pacing")["low_moments"] is True
    assert "cita" in ctx.format["tipos"] and "CLÍMAX 2" in ctx.format["escritura"]


TEXT = 'Y entonces gritó delante de todos: "Odio este deporte, no volveré a salir al hielo nunca más", dijo Trusova.'


def test_a_quote_card_keeps_only_what_the_script_says():
    card = graphics.clean("cita", {"speaker": "Trusova", "text": "«Odio este deporte, no volveré a salir al hielo nunca más»",
                                   "highlight": ["nunca más", "medalla"]}, TEXT, None, set())
    assert card == {"type": "cita", "speaker": "Trusova", "text": "Odio este deporte, no volveré a salir al hielo nunca más",
                    "highlight": ["nunca más"]}
    assert graphics.clean("cita", {"speaker": "Trusova", "text": "Quiero ganar el oro en Milán sin falta"}, TEXT, None, set()) is None
    assert graphics.clean("cita", {"speaker": "Shcherbakova", "text": "Odio este deporte"}, TEXT, None, set()) is None


def test_low_moments_are_marked_only_when_the_format_asks(monkeypatch):
    from pipeline.schemas import Word

    words = [Word(index=i, text=t, start=i, end=i + 0.9, matched=True, sentenceEnd=t.endswith("."))
             for i, t in enumerate("Ganó. Luego lo perdió todo. Y volvió.".split())]
    asked = []
    monkeypatch.setattr(planner, "complete_json", lambda ctx, **k: asked.append(k) or {"low": [1, 7]})
    off = RunContext.create("x", root=ROOT, config={"pacing": {}})
    assert planner.low_moments(off, words) == set() and not asked
    on = RunContext.create("x", root=ROOT, config={"pacing": {"low_moments": True}})
    assert planner.low_moments(on, words) == {1}


def test_a_low_shot_is_black_and_white_in_the_fast_render_too():
    assert "hue=s=0" in shot_filter({"mono": True}, 60, 30)
    assert "hue=s=0" not in shot_filter({}, 60, 30)


def test_a_comeback_in_the_news_is_the_second_climax_of_a_caida_y_regreso():
    story = {"name": "Trusova", "videos": [{"title": "Trusova vuelve y gana tras ser madre", "channel": "Sport", "ageHours": 5,
                                            "description": "Denis Ten Memorial"}]}
    assert noticias.idea_for(story, "patinaje")["format"] == "caida-y-regreso"
    assert noticias.idea_for(story, "general")["format"] == "caso-real"
    assert noticias.idea_for({**story, "videos": [{**story["videos"][0], "title": "Trusova gana en Almaty"}]},
                             "patinaje")["format"] == "caso-real"


def test_the_spend_page_estimates_what_the_metadata_proxy_cost_each_video(tmp_path):
    import json

    from pipeline import gasto

    (tmp_path / "config.yaml").write_text("sourcing:\n  youtube:\n    metadata_proxy_mb_per_request: 0.5\n"
                                          "    metadata_proxy_usd_per_gb: 4\n")
    log = tmp_path / "work" / "pati1" / "youtube_downloads.jsonl"
    log.parent.mkdir(parents=True)
    rows = [{"ts": 100 + i, "action": "metadata", "proxy": "metadatos"} for i in range(1024)] + [{"ts": 50, "action": "metadata"}]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    usage, rates = gasto.proxy_usage(tmp_path)
    assert usage == {"pati1": {"requests": 1024, "mb": 512.0, "usd": 2.0, "since": 100}}
    assert rates == {"mbPerRequest": 0.5, "usdPerGb": 4.0}
