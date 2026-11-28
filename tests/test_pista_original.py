"""The sound of a range is the video's own (original) track, never a dubbed or auto-dubbed one: «the worst audio»
is the worst in language too."""

from __future__ import annotations

from pipeline.sourcing.youtube import YouTubeSource, hls_format, selectable


def _audio(fid, lang, pref, note, tbr):
    return {"format_id": fid, "protocol": "m3u8_native", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "mp4",
            "language": lang, "language_preference": pref, "format_note": note, "tbr": tbr,
            "url": f"https://x/{fid}/index.m3u8"}


TRACKS = [
    _audio("233-0", "en", 10, "English original (default), low", 48),
    _audio("233-1", "es", -1, "Spanish, low", 40),
    _audio("233-2", "de", -10, "German (dubbed-auto), low", 32),
    {"format_id": "140-0", "protocol": "https", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a",
     "language": "en", "language_preference": 10, "format_note": "English original (default), medium", "tbr": 128,
     "url": "https://x/140-0"},
    {"format_id": "140-2", "protocol": "https", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a",
     "language": "de", "language_preference": -10, "format_note": "German (dubbed-auto), medium", "tbr": 120,
     "url": "https://x/140-2"},
]
DATA = {"id": "abcdefghijk", "extractor": "youtube", "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "formats": TRACKS}


def _pick(tmp_path, request):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    with yt._ydl({"format": request, "simulate": True, "quiet": True}) as ydl:
        chosen = ydl.process_ie_result(selectable(DATA), download=False)
    return [p["format_id"] for p in (chosen.get("requested_formats") or [chosen])]


def test_the_sound_of_a_statement_is_the_original_track(tmp_path):
    assert _pick(tmp_path, hls_format("ba", audio_only=True)) == ["233-0"]           # not the auto-dubbed 233-2
    assert _pick(tmp_path, "ba[ext=m4a]/ba") == ["140-0"]


def test_without_an_original_marked_every_track_stays(tmp_path):
    plain = [dict(t, language_preference=-1, format_note="low") for t in TRACKS[:2]]
    kept = selectable({**DATA, "formats": plain})["formats"]
    assert [f["format_id"] for f in kept] == ["233-0", "233-1"]
    broken = selectable({**DATA, "formats": [{"format_id": "x"}, None, "roto", *TRACKS[:1]]})["formats"]
    assert any(isinstance(f, dict) and f.get("format_id") == "233-0" for f in broken)
