"""«Lo que dicen estos datos» 2: every failed row says why, «otros» is split into causes, and a video already refused
is no failed request."""

from __future__ import annotations

import json

import pytest

from pipeline import ytstats
from pipeline.sourcing.youtube import Refused, YouTubeSource, error_cause, error_kind, tunnel_failure


@pytest.mark.parametrize("message, cause", [
    ("('Unable to connect to proxy', OSError('Tunnel connection failed: 502 Bad Gateway'))", "proxy-túnel"),
    ("Unable to connect to proxy: Remote end closed connection without response", "proxy-túnel"),
    ("El proxy gw.x no responde", "proxy-sin-respuesta"),
    ("ERROR: [youtube] abc: Requested format is not available. Use --list-formats", "formato-no-disponible"),
    ("yt-dlp download (HLS): el corte local falló: ffmpeg código 1", "ffmpeg"),
    ("YouTube devolvió un tramo vacío (1.0-3.0 s de abc)", "tramo-vacío"),
    ("('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))", "conexión-cortada"),
    ("HTTP Error 503: Service Unavailable", "http-5xx"),
    ("Sign in to confirm you’re not a bot", "bot"),
    ("HTTP Error 429: Too Many Requests", "429"),
    ("", "sin-texto"),
])
def test_causes(message, cause):
    assert error_cause(message) == cause


def test_the_retry_logic_keeps_its_kinds():
    assert error_kind("Requested format is not available") == "unavailable"     # unchanged: logic depends on it


def test_a_tunnel_without_status_is_transient_but_a_407_is_not():
    assert tunnel_failure("unable to connect to proxy: remote end closed connection") == "sin respuesta"
    assert tunnel_failure("tunnel connection failed: 502 bad gateway") == "502"
    assert tunnel_failure("unable to connect to proxy', oserror('tunnel connection failed: 407 proxy authentication required')") is None


def test_every_failed_row_has_words_and_a_cause(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    yt.metrics_path = tmp_path / "m.jsonl"
    yt._metric("metadata", ok=False, seconds=1.0, error="other")
    yt._metric("metadata", ok=False, seconds=1.0, error="other", detail="Unable to connect to proxy: Tunnel")
    rows = [json.loads(line) for line in yt.metrics_path.read_text().splitlines()]
    assert all(r["detail"] for r in rows)
    assert [r["cause"] for r in rows] == ["sin-texto", "proxy-túnel"]
    yt.close()


def test_an_already_refused_video_is_not_a_failed_request(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY", raising=False)
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path,
                       config={"min_interval": 0, "cookies": "never", "proxy": "http://u:p@resi.rainproxy.io:1"})
    yt.metrics_path = tmp_path / "m.jsonl"
    yt._refuse("vid00000000", "sin-hls")
    with pytest.raises(Refused):
        yt.download_range("vid00000000", 1.0, 2.0, fmt="bv*[height<=720]", prefix="hd")
    assert not yt.metrics_path.exists()
    yt.close()


def test_stats_split_other_and_leave_out_old_skip_rows():
    rows = [{"action": "metadata", "ok": False, "error": "other", "detail": "Unable to connect to proxy: Tunnel"},
            {"action": "archivo hd", "ok": False, "error": "other",
             "detail": "yt-dlp download: abc descartado (sin HLS y entero supera el tope); se pasa al siguiente"},
            {"action": "metadata", "ok": True}]
    s = ytstats.summary(rows)
    assert s["failed"] == 1 and s["skipped"] == 1 and s["causes"] == {"proxy-túnel": 1}
    assert any("Causas" in line for line in ytstats.lines(s))
