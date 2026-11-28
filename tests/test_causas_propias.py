"""The program's own summaries (in Spanish) get a cause in the request log, not «other» (36 of 80 real ones did)."""

from __future__ import annotations

import pytest

from pipeline.sourcing.youtube import error_cause, error_kind


@pytest.mark.parametrize("message, cause", [
    ("yt-dlp download: abc descartado (YouTube pide «no eres un bot»); se pasa al siguiente candidato", "rechazo-bot"),
    ("yt-dlp metadata: YouTube pide «no eres un bot» para este vídeo; se descarta", "rechazo-bot"),
    ("yt-dlp download: YouTube pide «no eres un bot» desde 3 IPs del proxy residencial; se descarta esta petición",
     "rechazo-bot"),
    ("yt-dlp download: YouTube no sirve el vídeo abc a la IP de un proxy; se descarta", "proxy-ip"),
    ("yt-dlp download: el vídeo abc no está disponible en el país del proxy; se descarta", "proxy-ip"),
    ("yt-dlp download: el vídeo necesita una cuenta (edad)", "cuenta"),
    ("yt-dlp download: abc descartado antes de analizarlo (sin HLS); se pasa al siguiente candidato", "descartado"),
    ("yt-dlp download (HLS): el proxy residencial no pudo abrir el túnel (502) en 3 sesiones; se descarta esta petición",
     "proxy-túnel"),
    ("el proxy residencial no abre el túnel (502) en varias sesiones seguidas: está caído o sin saldo", "proxy-túnel"),
    ("yt-dlp download (HLS): la sesión del proxy cambió de IP tres veces seguidas", "sesión-rotada"),
    ("yt-dlp download (HLS): segmento vacío", "tramo-vacío"),
    ("yt-dlp download (HLS): segmento incompleto (600 de 1000 bytes)", "conexión-cortada"),
    ("yt-dlp download (rango): cortado a 3000 de 9240 bytes (ChunkedEncodingError)", "conexión-cortada"),
    ("yt-dlp download (rango): llegaron 500 de 2048 bytes", "conexión-cortada"),
    ("el formato elegido no es mp4/m4a por HTTPS (itag 18, mp4, https)", "rango-sin-indice"),
    ("el tramo pediría 90 MB (> 40 MB, range_max_mb): índice demasiado grueso · itag 136", "rango-sin-indice"),
    ("«bv*[height<=360]» no pide ningún formato de solo vídeo", "rango-sin-indice"),
    ("API de YouTube: quotaExceeded", "api-youtube"),
])
def test_each_own_summary_has_its_cause(message, cause):
    assert error_cause(message) == cause


def test_the_kind_that_drives_the_retries_is_unchanged():
    # only the log's cause is new: what decides a retry or a rotation reads as before
    assert error_kind("yt-dlp download: abc descartado (YouTube pide «no eres un bot»); se pasa al siguiente candidato") \
        == "other"
