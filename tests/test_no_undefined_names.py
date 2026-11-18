"""Every name the code uses exists (pyflakes). 17-11: `official` was used in a function where it did not exist;
every video with footage failed in the «apertura» stage for a whole night and no test went through that line."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FATAL = ("undefined name", "referenced before assignment", "syntax error", "invalid syntax", "unexpected indent",
         "import * used; unable to detect undefined names")


def test_no_undefined_names_in_the_code():
    pytest.importorskip("pyflakes")
    done = subprocess.run([sys.executable, "-m", "pyflakes", "main.py", "pipeline", "scripts"], cwd=ROOT,
                          capture_output=True, text=True, timeout=300)
    bad = [line for line in (done.stdout + done.stderr).splitlines() if any(f in line for f in FATAL)]
    assert not bad, "Nombres sin definir (fallarían al ejecutarse):\n" + "\n".join(bad[:30])
