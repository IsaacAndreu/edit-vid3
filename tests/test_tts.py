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
    (folder / tts.LOCK).write_text(f"{__import__('os').getpid()} now\n")
    assert main.pending_slugs(tmp_path) == []                         # being made in the background: next video first
    (folder / tts.LOCK).unlink()


def _negocios(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "negocios.yaml").write_text("format: historia\n", encoding="utf-8")
    folder = tmp_path / "materiales" / "negocios" / "n1"
    folder.mkdir(parents=True)
    (folder.parent / "config.yaml").write_text("canal: negocios\n", encoding="utf-8")
    (folder / "guion.txt").write_text("## UNO\n" + "Hola. " * 5, encoding="utf-8")
    tts.set_voice(tmp_path, "negocios", {"voice_id": "V1"})
    return folder


def test_the_background_makes_the_voice_as_soon_as_the_video_appears(tmp_path, monkeypatch):
    folder = _negocios(tmp_path)
    made = []

    def fake_generate(token, text, voice, target, session=None, log=print):
        assert (folder / tts.LOCK).is_file()                          # nobody else makes it meanwhile
        made.append(text)
        target.write_bytes(b"mp3")
        return {"chars": len(text), "pieces": 1, "tasks": ["t1"]}

    monkeypatch.setattr(tts, "generate", fake_generate)
    assert tts.prepare_all(tmp_path, log=lambda *_: None) == 1
    assert (folder / "voz.mp3").read_bytes() == b"mp3" and not (folder / tts.LOCK).exists()
    assert "UNO" not in made[0]
    assert tts.prepare_all(tmp_path, log=lambda *_: None) == 0       # already there: nothing more


def test_a_failure_is_noted_and_retried_later_not_every_loop(tmp_path, monkeypatch):
    folder = _negocios(tmp_path)
    calls, told = [], []

    def failing(*a, **k):
        calls.append(1)
        raise tts.TTSError("GenAIPro 402: sin créditos")

    monkeypatch.setattr(tts, "generate", failing)
    monkeypatch.setattr(tts, "_tell", lambda root, text: told.append(text))
    assert tts.prepare_all(tmp_path, log=lambda *_: None) == 0
    assert "sin créditos" in (folder / tts.FAILED).read_text("utf-8") and not (folder / tts.LOCK).exists()
    tts.prepare_all(tmp_path, log=lambda *_: None)
    assert len(calls) == 1 and len(told) == 1                         # waits RETRY_MINUTES before trying again


def test_held_videos_wait(tmp_path, monkeypatch):
    folder = _negocios(tmp_path)
    (folder / ".en-espera").write_text("x")
    monkeypatch.setattr(tts, "generate", lambda *a, **k: pytest.fail("held video"))
    assert tts.prepare_all(tmp_path, log=lambda *_: None) == 0


def test_the_queue_waits_for_the_voice_being_made_elsewhere(tmp_path, monkeypatch):
    from pipeline.context import RunContext

    folder = _negocios(tmp_path)
    (folder / tts.LOCK).write_text(f"{__import__('os').getpid()} now\n")
    ctx = RunContext.create("n1", root=tmp_path)
    assert tts.ensure(ctx, wait=False) is False                       # the background has it: don't make it twice

    def sleep(_):                                                      # the other one finishes while we wait
        (folder / "voz.mp3").write_bytes(b"mp3")
        (folder / tts.LOCK).unlink()

    monkeypatch.setattr(tts.time, "sleep", sleep)
    monkeypatch.setattr(tts, "generate", lambda *a, **k: pytest.fail("made twice"))
    assert tts.ensure(ctx) is False and (folder / "voz.mp3").is_file()


def test_a_restart_reuses_the_pieces_already_made(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    fake = _FakeGenAIPro(_mp3(tmp_path / "piece.mp3"))
    voice = {**tts.DEFAULTS, "voice_id": "V1", "max_chars": 40}
    text = "Primera frase del guion. Segunda frase.\n\nTercer párrafo con más texto."
    target = tmp_path / "v" / "voz.mp3"
    calls = {"n": 0}
    real_download = tts.GenAIPro.download

    def dies_on_the_second(self, url, path):
        calls["n"] += 1
        if calls["n"] == 2:
            raise tts.TTSError("restart")
        return real_download(self, url, path)

    monkeypatch.setattr(tts.GenAIPro, "download", dies_on_the_second)
    with pytest.raises(tts.TTSError):
        tts.generate("k", text, voice, target, session=fake, log=lambda *_: None)
    created = len(fake.created)
    tts.generate("k", text, voice, target, session=fake, log=lambda *_: None)
    assert target.is_file() and len(fake.created) == created          # no task paid twice
    assert not (target.parent / ".voz-trozos").exists()


class _FakeWithSubtitles(_FakeGenAIPro):
    def request(self, method, url, headers=None, timeout=None, json=None, params=None):
        if method == "POST" and "/v1/labs/task/subtitle/" in url:
            task = url.rsplit("/", 1)[1]
            return _Response(payload={"subtitle": f"https://media.example/{task}.vtt"})
        return super().request(method, url, headers=headers, timeout=timeout, json=json, params=params)

    def get(self, url, stream=False, timeout=None):
        if url.endswith(".vtt"):
            return _Response(content=b"WEBVTT\n\n00:00:00.000 --> 00:00:00.500\nHola mundo\n\n"
                                     b"00:00:00.500 --> 00:00:01.000\nadios\n")
        return super().get(url, stream, timeout)


def test_the_subtitles_give_word_timings_and_align_skips_whisper(tmp_path, monkeypatch):
    from pipeline import align

    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    fake = _FakeWithSubtitles(_mp3(tmp_path / "piece.mp3"))
    voice = {**tts.DEFAULTS, "voice_id": "V1", "max_chars": 20}
    folder = tmp_path / "v"
    target = folder / "voz.mp3"
    tts.generate("k", "Hola mundo adios.\n\nHola mundo adios.", voice, target, session=fake, log=lambda *_: None)
    spoken = tts.timings(target)
    assert spoken and [w["word"] for w in spoken["words"]] == ["Hola", "mundo", "adios"] * 2
    second = spoken["words"][3]
    assert 0.9 < second["start"] < 1.2                                # the second piece shifted by the first's length
    raw = align.build_words_file(slug="v", title="", script="## UNO\nHola mundo adios.\nHola mundo adios.", raw=spoken,
                                 provider="genaipro", model="subtitles", language="es")
    assert raw.alignment.matchRatio == 1.0
    target.write_bytes(target.read_bytes() + b"x")                    # another voz.mp3: its timings no longer count
    assert tts.timings(target) is None


def test_cues_from_srt_too():
    cues = tts.parse_cues("1\n00:00:01,200 --> 00:00:02,000\n<b>Hola</b> mundo\n\n2\n00:00:02,000 --> 00:00:03,500\nadiós\n")
    assert cues == [(1.2, 2.0, "Hola mundo"), (2.0, 3.5, "adiós")]


class _Credits:
    def __init__(self, amount):
        self.amount, self.calls = amount, 0

    def request(self, method, url, headers=None, timeout=None, json=None, params=None):
        assert url.endswith("/v1/labs/credits")
        self.calls += 1
        return _Response(payload=[{"amount": self.amount, "expire_at": "2027-01-01T00:00:00Z"}])


def test_low_credits_are_told_once_a_day(tmp_path, monkeypatch):
    _negocios(tmp_path)
    told = []
    monkeypatch.setattr(tts, "_tell", lambda root, text: told.append(text))
    api = _Credits(756_769)
    state = tts.check_credits(tmp_path, "k", api, now=1_000_000)
    assert state["videos"] > 50 and not told                             # ~54 voices left: nothing to say
    assert tts.check_credits(tmp_path, "k", api, now=1_000_100) is None and api.calls == 1    # once an hour
    api.amount = 40_000
    tts.check_credits(tmp_path, "k", api, now=1_004_000)
    assert len(told) == 1 and "unas 3 voces" in told[0]
    tts.check_credits(tmp_path, "k", api, now=1_008_000)
    assert len(told) == 1                                                # not again until tomorrow


def test_a_dropped_connection_while_waiting_is_retried_but_a_create_is_not(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    fake = _FakeGenAIPro(b"mp3")
    real = fake.request
    drops = {"n": 0}

    def flaky(method, url, **kw):
        if method == "GET" and drops["n"] < 2:
            drops["n"] += 1
            raise requests.ConnectionError("reset")
        return real(method, url, **kw)

    fake.request = flaky
    api = tts.GenAIPro("k", fake)
    assert api.wait("t1").endswith("t1.mp3") and drops["n"] == 2
    fake.request = lambda method, url, **kw: (_ for _ in ()).throw(requests.ConnectionError("reset"))
    with pytest.raises(tts.TTSError):
        api.create("hola", {**tts.DEFAULTS, "voice_id": "V1"})


def test_a_script_written_for_reading_is_made_ready_to_narrate():
    from pipeline.tts import clean_script, narration_text

    script = ("GUIÓN\n\n[GANCHO — 0:00]\n\nEntras a una tienda.\n\n[CAPÍTULO 1 — QUIÉN ESTÁ DETRÁS — 1:00]\n\n"
              "Factura más que Ross. [VERIFICAR cifra de Ross]\n\n[CTA SUSCRIPCIÓN — aprox. 5:20]\n\nSuscríbete.\n\n"
              "[CAPÍTULO 2: De dónde sale]\n\nCompran barato.\n")
    clean = clean_script(script)
    assert "## Quién está detrás" in clean and "## De dónde sale" in clean
    assert "[" not in clean and "GUIÓN" not in clean and "5:20" not in clean
    assert narration_text(script) == "Entras a una tienda.\n\nFactura más que Ross.\n\nSuscríbete.\n\nCompran barato."
