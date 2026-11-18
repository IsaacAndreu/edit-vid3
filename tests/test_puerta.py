"""The gate before a deploy (pipeline/puerta.py): new code that would fail on the server never reaches the disk."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pipeline import puerta


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, capture_output=True,
                          text=True, check=True)
    return done.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "pipeline").mkdir()
    (origin / "pipeline" / "__init__.py").write_text("")
    (origin / "pipeline" / "uno.py").write_text("def f():\n    return 1\n")
    (origin / "main.py").write_text("import pipeline.uno\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "a")
    server = tmp_path / "server"
    git(tmp_path, "clone", "-q", str(origin), str(server))
    return origin, server


def test_good_code_is_pulled(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    monkeypatch.setattr(puerta, "_notify", lambda root, text: None)
    (origin / "pipeline" / "uno.py").write_text("def f():\n    return 2\n")
    git(origin, "commit", "-qam", "b")
    moved, _ = puerta.pull(server)
    assert moved and git(server, "rev-parse", "HEAD") == git(origin, "rev-parse", "HEAD")
    assert json.loads((server / puerta.STATE).read_text())["good"] == git(origin, "rev-parse", "HEAD")


def test_undefined_name_stays_out_and_is_reported_once(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    sent = []
    monkeypatch.setattr(puerta, "_notify", lambda root, text: sent.append(text))
    before = git(server, "rev-parse", "HEAD")
    (origin / "pipeline" / "uno.py").write_text("def f():\n    return official\n")     # the 17-11 NameError
    git(origin, "commit", "-qam", "bad")
    moved, message = puerta.pull(server)
    assert not moved and "official" in message
    assert git(server, "rev-parse", "HEAD") == before
    assert (server / "pipeline" / "uno.py").read_text() == "def f():\n    return 1\n"     # disk untouched
    assert len(sent) == 1
    moved, _ = puerta.pull(server)                       # 2 minutes later: no new check, no new message
    assert not moved and len(sent) == 1
    (origin / "pipeline" / "uno.py").write_text("official = 3\ndef f():\n    return official\n")
    git(origin, "commit", "-qam", "fix")
    moved, _ = puerta.pull(server)                       # the fix arrives: pulled
    assert moved and "bad" not in json.loads((server / puerta.STATE).read_text())


def test_an_import_error_of_our_own_code_stays_out(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    monkeypatch.setattr(puerta, "_notify", lambda root, text: None)
    (origin / "pipeline" / "dos.py").write_text("from .uno import g\n")      # pyflakes cannot see this one
    git(origin, "add", "-A")
    git(origin, "commit", "-qm", "bad import")
    moved, message = puerta.pull(server)
    assert not moved and "pipeline.dos" in message


def test_a_new_third_party_dependency_is_only_a_warning(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    monkeypatch.setattr(puerta, "_notify", lambda root, text: None)
    (origin / "pipeline" / "dos.py").write_text("import paquete_que_no_existe_aun\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-qm", "new dep")
    moved, _ = puerta.pull(server)
    assert moved
    assert "paquete_que_no_existe_aun" in json.loads((server / puerta.STATE).read_text())["warnings"][0]


def test_the_real_code_passes_the_quick_check():
    errors, _ = puerta.check_folder(Path(__file__).resolve().parents[1])
    assert not errors, "\n".join(errors)
