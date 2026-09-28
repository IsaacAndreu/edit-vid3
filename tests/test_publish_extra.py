from pipeline.publish import subtitles
from pipeline.schemas import Timeline


def _timeline(voice_from=0, gaps=()):
    return Timeline.model_validate({
        "slug": "x", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 3000,
        "shots": [{"id": "d", "type": "datacard", "from": 0, "durationInFrames": 3000, "text": ""}], "groups": [],
        "audio": {"voice": "v.mp3", "voiceFrom": voice_from, "voiceGaps": list(gaps)}})


def _words(text, start=0.0):
    return [{"text": w, "start": start + i * 0.4, "end": start + i * 0.4 + 0.35} for i, w in enumerate(text.split())]


def test_cues_break_at_sentences_and_shift_with_cold_open_and_moments():
    words = _words("Hola a todos. Esta es la historia de un gimnasta que lo cambió todo en Filipinas para siempre.")
    srt = subtitles(_timeline(voice_from=150, gaps=[(60, 90)]), words)
    blocks = srt.strip().split("\n\n")
    assert blocks[0].startswith("1\n00:00:05,000 --> ")                   # after a 5 s cold open
    assert blocks[0].endswith("Hola a todos.")
    assert blocks[1].startswith("2\n00:00:06,200 --> ") and blocks[1].endswith("Esta es")   # cut at the moment
    assert blocks[2].startswith("3\n00:00:10,000 --> ")                  # "la" at voice 2 s + 5 s cold open + 3 s moment
    for block in blocks:
        for line in block.split("\n")[2:]:
            assert len(line) <= 42
