"""A partner cannot start paid work without end, nor hand options to the command line, nor fill the disk."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from pipeline import limites, web
from tests.test_socios import studio  # noqa: F401  (fixture)


class Running:
    """A job that never ends while the test looks (poll() is None) — like a slow apertura."""

    started: list[list[str]] = []

    def __init__(self, argv, **_kwargs):
        Running.started.append(argv)

    def poll(self):
        return None


@pytest.fixture
def jobs():
    Running.started = []
    web._JOBS.clear()
    with patch("pipeline.web.subprocess.Popen", Running):
        yield Running.started
    web._JOBS.clear()


APERTURA = {"channel": "atletismo", "title": "t", "script": "s", "url": "https://www.youtube.com/watch?v=abcdefghijk"}


def test_one_job_of_each_kind_at_a_time_per_partner(studio, jobs):  # noqa: F811
    root, call, login = studio
    assert login("contraseña-amigo") == 200
    codes = [call("/api/apertura", APERTURA)[0] for _ in range(6)]
    assert codes[0] == 200 and set(codes[1:]) == {429} and len(jobs) == 1
    login("clave")                                       # the owner: no limit of their own
    assert call("/api/apertura", {**APERTURA, "channel": "aviacion"})[0] == 200 and len(jobs) == 2


def test_a_daily_most_per_partner(studio, jobs, tmp_path):  # noqa: F811
    root, call, login = studio
    (root / "config.yaml").write_text((root / "config.yaml").read_text() + "\nsocios:\n  trabajos_dia: 2\n")
    login("contraseña-amigo")
    assert call("/api/apertura", APERTURA)[0] == 200
    web._JOBS.clear()                                    # the first one ended
    assert call("/api/apertura", APERTURA)[0] == 200
    web._JOBS.clear()
    code, body, _ = call("/api/apertura", APERTURA)
    assert code == 429 and "máximo" in json.loads(body)["error"] and len(jobs) == 2
    # a broken day's count (half written by a process that died) never blocks nor crashes
    (root / limites.LEDGER).write_text('{"amigo": {"day": 7, "jobs": "x"}, "otro": []}')
    assert call("/api/apertura", APERTURA)[0] == 200


def test_values_never_become_options(studio, jobs):  # noqa: F811
    root, call, login = studio
    (root / "out" / "suyo1" / "fotogramas").mkdir()
    login("contraseña-amigo")
    code, _, _ = call("/api/video/suyo1/miniatura-ia", {"refs": "--slug=mio1 -x https://youtu.be/abcdefghijk",
                                                        "text": "--force=all", "count": 1})
    assert code == 200
    argv = jobs[-1][2:]
    assert "--slug=mio1" not in argv and "-x" not in argv
    assert "--ref=abcdefghijk" in argv and "--texto=--force=all" in argv
    for arg in argv:
        assert arg.startswith("--")
    with pytest.raises(ValueError):
        limites.check_args(["--slug", "-x"])
    with pytest.raises(ValueError):
        web.background(root, "x", ["--slug", "mio1"])      # a value on its own: refused before anything runs
    assert not any("mio1" in a for argv in jobs for a in argv)
    with pytest.raises(ValueError):
        web.find_video(root, "-x")                          # nor a name that reads as an option


def test_a_partners_disk_has_a_quota(studio, jobs):  # noqa: F811
    root, call, login = studio
    (root / "config.yaml").write_text((root / "config.yaml").read_text() + "\nsocios:\n  disco_gb: 0.000001\n")
    login("contraseña-amigo")
    assert 0 < limites.disk_used(root, "amigo", ["atletismo"]) < 1000
    code, body, _ = call("/api/video/suyo1/voz", {"padding": "x" * 2000})      # ~1 KB of quota, 2 KB sent
    assert code == 413 and "espacio" in json.loads(body)["error"]
    login("clave")                                       # the owner: no quota (the upload goes on and fails later)
    assert call("/api/video/suyo1/voz", {"padding": "x" * 2000})[0] != 413
