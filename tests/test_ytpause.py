"""The queue pauses itself while YouTube blocks the connection and resumes when a probe works."""

from __future__ import annotations

from pathlib import Path

from pipeline import ytpause


def test_pause_is_written_once_and_resume_clears_it(tmp_path: Path, monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(ytpause, "_tell", lambda root, text: sent.append(text))
    assert ytpause.paused(tmp_path) is None
    ytpause.pause(tmp_path, "YouTube ha bloqueado las búsquedas")
    ytpause.pause(tmp_path, "otra vez")                       # a second blocked video: no second message
    assert ytpause.paused(tmp_path)["reason"].startswith("YouTube ha bloqueado")
    assert len(sent) == 1
    assert not ytpause.due(tmp_path, 60) and ytpause.due(tmp_path, 0)
    ytpause.resume(tmp_path)
    assert ytpause.paused(tmp_path) is None and len(sent) == 2


def test_blocked_is_a_runtime_error() -> None:
    assert issubclass(ytpause.YouTubeBlocked, RuntimeError)
