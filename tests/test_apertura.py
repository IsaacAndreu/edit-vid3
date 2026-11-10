"""The opening clip: found in a video's captions, translated line by line, chosen on the page, placed before the voice."""

import json
from types import SimpleNamespace

import pytest

from pipeline import apertura
from pipeline.context import RunContext
from pipeline.quotes import parse_vtt, timed_words
from pipeline.schemas import ColdOpenFile, Timeline

VTT = """WEBVTT

00:00:58.000 --> 00:01:02.000
okay next question from Instagram

00:01:02.000 --> 00:01:05.000
you have to have a certain body type to be a gymnast

00:01:06.200 --> 00:01:10.000
no, absolutely not. Gymnastics is for every body.

00:01:12.000 --> 00:01:15.000
next one
"""


def test_video_id_and_seconds():
    assert apertura.video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s") == "dQw4w9WgXcQ"
    assert apertura.video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert apertura.video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert apertura.video_id("Simone Biles instagram") is None
    assert apertura._seconds("1:15") == 75 and apertura._seconds("75.5") == 75.5 and apertura._seconds("") is None
    with pytest.raises(ValueError):
        apertura._seconds("uno")


def test_lines_split_at_pauses_and_sentence_ends():
    lines = apertura.lines_of(timed_words(parse_vtt(VTT)))
    texts = [l["original"] for l in lines]
    assert "you have to have a certain body type to be a gymnast" in " ".join(texts)
    assert any(t.startswith("no, absolutely not.") for t in texts) and "Gymnastics is for every body." in texts
    assert all(len(t.split()) <= 9 for t in texts)
    assert lines[0]["from"] == 58.0


def _ctx(tmp_path, monkeypatch, answers):
    ctx = RunContext.create("t", root=tmp_path, config={"align": {"language": "es"}})

    def fake(ctx, *, system, user, **kw):
        for key, answer in answers.items():
            if key in system:
                return answer(user) if callable(answer) else answer
        raise AssertionError(system[:60])

    monkeypatch.setattr(apertura, "complete_json", fake)
    return ctx


class FakeYouTube:
    def __init__(self):
        self.searched = []

    def search(self, query):
        self.searched.append(query)
        return [{"id": "aaaaaaaaaaa", "title": "Simone Biles answers Instagram questions", "channel": "Vogue", "duration": 600}]

    def info(self, vid):
        return {"title": "Given", "channel": "Given channel", "duration": 300}

    def close(self):
        pass


def test_search_finds_the_moment_and_translates_it(tmp_path, monkeypatch):
    import pipeline.quotes as quotes

    monkeypatch.setattr(quotes, "transcript", lambda ctx, yt, vid, lang, minutes: timed_words(parse_vtt(VTT)))
    ctx = _ctx(tmp_path, monkeypatch, {
        "CLIP REAL": {"about": "Biles responde si hace falta un tipo de cuerpo", "speaker": "Simone Biles",
                      "role": "gimnasta", "language": "en", "said": "you have to have a certain body type to be a gymnast",
                      "searches": ["Simone Biles answers Instagram questions body type"]},
        "Traduce": lambda user: {"lines": [f"ES {line}" for line in user.split("\n")]},
    })
    yt = FakeYouTube()
    result = apertura.search(ctx, title="Reglas de la gimnasia", script="La gimnasia tiene reglas.", ask="Biles Instagram",
                             youtube=yt)
    assert yt.searched == ["Simone Biles answers Instagram questions body type"]
    [c] = result["candidates"]
    assert c["id"] == "aaaaaaaaaaa" and c["speaker"] == "Simone Biles" and c["channel"] == "Vogue"
    assert 60 <= c["start"] <= 62.5 and c["end"] - c["start"] <= apertura.MAX_SECONDS
    assert all(l["text"].startswith("ES ") for l in c["lines"])
    # saved from the page with a later end: subtitles in seconds from the clip's start, only inside it
    saved = apertura.choice(c, 60.0, 70.0)
    assert saved["url"] == "https://www.youtube.com/watch?v=aaaaaaaaaaa" and saved["end"] == 70.0
    assert saved["subtitles"][0]["from"] >= 0 and all(s["to"] <= 10.0 for s in saved["subtitles"])
    assert not any("next one" in s["text"] for s in saved["subtitles"])
    with pytest.raises(ValueError):
        apertura.choice(c, 60.0, 60.5)
    assert apertura.choice(c, 0.0, 100.0)["end"] == apertura.LIMIT


def test_a_link_with_seconds_skips_the_search(tmp_path, monkeypatch):
    import pipeline.quotes as quotes

    monkeypatch.setattr(quotes, "transcript", lambda ctx, yt, vid, lang, minutes: timed_words(parse_vtt(VTT)))
    ctx = _ctx(tmp_path, monkeypatch, {"CLIP REAL": {"about": "x", "speaker": "S", "language": "en", "searches": ["q"]},
                                       "Traduce": {"lines": []}})          # a failed translation keeps the original
    yt = FakeYouTube()
    result = apertura.search(ctx, url="https://youtu.be/bbbbbbbbbbb", start=58.0, end=70.0, youtube=yt)
    assert yt.searched == []
    [c] = result["candidates"]
    assert (c["id"], c["start"], c["end"], c["title"]) == ("bbbbbbbbbbb", 58.0, 70.0, "Given")
    assert c["lines"][0]["text"] == c["lines"][0]["original"]


def test_the_opening_plays_before_the_voice(tmp_path):
    from pipeline.timeline import with_opening

    ctx = RunContext.create("t", root=tmp_path, config={})
    shot = lambda i: {"id": f"s{i:03d}", "type": "broll", "from": i * 60, "durationInFrames": 60, "text": "x",  # noqa: E731
                      "media": {"src": "a.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}}
    timeline = Timeline.model_validate({"slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080,
                                        "durationInFrames": 240, "shots": [shot(i) for i in range(4)], "groups": [],
                                        "labels": [{"kind": "name", "text": "Hola", "from": 30, "durationInFrames": 30}],
                                        "audio": {"voice": "audio/voz.mp3", "speech": [(0, 230)],
                                                  "sfx": [{"src": "a.wav", "from": 60, "volume": 1.0}]}})
    clip = SimpleNamespace(path=str(ctx.work_dir / "coldopen" / "apertura.mp4"), durationSeconds=10.0, credit="Fuente: Vogue",
                           width=1920, height=1080, speaker="Simone Biles", role="gimnasta",
                           subtitles=[SimpleNamespace(text="Hay que tener un tipo de cuerpo", from_=0.5, to=4.0),
                                      SimpleNamespace(text="No, para nada", from_=5.0, to=12.0)])
    out = with_opening(timeline, clip, ctx, 30)
    assert out.shots[0].id == "apertura" and out.shots[0].coldOpen and out.shots[0].durationInFrames == 300
    assert out.shots[1].from_ == 300 and out.durationInFrames == 540
    assert out.audio.voiceFrom == 300 and out.audio.speech[0] == (0, 300) and out.audio.speech[1] == (300, 530)
    assert out.audio.clips[0].from_ == 0 and out.audio.sfx[0].from_ == 360 and out.labels[0].from_ == 330
    quote = out.groups[0]
    assert quote.graphic["type"] == "quote" and quote.graphic["speaker"] == "Simone Biles"
    assert quote.graphic["lines"][1] == {"text": "No, para nada", "from": 150, "to": 300}


def test_chosen_file_and_schema(tmp_path):
    ctx = RunContext.create("t", root=tmp_path, config={})
    assert apertura.chosen(ctx) is None
    ctx.materials_dir.mkdir(parents=True, exist_ok=True)
    (ctx.materials_dir / apertura.FILE).write_text(json.dumps({"url": "https://youtu.be/aaaaaaaaaaa", "start": 61, "end": 75}))
    assert apertura.chosen(ctx)["start"] == 61
    data = ColdOpenFile.model_validate({"slug": "t", "opening": {
        "path": "work/t/coldopen/a.mp4", "candidateId": "yt:a", "url": "u", "start": 61, "end": 81, "durationSeconds": 20,
        "width": 1920, "height": 1080, "credit": "Fuente: Vogue", "afterSeconds": 0, "speaker": "Simone Biles"}})
    assert data.opening.durationSeconds == 20


def test_your_own_video_is_cut_here_without_subtitles(tmp_path, monkeypatch):
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg")
    ctx = _ctx(tmp_path, monkeypatch, {"CLIP REAL": {"about": "x", "speaker": "Simone Biles", "language": "en", "searches": []}})
    monkeypatch.setattr(apertura, "whisper", lambda *a: (_ for _ in ()).throw(AssertionError("no transcription needed")))
    upload = tmp_path / "out" / "_tareas" / "apertura-0123456789ab.mp4"
    upload.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=12",
                    "-f", "lavfi", "-i", "sine=f=330:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(upload)], check=True)
    result = apertura.search(ctx, file=str(upload), start=3.0, end=7.5, subtitles=False)
    [c] = result["candidates"]
    assert (c["file"], c["start"], c["end"], c["lines"]) == ("0123456789ab", 3.0, 7.5, [])
    saved = apertura.choice(c, "3", "7.5", subtitles=False, credit="Vogue")
    assert saved["file"] == "0123456789ab" and saved["subtitles"] == [] and saved["channel"] == "Vogue" and not saved["url"]
    # what create_video does: the upload goes next to the script
    ctx.materials_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(upload), str(ctx.materials_dir / "apertura.mp4"))
    (ctx.materials_dir / apertura.FILE).write_text(json.dumps({**saved, "file": "apertura.mp4"}))
    out = ctx.work_dir / "coldopen"
    out.mkdir(parents=True)
    clip = apertura.pick(ctx, None, out)
    assert 4.3 <= clip["durationSeconds"] <= 4.6 and clip["credit"] == "Fuente: Vogue" and clip["subtitles"] == []
    assert clip["candidateId"] == "file:apertura.mp4" and (ctx.root / clip["path"]).is_file()


def test_no_subtitles_no_quote_box(tmp_path):
    from pipeline.timeline import with_opening

    ctx = RunContext.create("t", root=tmp_path, config={})
    timeline = Timeline.model_validate({"slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080,
                                        "durationInFrames": 60, "groups": [], "audio": {"voice": "audio/voz.mp3"},
                                        "shots": [{"id": "s000", "type": "broll", "from": 0, "durationInFrames": 60, "text": "x",
                                                   "media": {"src": "a.mp4", "kind": "video", "source": "youtube",
                                                             "credit": "Fuente: X"}}]})
    clip = SimpleNamespace(path=str(ctx.work_dir / "coldopen" / "a.mp4"), durationSeconds=4.0, credit="Fuente: S", width=1920,
                           height=1080, speaker="S", role=None, subtitles=[])
    out = with_opening(timeline, clip, ctx, 30)
    assert out.groups == [] and out.shots[0].id == "apertura" and out.audio.voiceFrom == 120
