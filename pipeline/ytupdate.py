"""Keep up with YouTube without updating yt-dlp blindly (fase 1.9).

The queue updates yt-dlp before every round (`pip install -U "yt-dlp[default]"`): YouTube changes and yt-dlp
follows, but a new release can also break what worked. Here, when the update changes the version:

1. the probe of `--probar-youtube` (pipeline/ytcheck.py: 10 s of a public video, the way the pipeline downloads,
   in a child process with a time limit) runs with the new one;
2. if it fails, the previous version is installed again and probed: if that one works, it stays, the new one is
   remembered as bad in out/_ytdlp.json (not tried again until a newer release) and a notice says so; if the old one
   fails too, the trouble is YouTube or the connection, not the release: the new one is kept.

`youtube_update_probe: false` (sourcing.youtube) skips the probe: one download of ~2 MB per new release.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

STATE = "out/_ytdlp.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def pip_install(*specs: str) -> bool:
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", *specs], capture_output=True, text=True,
                          timeout=300)
    return done.returncode == 0


def installed() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for name in ("yt-dlp", "yt-dlp-ejs"):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = ""
    return out


def probe_ok(root: Path) -> bool:
    """The download probe, in a child process (it imports the yt-dlp just installed)."""

    from .context import RunContext
    from .ytcheck import _try

    result = _try(RunContext.create("_ytdlp", root=root), "sonda tras actualizar yt-dlp", cookies=False, ipv4=True)
    return not result.get("error") and not result.get("timeout") and float(result.get("mb") or 0) > 0


def update(root: Path, *, install: Callable[..., bool] = pip_install, versions: Callable[[], dict[str, str]] = installed,
           probe: Callable[[Path], bool] = probe_ok, notify: Callable[[str], None] = print,
           check: bool = True) -> dict[str, Any]:
    """Update yt-dlp; returns what happened: {"from", "to", "kept", "rolledBack", "probe"}."""

    state_path = root / STATE
    state = _read(state_path)
    before = versions()
    updated = install("-U", "yt-dlp[default]")
    after = versions()
    result: dict[str, Any] = {"from": before.get("yt-dlp"), "to": after.get("yt-dlp"), "updated": updated}
    pin = [f"yt-dlp=={before['yt-dlp']}"] + ([f"yt-dlp-ejs=={before['yt-dlp-ejs']}"] if before.get("yt-dlp-ejs") else [])
    if after.get("yt-dlp") and after.get("yt-dlp") == state.get("bad") and before.get("yt-dlp") \
            and before.get("yt-dlp") != after.get("yt-dlp"):
        install(*pin)                                    # known to break here: straight back, no probe again
        result.update(kept=before.get("yt-dlp"), rolledBack=True, probe="conocida como mala")
        return result
    if not check or not before.get("yt-dlp") or before.get("yt-dlp") == after.get("yt-dlp"):
        result.update(kept=after.get("yt-dlp"), rolledBack=False, probe=None)
        return result
    if probe(root):
        state.update(good=after.get("yt-dlp"), checkedAt=time.strftime("%Y-%m-%d %H:%M"))
        state.pop("bad", None)
        result.update(kept=after.get("yt-dlp"), rolledBack=False, probe="bien")
    else:
        install(*pin)
        if probe(root):
            state.update(bad=after.get("yt-dlp"), good=before.get("yt-dlp"), checkedAt=time.strftime("%Y-%m-%d %H:%M"))
            notify(f"⚠️ yt-dlp {after.get('yt-dlp')} no descarga en este servidor (la sonda falla) y la "
                   f"{before.get('yt-dlp')} sí: vuelvo a la {before.get('yt-dlp')} hasta que salga otra versión.")
            result.update(kept=before.get("yt-dlp"), rolledBack=True, probe="falla la nueva, la anterior bien")
        else:
            install("-U", "yt-dlp[default]")              # both fail: YouTube or the connection, not the release
            result.update(kept=after.get("yt-dlp"), rolledBack=False, probe="fallan las dos (YouTube o la conexión)")
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass
    return result
