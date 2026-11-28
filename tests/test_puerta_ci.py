"""The deploy gate also catches a wrong name imported inside a function, installs a new dependency before the code
that needs it, and (deploy.require_ci, off) waits for the CI to be green."""

from __future__ import annotations

import json

from pipeline import puerta
from tests.test_puerta import _repo, git


def test_a_wrong_name_imported_inside_a_function_stays_out(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    monkeypatch.setattr(puerta, "_notify", lambda root, text: None)
    (origin / "pipeline" / "dos.py").write_text("def g():\n    from .uno import ff   # typo: f\n    return ff()\n"
                                                "def h():\n    from . import uno\n    from pipeline.uno import f\n"
                                                "    return uno, f\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-qm", "typo")
    moved, message = puerta.pull(server)
    assert not moved and "ff" in message and "dos" in message


def test_a_new_dependency_is_installed_before_the_code_arrives(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    monkeypatch.setattr(puerta, "_notify", lambda root, text: None)
    (origin / "requirements.txt").write_text("paquete-nuevo-que-no-existe\n")
    (origin / "pipeline" / "uno.py").write_text("import paquete_nuevo_que_no_existe\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-qm", "dep")
    installed = []
    monkeypatch.setattr(puerta, "install", lambda folder, python: installed.append(folder) or (False, "no existe"))
    moved, message = puerta.pull(server)
    assert installed and not moved and "no existe" in message        # the install failed: the old code stays
    assert puerta.pull(server)[0] is False                           # 2 minutes later: no new pip run
    state = json.loads((server / puerta.STATE).read_text())
    assert "bad" not in state                                        # never marked bad for a failed install
    state["installFailed"]["at"] -= 3600                             # an hour later: tried again
    (server / puerta.STATE).write_text(json.dumps(state))
    monkeypatch.setattr(puerta, "install", lambda folder, python: (True, ""))
    moved, _ = puerta.pull(server)                                   # installed now: pulled (only a warning left)
    assert moved


def test_with_require_ci_only_a_green_commit_is_deployed(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    monkeypatch.setattr(puerta, "_notify", lambda root, text: None)
    (server / "config.yaml").write_text("deploy: {require_ci: true}\n")
    (origin / "pipeline" / "uno.py").write_text("def f():\n    return 2\n")
    git(origin, "commit", "-qam", "b")
    answers = iter(["pendiente", "rojo", "verde"])
    monkeypatch.setattr(puerta, "ci_state", lambda root, sha: next(answers))
    assert puerta.pull(server)[0] is False                          # running: wait, nothing marked
    assert "bad" not in json.loads((server / puerta.STATE).read_text() or "{}")
    moved, message = puerta.pull(server)                            # red: stays out
    assert not moved and "CI" in message
    (origin / "pipeline" / "uno.py").write_text("def f():\n    return 3\n")
    git(origin, "commit", "-qam", "c")
    assert puerta.pull(server)[0] is True                           # the next one is green


def test_without_require_ci_the_ci_is_only_written_down(tmp_path, monkeypatch):
    origin, server = _repo(tmp_path)
    monkeypatch.setattr(puerta, "_notify", lambda root, text: None)
    monkeypatch.setattr(puerta, "ci_state", lambda root, sha: "rojo")
    (origin / "pipeline" / "uno.py").write_text("def f():\n    return 2\n")
    git(origin, "commit", "-qam", "b")
    assert puerta.pull(server)[0] is True                           # off by default: as before
    assert json.loads((server / puerta.STATE).read_text())["ci"] == "rojo"   # …and how often it would have waited


def test_ci_state_reads_the_check_runs_and_never_breaks(tmp_path):
    def answer(runs):
        return lambda url: {"total_count": len(runs), "check_runs": runs}

    green = [{"status": "completed", "conclusion": "success"}, {"status": "completed", "conclusion": "skipped"}]
    assert puerta.ci_state_from(answer(green)("x")) == "verde"
    assert puerta.ci_state_from(answer([{"status": "in_progress", "conclusion": None}])("x")) == "pendiente"
    assert puerta.ci_state_from(answer([{"status": "completed", "conclusion": "failure"}])("x")) == "rojo"
    assert puerta.ci_state_from({"total_count": 0, "check_runs": []}) == "pendiente"
    assert puerta.ci_state_from({"message": "API rate limit exceeded"}) == "desconocido"
    assert puerta.ci_state_from(None) == "desconocido"
