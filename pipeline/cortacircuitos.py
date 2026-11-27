"""The queue's circuit breaker: stop starting videos that will fail the same way, in both queue modes.

Two signs that the failures are not the videos' fault:
- the same bug of the program in two videos: an exception of the code (NameError, AttributeError, TypeError, KeyError,
  IndexError…), grouped by its type and the file:line of our code where it happened — not by the whole error line,
  which carries a different video id or value each time (17-11: one NameError, a whole night);
- `queue.breaker_same_stage` (3) failures in a row, without a success between them, in the same stage (0: off).

`failed()` returns why the queue should pause (main.stop_for_bug writes out/_pausa and says so), or None.
"""

from __future__ import annotations

import json
import re
import traceback
from pathlib import Path
from typing import Any

BUG_TYPES = ("NameError", "AttributeError", "TypeError", "ImportError", "ModuleNotFoundError", "SyntaxError",
             "UnboundLocalError", "IndentationError", "KeyError", "IndexError", "ZeroDivisionError", "AssertionError",
             "RecursionError")
BUG = re.compile(r"\b(" + "|".join(BUG_TYPES) + r")\b")
FRAME = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
# a cut connection or a busy API is not the videos' fault nor the same failure three times: it never trips the
# breaker (27-11: three «peer closed connection» from Claude in the planner paused the whole queue for the night)
NETWORK = re.compile(r"RemoteProtocolError|peer closed connection|incomplete chunked read|ReadTimeout|ConnectTimeout|"
                     r"ConnectError|APIConnectionError|APITimeoutError|Connection reset|overloaded|"
                     r"Error code: (?:429|500|502|503|504|529)\b", re.I)


def _ours(path: str) -> str | None:
    clean = path.replace("\\", "/")
    for marker in ("/pipeline/", "/scripts/"):
        if marker in clean:
            return marker.strip("/") + "/" + clean.split(marker, 1)[1]
    if clean.endswith("/main.py") or clean == "main.py":
        return "main.py"
    return None


def bug_key(detail: str, lines: list[str] | None = None, error: BaseException | None = None) -> str | None:
    """«NameError en pipeline/apertura.py:212», or None when it is not a bug of the program."""

    if error is not None:
        kind = type(error).__name__
        if kind not in BUG_TYPES:
            return None
        frames = [f for f in traceback.extract_tb(error.__traceback__) if _ours(f.filename)]
        where = f"{_ours(frames[-1].filename)}:{frames[-1].lineno}" if frames else str(error)[:120]
        return f"{kind} en {where}"
    found = BUG.search(detail or "")
    if not found:
        return None
    where = None
    for line in reversed(lines or []):
        frame = FRAME.search(line)
        if frame and _ours(frame.group("path")):
            where = f"{_ours(frame.group('path'))}:{frame.group('line')}"
            break
    return f"{found.group(1)} en {where}" if where else detail.strip()[:300]


def stage_of(root: Path, slug: str) -> str | None:
    """The stage a video was at when it stopped (work/<slug>/current.json, kept with «ended» after a failure)."""

    try:
        return str(json.loads((root / "work" / slug / "current.json").read_text("utf-8")).get("stage") or "") or None
    except (OSError, ValueError):
        return None


class Breaker:
    def __init__(self, root: Path, same_stage: int = 3) -> None:
        self.root = root
        self.same_stage = int(same_stage)
        self.bugs: dict[str, list[str]] = {}
        self.streak: list[tuple[str, str]] = []          # (slug, stage) of the failures since the last success

    def succeeded(self) -> None:
        self.streak.clear()

    def failed(self, slug: str, detail: str, lines: list[str] | None = None,
               error: BaseException | None = None) -> tuple[str, list[str]] | None:
        """(why, videos) when the queue should pause; None otherwise."""

        if NETWORK.search(detail or "") or (error is not None and NETWORK.search(f"{type(error).__name__}: {error}")):
            return None
        key = bug_key(detail, lines, error)
        if key:
            hit = self.bugs.setdefault(key, [])
            if slug not in hit:
                hit.append(slug)
            if len(hit) >= 2:
                return key, list(hit)
        stage = stage_of(self.root, slug) or "?"
        if self.streak and self.streak[-1][1] != stage:
            self.streak.clear()
        self.streak.append((slug, stage))
        if self.same_stage > 0 and len(self.streak) >= self.same_stage and stage != "?":
            videos = [s for s, _ in self.streak]
            return f"{len(videos)} vídeos seguidos fallaron en la etapa {stage} (último: {detail.strip()[:200]})", videos
        return None


def from_config(root: Path) -> Breaker:
    try:
        from .context import RunContext

        value: Any = RunContext.create("_cola", root=root).section("queue").get("breaker_same_stage", 3)
        return Breaker(root, int(value or 0))
    except Exception:
        return Breaker(root)
