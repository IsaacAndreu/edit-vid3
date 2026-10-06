"""GenAIPro narration: the text sent, the pieces of a long script, the create → wait → download flow, the queue."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline import tts


def _mp3(path: Path, seconds: float = 1.0) -> bytes:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:a", "libmp3lame", str(path)], check=True)
    return path.read_bytes()


class _Response:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code, self._payload, self.content = status, payload, content or (b"{}" if payload is not None else b"")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, size):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeGenAIPro:
    def __init__(self, audio: bytes):
        self.audio, self.created, self.polls = audio, [], {}

    def request(self, method, url, headers=None, timeout=None, json=None, params=None):
        assert headers["Authorization"] == "Bearer k"
        if method == "POST" and url.endswith("/v1/labs/task"):
            self.created.append(json)
            return _Response(payload={"task_id": f"t{len(self.created)}"})
        if method == "GET" and "/v1/labs/task/" in url:
            task = url.rsplit("/", 1)[1]
            self.polls[task] = self.polls.get(task, 0) + 1
            done = self.polls[task] >= 2                             # «processing» once, then «completed»
            return _Response(payload={"status": "completed" if done else "processing",
                                      "result": f"https://media.example/{task}.mp3" if done else ""})
        raise AssertionError(url)

    def get(self, url, stream=False, timeout=None):
        return _Response(content=self.audio)


def test_the_text_drops_chapter_lines_and_marks():
    assert tts.narration_text("## CAPÍTULO I\nHola **mundo**.\n\n\n\nAdiós.") == "Hola mundo.\n\nAdiós."


def test_long_scripts_go_in_pieces_at_paragraphs_and_sentences():
    text = "\n\n".join(["Frase uno. Frase dos."] * 10)
    parts = tts.pieces(text, 60)
    assert all(len(p) <= 60 for p in parts) and " ".join(parts).count("Frase") == 20
    long = "Palabra " * 40
    assert all(len(p) <= 50 for p in tts.pieces(long.strip(), 50))


def test_generate_creates_waits_downloads_and_joins(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    fake = _FakeGenAIPro(_mp3(tmp_path / "piece.mp3"))
    voice = {**tts.DEFAULTS, "voice_id": "V1", "max_chars": 40}
    target = tmp_path / "voz.mp3"
    result = tts.generate("k", "Primera frase del guion. Segunda frase.\n\nTercer párrafo con más texto.", voice, target,
                          session=fake, log=lambda *_: None)
    assert result["pieces"] == len(fake.created) >= 2 and target.is_file()
    assert fake.created[0]["voice_id"] == "V1" and fake.created[0]["model_id"] == "eleven_multilingual_v2"
    duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(target)], capture_output=True, text=True).stdout)
    assert duration > 1.5                                             # the pieces joined, not just the first


def test_no_key_is_a_clear_error():
    with pytest.raises(tts.TTSError, match="GENAIPRO_API_KEY"):
        tts.GenAIPro("")


def test_a_channel_with_a_voice_puts_a_script_only_video_in_the_queue(tmp_path):
    import main

    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "negocios.yaml").write_text("format: historia\n", encoding="utf-8")
    folder = tmp_path / "materiales" / "negocios" / "n1"
    folder.mkdir(parents=True)
    (folder.parent / "config.yaml").write_text("canal: negocios\n", encoding="utf-8")
    (folder / "guion.txt").write_text("Hola. " * 50, encoding="utf-8")
    assert main.pending_slugs(tmp_path) == []                         # no voice and no voice for the channel
    tts.set_voice(tmp_path, "negocios", {"voice_id": "V1", "name": "Narrador", "speed": 1.5})
    assert tts.voice_for(tmp_path, "negocios")["speed"] == 1.2        # clamped to GenAIPro's range
    assert main.pending_slugs(tmp_path) == ["n1"]
