"""Real statements: find where the quoted sentence is said in a video's captions, and cut it in with subtitles."""

from pathlib import Path

from pipeline.quotes import best_match, parse_vtt, timed_words
from pipeline.schemas import Timeline

# YouTube's automatic captions repeat each line while the next one is typed in
VTT = """WEBVTT
Kind: captions
Language: en

00:01:10.000 --> 00:01:12.500
so we we have been very clear with

00:01:12.500 --> 00:01:12.510
so we we have been very clear with

00:01:12.510 --> 00:01:15.000
so we we have been very clear with
Boeing they are fully aware of the

00:01:15.000 --> 00:01:18.000
Boeing they are fully aware of the
damage it has caused Emirates and

00:01:18.000 --> 00:01:21.000
damage it has caused Emirates and
we expect them to fix it
"""


def test_rolling_captions_become_one_clean_transcript():
    text = " ".join(t for _, _, t in parse_vtt(VTT))
    assert text == "so we we have been very clear with Boeing they are fully aware of the damage it has caused Emirates and we expect them to fix it"


def test_the_quote_is_found_where_it_is_said():
    words = timed_words(parse_vtt(VTT))
    start, end, score, original = best_match(words, "Boeing is fully aware of the damage it has caused Emirates")
    assert 72.5 <= start <= 75.5 and 76 <= end <= 19.5 * 60 and score >= 0.7
    assert original.startswith("Boeing") and "Emirates" in original
    assert best_match(words, "The A380 was the best aircraft ever built by Airbus")[2] < 0.55


def test_a_statement_pauses_the_narration_and_carries_its_subtitles(tmp_path):
    from types import SimpleNamespace

    from pipeline.context import RunContext
    from pipeline.timeline import with_quotes

    ctx = RunContext.create("t", root=tmp_path, config={})
    shot = lambda i: {"id": f"s{i:03d}", "type": "broll", "from": i * 60, "durationInFrames": 60, "text": "x",  # noqa: E731
                      "media": {"src": "a.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}}
    timeline = Timeline.model_validate({"slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080,
                                        "durationInFrames": 240, "shots": [shot(i) for i in range(4)], "groups": [],
                                        "audio": {"voice": "audio/voz.mp3", "speech": [(0, 230)]}})
    quote = SimpleNamespace(path=str(ctx.work_dir / "coldopen" / "q01.mp4"), afterSeconds=4.0, durationSeconds=6.0,
                            credit="Fuente: CNBC", width=1920, height=1080, speaker="Tim Clark", role="presidente de Emirates",
                            subtitles=[SimpleNamespace(text="Boeing es plenamente consciente", from_=0.3, to=3.0),
                                       SimpleNamespace(text="del daño que ha causado a Emirates", from_=3.0, to=5.8)])
    out = with_quotes(timeline, [quote], ctx, 30)
    clip = next(s for s in out.shots if s.coldOpen)
    assert clip.from_ == 120 and clip.durationInFrames == 180 and out.durationInFrames == 420
    group = next(g for g in out.groups if g.graphic and g.graphic["type"] == "quote")
    assert group.from_ == 120 and group.graphic["speaker"] == "Tim Clark"
    assert group.graphic["lines"][1] == {"text": "del daño que ha causado a Emirates", "from": 90, "to": 174}
    assert out.audio.voiceGaps == [(120, 180)]
