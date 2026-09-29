from pipeline import graphics, planner, timeline
from pipeline.config import PROJECT_ROOT
from pipeline.context import RunContext
from pipeline.render import graphic_media

TEXT = ("En París sacó un 6,6 de dificultad y un 8,766 de ejecución, con 0,3 de penalización: 15,066. "
        "El Philippine Star tituló que Yulo hacía historia con dos oros. "
        "El Código de Puntuación prohíbe desde 1977 cualquier elemento que empiece de pie sobre la barra alta. "
        "Uchimura en Tokio y Yulo en París: dos maneras de ganar.")


def test_score_parts_must_add_up():
    data = {"name": "Yulo", "d": "6,6", "e": "8,766", "penalty": "0,3", "total": "15,066"}
    ok = graphics.clean("score", data, TEXT, None, set())
    assert ok["total"] == 15.066 and ok["penalty"] == 0.3 and ok["labels"]["d"] == "DIFICULTAD"
    assert graphics.clean("score", {**data, "total": "15,366"}, TEXT, None, set()) is None     # never said
    assert graphics.clean("score", {**data, "e": "8,4"}, TEXT, None, set()) is None             # invented part


def test_press_keeps_said_headlines_and_named_outlets():
    out = graphics.clean("press", {"items": [
        {"outlet": "Philippine Star", "headline": "Yulo hace historia con dos oros", "highlight": "dos oros", "date": "2024"},
        {"outlet": "The Guardian", "headline": "Escándalo mundial en la federación asiática", "highlight": "x"}]}, TEXT, None, set())
    assert out["items"] == [{"outlet": "Philippine Star", "headline": "Yulo hace historia con dos oros",
                             "date": None, "highlight": "dos oros"}]


def test_rule_and_stamp():
    out = graphics.clean("rule", {"source": "Código de Puntuación", "article": "Art. 13.4", "stamp": True,
                                  "text": "Prohíbe cualquier elemento que empiece de pie sobre la barra alta",
                                  "highlight": "de pie sobre la barra alta"}, TEXT, None, set())
    assert out["stamp"] == "PROHIBIDO" and out["article"] is None and out["source"] == "Código de Puntuación"
    generic = graphics.clean("rule", {"source": "Reglas FIFA", "text": "cualquier elemento sobre la barra alta"}, TEXT, None, set())
    assert generic["source"] == "REGLAMENTO" and generic["stamp"] is None


def test_split_needs_both_names_said():
    assert graphics.clean("split", {"left": {"name": "Uchimura"}, "right": {"name": "Yulo"}}, TEXT, None, set())
    assert graphics.clean("split", {"left": {"name": "Uchimura"}, "right": {"name": "Biles"}}, TEXT, None, set()) is None


SENTS = [{"n": i, "start": i * 7.0, "end": i * 7.0 + 6.5, "text": t} for i, t in enumerate([
    "Hay movimientos que la gimnasia prohibió.",
    "El número tres es el mortal Korbut.",
    "Olga Korbut lo hizo en Múnich y en 1977 se prohibió por peligroso.",
    "Otro caso fue el salto Produnova.",
    "Muchos lo llaman el salto de la muerte.",
])]


def test_banned_cards(tmp_path, monkeypatch):
    items = [{"sentence": 1, "name": "mortal Korbut", "who": "Olga Korbut", "year": "1977", "number": 3,
              "reason": "por peligroso"},
             {"sentence": 3, "name": "salto Produnova", "who": "Yelena Produnova", "year": "2020"}]
    monkeypatch.setattr(graphics, "complete_json", lambda *a, **k: {"items": items})
    ctx = RunContext.create("x", root=tmp_path, config={"format": "prohibidos"})
    out = graphics.banned(ctx, SENTS)
    first, second = out[0]["graphic"], out[1]["graphic"]
    assert first == {"type": "banned", "name": "mortal Korbut", "number": 3, "who": "Olga Korbut",
                     "reason": "por peligroso", "stamp": "PROHIBIDO", "since": "DESDE 1977"}
    assert second["who"] is None and second["since"] is None          # neither is said around it


def test_banned_outline_and_cues():
    ctx = RunContext.create("_t", root=PROJECT_ROOT, config={"format": "prohibidos"})
    assert "PROHIBIDAS" in planner.outline_system(ctx)
    assert timeline.graphic_cues({"type": "banned"}, 150) == [("impact", timeline.BANNED_STAMP)]
    assert timeline.graphic_cues({"type": "rule", "stamp": None}, 150) == [("pop", 4)]
    assert [k for k, _ in timeline.graphic_cues({"type": "score", "penalty": 0.3}, 150)] == ["pop", "pop", "pop", "impact"]


def test_graphic_media_finds_nested_files():
    graphic = {"type": "spotlight", "still": {"src": "spotlight/a.jpg", "kind": "image"},
               "cutout": {"src": "spotlight/a.png", "kind": "image"},
               "left": {"media": {"src": "media/s1.mp4", "kind": "video"}}}
    assert {m["src"] for m in graphic_media(graphic)} == {"spotlight/a.jpg", "spotlight/a.png", "media/s1.mp4"}
