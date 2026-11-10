"""Tanda C: what-if videos, data videos, news round-ups and native vertical shorts."""

import sys
import types

from pipeline import graphics
from pipeline.config import PROJECT_ROOT
from pipeline.context import RunContext
from pipeline.schemas import BrollSpec, Shot, Timeline, WordsFile
from pipeline.sourcing import hypothetical
from pipeline.sourcing.youtube import YouTubeSource, _upload_filter
from pipeline.timeline import captions

BROLL = {"visualIntent": "bank branch", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}


def _shot(event):
    return Shot.model_validate({"id": "s001", "type": "broll", "startWord": 0, "endWord": 1, "start": 0, "end": 2,
                                "text": "t", "chapter": 0, "broll": {**BROLL, "event": event}})


def _video(root, text, fmt_files=True):
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.yaml").write_text("video: {width: 1920, height: 1080}\nsourcing: {youtube: {results_per_query: 8}}\n")
    (root / "materiales" / "v").mkdir(parents=True)
    (root / "materiales" / "v" / "config.yaml").write_text(text)
    return RunContext.create("v", root=root)


def test_what_if_shots_are_recognised():
    assert hypothetical(_shot("WHAT IF: Spanish banks with no crisis 2010"))
    assert hypothetical(_shot("what if Lehman had been rescued"))
    assert not hypothetical(_shot("Lehman Brothers collapse 2008 news"))
    assert not hypothetical(_shot(None))


def test_what_if_images_are_illustrations(tmp_path, monkeypatch):
    import base64

    import cv2
    import numpy as np

    from pipeline import fallback

    ok, png = cv2.imencode(".png", np.zeros((64, 96, 3), np.uint8))
    prompts = []

    class Images:
        def generate(self, **kw):
            prompts.append(kw["prompt"])
            return types.SimpleNamespace(data=[types.SimpleNamespace(b64_json=base64.b64encode(png.tobytes()).decode())],
                                         usage=None)

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=lambda api_key: types.SimpleNamespace(images=Images())))
    ctx = RunContext.create("v", root=tmp_path, config={"paths": {}})
    monkeypatch.setattr(ctx, "env", lambda *a, **k: "key")
    ctx.write_json("shots.json", {"context": "Spain 2008"})
    (tmp_path / "out").mkdir()
    item = fallback._generate(ctx, _shot("WHAT IF: Spanish banks with no crisis 2010"), "r", "h", tmp_path / "out", None,
                              {"image_usd_estimate": 0.05}, illustration=True)
    assert item.method == "generated" and "illustration" in prompts[0].lower()
    assert "Spanish banks with no crisis" in prompts[0] and "No recognizable real people" in prompts[0]
    # a channel that draws its story scenes (image_style: illustration): pencil and watercolor, never a photo
    fallback._generate(ctx, _shot("Concorde first flight 1969"), "r", "h", tmp_path / "out", None,
                       {"image_usd_estimate": 0.05, "image_style": "illustration"})
    assert "pencil and watercolor" in prompts[1] and "Photorealistic" not in prompts[1]


def test_data_csv_is_read_in_any_common_shape(tmp_path):
    path = tmp_path / "datos.csv"
    path.write_text("Año;España;Francia\n2000;1.234,5;12\n2004;2.000;15,5\n2008;0.125;20\n", "utf-8")
    column, steps = graphics.read_data(path)
    assert column == "Año" and [s["label"] for s in steps] == ["2000", "2004", "2008"]
    assert steps[0]["values"] == {"España": 1234.5, "Francia": 12.0}
    assert steps[1]["values"]["España"] == 2000 and steps[2]["values"]["España"] == 0.125
    path.write_text("year,A,B\n1990,1,2\n1991,3,4\n", "utf-8")
    assert graphics.read_data(path)[1][1]["values"] == {"A": 3.0, "B": 4.0}


def test_data_race_enters_when_a_year_is_said(tmp_path):
    ctx = _video(tmp_path, "format: datos\ndatos: {titulo: Medallas}\n")
    (ctx.materials_dir / "datos.csv").write_text("Año,URSS,China\n1980,10,1\n1988,12,4\n1996,0,8\n2008,0,20\n", "utf-8")
    sents = [{"n": i, "start": 20.0 * i, "end": 20.0 * i + 10, "text": t} for i, t in enumerate([
        "Empezamos.", "En 1980 la URSS mandaba.", "Todo cambia.", "En 1996 ya no existía.", "Y en 2008, China."])]
    out = graphics.data_race(ctx, sents)
    assert [o["graphic"]["steps"][-1]["label"] for o in out] == ["1980", "1996", "2008"]
    assert [s["label"] for s in out[1]["graphic"]["steps"]] == ["1980", "1988", "1996"]   # animates across 1988
    assert out[0]["graphic"]["title"] == "Medallas" and out[-1]["end"] - out[-1]["start"] > out[0]["end"] - out[0]["start"]


def test_formats_bring_settings_that_the_video_can_still_change(tmp_path):
    news = _video(tmp_path / "a", "format: noticias\n")
    assert news.section("sourcing")["youtube"]["recent_days"] == 14
    assert news.section("sourcing")["youtube"]["results_per_query"] == 8          # the rest stays
    week = _video(tmp_path / "b", "format: noticias\nsourcing: {youtube: {recent_days: 7}}\n")
    assert week.section("sourcing")["youtube"]["recent_days"] == 7
    short = _video(tmp_path / "c", "format: short\n")
    assert (short.section("video")["width"], short.section("video")["height"]) == (1080, 1920)
    assert short.section("timeline")["captions"] is True and short.section("render")["hybrid"] is False
    assert _video(tmp_path / "d", "format: historia\n").section("video")["width"] == 1920


def test_recent_searches_use_the_upload_date_filter(tmp_path, monkeypatch):
    assert [_upload_filter(d) for d in (1, 7, 14, 31, 400)] == ["EgQIAhAB", "EgQIAxAB", "EgQIBBAB", "EgQIBBAB", "EgQIBRAB"]
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "recent_days": 7})
    seen = []

    class Ydl:
        def extract_info(self, target, download):
            seen.append(target)
            return {"entries": [{"id": "abcdefghijk", "title": "t", "duration": 100}]}

    monkeypatch.setattr(yt, "_ydl", lambda extra=None: Ydl())
    assert yt.search("spacex ipo")[0]["id"] == "abcdefghijk"
    assert seen[0].startswith("https://www.youtube.com/results?search_query=spacex+ipo&sp=EgQIAxAB")


def test_captions_follow_the_voice_after_the_cold_open():
    words = WordsFile.model_validate({
        "slug": "t", "title": "T", "language": "es", "durationSeconds": 4.0,
        "words": [{"index": i, "text": t, "start": s, "end": s + 0.3, "matched": True}
                  for i, (t, s) in enumerate([("Cada", 0.0), ("Mercadona", 0.4), ("factura", 0.8), ("mucho.", 1.2),
                                              ("Pero", 2.5), ("¿por", 2.9), ("qué?", 3.2)])],
        "chapters": [], "alignment": {"provider": "l", "model": "m", "scriptWords": 7, "whisperWords": 7,
                                      "matchedWords": 7, "matchRatio": 1.0}})
    timeline = Timeline.model_validate({
        "slug": "t", "title": "T", "fps": 30, "width": 1080, "height": 1920, "durationInFrames": 180,
        "shots": [{"id": "s000", "type": "broll", "from": 0, "durationInFrames": 180, "text": "t",
                   "media": {"src": "m.jpg", "kind": "image", "source": "wikimedia", "credit": "Fuente: X"}}],
        "groups": [], "audio": {"voice": "v.mp3", "voiceFrom": 60}})
    out = captions(words, timeline, 3)
    assert [[w.text for w in c.words] for c in out] == [["Cada", "Mercadona", "factura"], ["mucho."], ["Pero", "¿por", "qué?"]]
    assert out[0].from_ == 60 and out[0].words[1].from_ == 12 and out[2].from_ == 60 + 75
