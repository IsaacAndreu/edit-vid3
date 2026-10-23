"""Whisper through the API: a voice over its 25 MB limit goes in pieces with the same timings (the «413» of patiICE)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import types

import pytest

from pipeline import whisper_local


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_a_long_voice_goes_in_pieces_and_keeps_its_timings(tmp_path, monkeypatch):
    voice = tmp_path / "voz.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=5", str(voice)], check=True)
    sent = []

    class Transcriptions:
        def create(self, model, file, **_):
            sent.append(file.name)
            return {"duration": 2.0 if len(sent) < 3 else 1.0, "language": "spanish",
                    "words": [{"word": f"w{len(sent)}", "start": 0.5, "end": 0.9}]}

    fake = types.SimpleNamespace(OpenAI=lambda api_key: types.SimpleNamespace(audio=types.SimpleNamespace(transcriptions=Transcriptions())))
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setattr(whisper_local, "OPENAI_MAX_BYTES", 10)
    monkeypatch.setattr(whisper_local, "OPENAI_CHUNK_SECONDS", 2)
    raw = whisper_local._transcribe_openai(voice, "key")
    assert len(sent) == 3 and all(name.endswith(".mp3") and "trozo" in name for name in sent)
    assert [w["start"] for w in raw["words"]] == [0.5, 2.5, 4.5] and raw["duration"] == 5.0

    monkeypatch.setattr(whisper_local, "OPENAI_MAX_BYTES", 10**9)       # small voices go as they are
    sent.clear()
    whisper_local._transcribe_openai(voice, "key")
    assert sent == [str(voice)]
