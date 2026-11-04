"""Atlas deep dives: the LLM's scenes cleaned, every element at its word, chapters, cues, drawn and dubbed."""

from pathlib import Path
from types import SimpleNamespace

from pipeline import atlas, dub, stickman
from pipeline.context import RunContext


def test_clean_keeps_only_the_vocabulary_and_falls_back_to_the_globe():
    scene = atlas.clean({"view": "chart", "camera": {"lat": -90, "lon": 0, "zoom": 9},
                         "routes": [{"from": [-31.9, 115.8], "to": [-34.6, -58.4], "label": "6.500 km", "style": "main", "at": "cuerda"},
                                    {"from": "x", "to": [1, 2]}],
                         "rings": [{"lat": -54.8, "lon": -68.3, "km": 99999, "label": "Ushuaia"}],
                         "card": {"kind": "quote", "title": "Tratado", "lines": ["cita"], "at": "dice"},
                         "chart": {"kind": "bars", "bars": [{"label": "787", "value": "330"}]}}, None)
    assert scene["camera"] == {"lat": -90.0, "lon": 0.0, "zoom": 6.0}
    assert len(scene["routes"]) == 1 and scene["rings"][0]["km"] == 6000 and scene["rings"][0]["label"] == "USHUAIA"
    assert scene["view"] == "chart" and scene["chart"]["bars"][0]["value"] == 330
    bad = atlas.clean({"view": "icon", "icon": {"name": "unicornio"}}, scene)
    assert bad["view"] == "globe" and bad["camera"] == scene["camera"]          # no valid icon: the globe, same camera


def _shot(i, start, dur, text, kind="broll", title=None, number=None):
    return SimpleNamespace(id=f"s{i}", type=kind, from_=start, durationInFrames=dur, text=text,
                           chapterTitle=title, chapterNumber=number)


def test_groups_time_elements_to_their_words_and_carry_the_chapters(monkeypatch, tmp_path: Path):
    ctx = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "brand": {"name": "Atlas"}})
    shots = [_shot(0, 0, 90, "Estira una cuerda de Perth a Buenos Aires."),
             _shot(1, 90, 60, "", "chapter", "Nadie a quien *volar*", 1),
             _shot(2, 150, 90, "Casi nadie vive en el sur.")]
    monkeypatch.setattr(atlas, "scenes", lambda c, s: {
        "s0": atlas.clean({"camera": {"lat": -90, "lon": 0, "zoom": 1.5},
                           "points": [{"name": "Perth", "lat": -31.9, "lon": 115.8, "at": "Perth"}]}, None),
        "s2": atlas.clean({"camera": {"lat": -40, "lon": 20, "zoom": 1}}, None)})
    words = SimpleNamespace(words=[SimpleNamespace(start=1.5, text="Perth"), SimpleNamespace(start=0.2, text="Estira")])
    out = atlas.groups(ctx, shots, 30, [], words)
    assert [g["graphic"]["view"] for g in out] == ["globe", "title", "globe"]
    assert out[0]["graphic"]["points"][0]["at"] == 45                  # the frame of «Perth»
    assert out[1]["graphic"]["title"] == {"number": "I", "text": "Nadie a quien *volar*"}
    assert out[2]["graphic"]["chapter"] == 1 and out[2]["graphic"]["chapters"] == ["Nadie a quien *volar*"]
    assert out[2]["graphic"]["prev"] == out[0]["graphic"]["camera"]    # the globe turns from the last globe shot
    assert out[0]["graphic"]["brand"] == "Atlas"


def test_atlas_is_drawn_and_its_texts_are_dubbed(tmp_path: Path):
    ctx = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}})
    assert atlas.active(ctx) and stickman.drawn(ctx) and stickman.film(ctx)
    assert "atlas" in dub.DRAWN_TEXTS and "card" in dub.DRAWN_TEXTS["atlas"]
    cues = atlas.cues({"prev": {"lat": 0, "lon": 0, "zoom": 1}, "camera": {"lat": -90, "lon": 0, "zoom": 2},
                       "stamp": {"at": 10}, "routes": [{"at": 5}]}, 30)
    assert {c[0] for c in cues} >= {"whoosh-down", "stamp", "marker"}


def test_writing_guide_per_language(tmp_path: Path):
    es = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "align": {"language": "es"}})
    en = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "align": {"language": "en"}})
    assert "cinco razones" in atlas.writing(es) and "five reasons" in atlas.writing(en)


def test_description_cites_the_checked_facts(tmp_path: Path):
    import json

    from pipeline import publish

    ctx = RunContext.create("t", root=tmp_path, config={"visual": {"style": "atlas"}, "align": {"language": "en"}})
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    (ctx.work_dir / "factcheck.json").write_text(json.dumps({"claims": [
        {"claim": "The A350 is certified for 370-minute ETOPS", "verdict": "ok", "source": "https://example.org/a350"},
        {"claim": "Unsure thing", "verdict": "unverified", "source": "https://example.org/x"},
        {"claim": "Duplicate", "verdict": "ok", "source": "https://example.org/a350"}]}))
    text = publish.fact_sources(ctx, 1000)
    assert text == "Sources\nThe A350 is certified for 370-minute ETOPS: https://example.org/a350"
    assert publish.compact_credits([], 1000).strip().count("\n") == 0        # no third-party sources: the heading alone


def test_the_camera_fits_what_is_drawn_and_a_line_in_the_same_place_keeps_it():
    scene = atlas.clean({"camera": {"lat": -45, "lon": 100, "zoom": 2},
                         "routes": [{"from": [-31.9, 115.8], "to": [-34.6, -58.4], "at": "cuerda"}]}, None)
    fitted = atlas.fit_camera(scene)
    assert fitted["camera"]["lat"] < -70 and fitted["camera"]["zoom"] <= 1.3          # looks down at the pole, pulled out
    nxt = atlas.carry(atlas.clean({"camera": dict(fitted["camera"])}, fitted), fitted)
    assert nxt["routes"] and nxt["routes"][0]["kept"]
    moved = atlas.carry(atlas.clean({"camera": {"lat": 50, "lon": 0, "zoom": 2}}, fitted), fitted)
    assert not moved["routes"]


def test_autopilot_asks_an_atlas_channel_for_a_question_in_five_reasons(monkeypatch, tmp_path: Path):
    from pipeline import autopilot, llm

    (tmp_path / "canales").mkdir()
    (tmp_path / "config.yaml").write_text("align: {language: es}\n")
    (tmp_path / "canales" / "atlas-es.yaml").write_text("visual: {style: atlas}\nideas: {about: mapas}\n")
    seen = {}

    def fake(ctx, **kw):
        seen.update(kw)
        return {"title": "¿Por qué nadie vive aquí?"}

    monkeypatch.setattr(llm, "complete_json", fake)
    import pipeline.porque as porque
    import pipeline.repeticion as repeticion
    monkeypatch.setattr(porque, "lessons", lambda root, ch: [])
    monkeypatch.setattr(repeticion, "recent_titles", lambda root, ch: [])
    idea = autopilot.idea_from(tmp_path, "atlas-es", {"title": "Why planes avoid Antarctica", "channel": "X", "views": 1, "ratio": 50})
    assert idea["title"] and "cinco razones" in seen["system"] and "PREGUNTA" in seen["system"]
