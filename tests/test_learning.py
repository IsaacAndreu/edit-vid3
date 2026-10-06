"""The program learns from your «Errores» labels: channels blocked, corrections shown to the judge."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import feedback
from pipeline.sourcing import common


def _labels(root: Path, entries: dict) -> None:
    path = root / feedback.LABELS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def _entry(verdict, reason="", channel="Canal Malo", text="La multa de Booking", title="clip", at="2026-10-01T10:00:00"):
    return {"verdict": verdict, "reason": reason, "candidateId": "yt:x", "start": 1.0, "end": 2.0, "method": "judge",
            "text": text, "source": "youtube", "url": "", "title": title, "channel": channel,
            "videoChannel": "negocios", "at": at}


def test_a_channel_wrong_three_times_is_blocked_everywhere(tmp_path):
    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    _labels(tmp_path, {
        "n1/s001": _entry("incorrecta", "no_tiene_que_ver"),
        "n1/s002": _entry("incorrecta", "roto"),
        "n2/s003": _entry("incorrecta", "persona_equivocada"),              # not the channel's fault
        "n2/s004": _entry("incorrecta", "dibujo_animado", channel="Otro"),
    })
    assert feedback.blocked_channels(tmp_path) == {}
    _labels(tmp_path, {**json.loads((tmp_path / feedback.LABELS).read_text()),
                       "n3/s005": _entry("incorrecta", "texto_marca_agua")})
    assert feedback.blocked_channels(tmp_path) == {"Canal Malo": 3}
    try:
        assert feedback.load_learned(tmp_path) == ["Canal Malo"]
        assert common.blocked_by_title("Cualquier título", "canal malo") == "canal malo"
        assert common.blocked_by_title("Cualquier título", "Canal Bueno") is None
    finally:
        common.LEARNED_BLOCKED_CHANNELS = set()


def test_a_channel_mostly_right_is_not_blocked(tmp_path):
    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    wrong = {f"n1/s00{i}": _entry("incorrecta", "no_tiene_que_ver") for i in range(3)}
    right = {f"n2/s00{i}": _entry("correcta") for i in range(4)}
    _labels(tmp_path, {**wrong, **right})
    assert feedback.blocked_channels(tmp_path) == {}


def test_the_judge_sees_this_channels_corrections(tmp_path):
    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    _labels(tmp_path, {
        "n1/s001": _entry("incorrecta", "no_tiene_que_ver", text="Booking recurrió la multa", title="Hotel tour"),
        "n1/s002": _entry("correcta", text="La CNMC multó a Booking", title="CNMC rueda de prensa"),
        "a1/s001": {**_entry("incorrecta", "roto", text="Salto de Simone"), "videoChannel": "gimnasia"},
    })
    text = feedback.lessons(tmp_path, "negocios")
    assert "Booking recurrió la multa" in text and "WRONG: No tiene que ver con la frase" in text
    assert "RIGHT" in text and "Simone" not in text
