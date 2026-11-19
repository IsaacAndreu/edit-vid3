"""The gate before new code reaches the server: `git pull` only when the new code passes a quick check.

On 17-11 a `NameError` reached `main` and stopped every video with footage for a whole night. The studio, the
watcher (`--vigilar`) and `--actualizar` pull `main` on their own, so a mistake in a commit reaches production two
minutes later. Here the new commit is checked BEFORE it touches the working tree:

1. `git fetch` and look at the upstream commit (nothing on disk changes yet).
2. Export that commit to a temporary folder (`git archive`) and run there:
   - pyflakes (undefined names, syntax errors: what would fail only when a line runs), and
   - an import of `main` and of every module of `pipeline/` (what would fail when a stage starts).
3. Only when both pass, `git merge --ff-only`. When they fail, the code on disk stays as it was, the commit is
   remembered in out/_puerta.json (so the check is not repeated every 2 minutes) and the owner gets a Telegram.

A missing third-party module (a new dependency in requirements.txt that `--actualizar` will install) does not
stop the gate: it is reported as a warning.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STATE = "out/_puerta.json"
FATAL = ("undefined name", "referenced before assignment", "syntax error", "invalid syntax", "unexpected indent",
         "import * used; unable to detect undefined names", "unindent does not match", "expected an indented block")
OWN = ("main", "pipeline", "scripts")             # our code: an import error there is always a bug

# Imports every module of pipeline/ and main; prints one line per failure: «ERR <module> <kind> <message>»
_IMPORT_ALL = r"""
import importlib, pkgutil, sys, traceback
sys.path.insert(0, ".")
names = ["main"]
import pipeline
names += [m.name for m in pkgutil.walk_packages(pipeline.__path__, "pipeline.")]
for name in names:
    try:
        importlib.import_module(name)
    except BaseException as error:
        missing = getattr(error, "name", None) if isinstance(error, ModuleNotFoundError) else None
        kind = "MISSING:" + str(missing) if missing else type(error).__name__
        line = str(error).replace("\n", " ")[:300]
        print("ERR", name, kind, line, flush=True)
"""


def _git(root: Path, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout)


def pyflakes_problems(folder: Path, python: str = sys.executable) -> list[str]:
    targets = [name for name in ("main.py", "pipeline", "scripts") if (folder / name).exists()]
    try:
        done = subprocess.run([python, "-m", "pyflakes", *targets], cwd=folder, capture_output=True, text=True,
                              timeout=300)
    except (OSError, subprocess.SubprocessError) as error:
        return [f"pyflakes no se pudo ejecutar: {type(error).__name__}: {error}"]
    output = done.stdout + done.stderr
    if "No module named pyflakes" in output:
        return ["pyflakes no está instalado (pip install -r requirements.txt)"]
    return [line for line in output.splitlines() if any(f in line for f in FATAL)]


def import_problems(folder: Path, python: str = sys.executable) -> tuple[list[str], list[str]]:
    """(errors, warnings) of importing main and every module of pipeline/ from `folder`."""

    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(folder)}
    try:
        done = subprocess.run([python, "-c", _IMPORT_ALL], cwd=folder, capture_output=True, text=True, timeout=600,
                              env=env)
    except subprocess.TimeoutExpired:
        return ["importar el código tardó más de 10 min"], []
    except OSError as error:
        return [f"no se pudo importar el código: {error}"], []
    errors, warnings = [], []
    for line in done.stdout.splitlines():
        if not line.startswith("ERR "):
            continue
        _, module, kind, *rest = line.split(" ", 3)
        text = f"{module}: {kind} {' '.join(rest)}".strip()
        missing = kind.split(":", 1)[1] if kind.startswith("MISSING:") else ""
        if missing and missing.split(".")[0] not in OWN:
            warnings.append(text)          # a new dependency: --actualizar installs requirements.txt
        else:
            errors.append(text)
    if done.returncode != 0 and not errors:
        errors.append(f"la importación terminó con código {done.returncode}: {done.stderr.strip()[-400:]}")
    return errors, warnings


def check_folder(folder: Path, python: str = sys.executable) -> tuple[list[str], list[str]]:
    """The quick check: (errors, warnings). No errors → the code can be deployed.

    pyflakes missing on the machine (a server that pulled this code but has not run pip install yet) is a warning,
    never an error: otherwise the gate would refuse every new commit — including the one that installs it."""

    errors = pyflakes_problems(folder, python)
    missing = [e for e in errors if "pyflakes no está instalado" in e]
    errors = [e for e in errors if e not in missing]
    import_errors, warnings = import_problems(folder, python)
    return errors + import_errors, missing + warnings


def check_commit(root: Path, commit: str, python: str = sys.executable) -> tuple[list[str], list[str]]:
    with tempfile.TemporaryDirectory(prefix="puerta-") as tmp:
        archive = subprocess.run(["git", "archive", "--format=tar", commit], cwd=root, capture_output=True, timeout=300)
        if archive.returncode != 0:
            return [f"git archive {commit[:7]} falló: {archive.stderr.decode(errors='replace')[-300:]}"], []
        unpacked = subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, capture_output=True, timeout=300)
        if unpacked.returncode != 0:
            return [f"no se pudo descomprimir {commit[:7]}: {unpacked.stderr.decode(errors='replace')[-300:]}"], []
        return check_folder(Path(tmp), python)


def _state(root: Path) -> dict:
    try:
        return json.loads((root / STATE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(root: Path, state: dict) -> None:
    path = root / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _notify(root: Path, text: str) -> None:
    try:
        from . import notify
        from .context import RunContext

        notify.telegram(RunContext.create("_puerta", root=root), text)
    except Exception as error:            # the gate must never stop because a message could not be sent
        print(f"(aviso de la puerta no enviado: {type(error).__name__})")


def pull(root: Path, *, who: str = "", python: str = sys.executable) -> tuple[bool, str]:
    """`git pull --ff-only` through the gate. Returns (moved, message): `moved` when the code on disk changed."""

    try:
        fetched = _git(root, "fetch", "-q")
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"git fetch no se pudo: {type(error).__name__}"
    if fetched.returncode != 0:
        return False, f"git fetch no se pudo: {(fetched.stderr or fetched.stdout).strip()[-200:]}"
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    upstream = _git(root, "rev-parse", "@{u}")
    target = upstream.stdout.strip()
    if upstream.returncode != 0 or not target:
        return False, "la rama no sigue a ninguna rama remota"
    if target == head:
        return False, ""
    if _git(root, "merge-base", "--is-ancestor", head, target).returncode != 0:
        return False, "git pull --ff-only no se puede (hay commits locales o la rama remota se reescribió)"
    state = _state(root)
    if state.get("bad") == target:
        return False, f"el commit {target[:7]} no pasó la comprobación: sigo con {head[:7]}"
    started = time.monotonic()
    errors, warnings = check_commit(root, target, python)
    if errors:
        state.update({"bad": target, "checkedAt": time.strftime("%Y-%m-%d %H:%M:%S"), "errors": errors[:30]})
        _save_state(root, state)
        lines = "\n".join(errors[:12])
        message = (f"⛔ Código nuevo rechazado ({target[:7]}): no pasa la comprobación rápida. "
                   f"Sigo con {head[:7]}{f' ({who})' if who else ''}.\n{lines}")
        print(message, flush=True)
        _notify(root, message)
        return False, message
    merged = _git(root, "merge", "--ff-only", "-q", target)
    if merged.returncode != 0:
        return False, f"git merge --ff-only falló: {(merged.stderr or merged.stdout).strip()[-200:]}"
    state.pop("bad", None)
    state.update({"good": target, "checkedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "seconds": round(time.monotonic() - started, 1)})
    if warnings:
        state["warnings"] = warnings[:30]
        print("Código nuevo con dependencias aún sin instalar (python main.py --actualizar las instala):\n  "
              + "\n  ".join(warnings[:10]), flush=True)
    else:
        state.pop("warnings", None)
    _save_state(root, state)
    return True, f"{head[:7]} → {target[:7]}"


def main_cli(root: Path) -> int:
    """`python -m pipeline.puerta`: the quick check on the code on disk (what CI and a human can run)."""

    errors, warnings = check_folder(root)
    for line in warnings:
        print("aviso:", line)
    for line in errors:
        print("ERROR:", line)
    print("Comprobación rápida: " + ("FALLA" if errors else "bien"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main_cli(Path(__file__).resolve().parents[1]))
