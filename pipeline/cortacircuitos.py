"""The queue's circuit breaker: stop starting videos that will fail the same way, in both queue modes.

Signs that the failures are not the videos' fault (all counted over the last `queue.breaker_window_minutes`, 180,
kept in out/_cortacircuitos.json so a new round of the watcher remembers them):
- the same bug of the program in two videos, or `queue.breaker_same_failure` (3) times in one: an exception of the
  code (NameError, AttributeError, TypeError, KeyError, IndexError…), grouped by its type and the file:line of our code
  where it happened — not by the whole error line, which carries a different video id or value each time (17-11: one
  NameError, a whole night);
- any other exception, grouped the same way, `queue.breaker_same_failure` (3) times in at least two videos, whatever
  the stage (27-11: eight videos failing alike at alternating stages never tripped it);
- `queue.breaker_same_stage` (3) failures in a row, without a success between them, in the same stage (0: off);
- a failure rate: `queue.breaker_rate` (0.8) of at least `queue.breaker_min_attempts` (6) attempts failed, even with a
  success now and then (0: off).
A cut connection or a busy API is never counted. When it trips, the count starts again from zero.

`failed()` returns why the queue should pause (main.stop_for_bug writes out/_pausa and says so), or None.
"""

from __future__ import annotations

import json
import re
import time
import traceback
from pathlib import Path
from typing import Any

from .fileio import update_json

STATE = Path("out") / "_cortacircuitos.json"
KIND = re.compile(r"^(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*(?:Error|Exception|Exit|Timeout|Expired|Failure|Failed))\b")

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


def failure_key(detail: str, lines: list[str] | None = None, error: BaseException | None = None) -> str | None:
    """Any failure by its kind and our code's place: «ValidationError en pipeline/planner.py:88», «SystemExit en
    pipeline/sourcing.py:300». None when there is no exception kind to go by."""

    if error is not None:
        frames = [f for f in traceback.extract_tb(error.__traceback__) if _ours(f.filename)]
        where = f"{_ours(frames[-1].filename)}:{frames[-1].lineno}" if frames else None
        return f"{type(error).__name__} en {where}" if where else None
    kind = where = None
    for line in reversed(lines or []):
        text = line.strip()
        if kind is None and (found := KIND.match(text)):
            kind = found.group(1)
        elif kind is not None and (frame := FRAME.search(text)) and _ours(frame.group("path")):
            where = f"{_ours(frame.group('path'))}:{frame.group('line')}"
            break
    if kind is None and (found := KIND.match((detail or "").strip())):
        kind = found.group(1)
    return f"{kind} en {where}" if kind and where else None


def stage_of(root: Path, slug: str) -> str | None:
    """The stage a video was at when it stopped (work/<slug>/current.json, kept with «ended» after a failure)."""

    try:
        return str(json.loads((root / "work" / slug / "current.json").read_text("utf-8")).get("stage") or "") or None
    except (OSError, ValueError):
        return None


class Breaker:
    def __init__(self, root: Path, same_stage: int = 3, *, same_failure: int = 3, rate: float = 0.8,
                 min_attempts: int = 6, window_minutes: float = 180) -> None:
        self.root = root
        self.same_stage = int(same_stage)
        self.same_failure = int(same_failure)
        self.rate = float(rate)
        self.min_attempts = int(min_attempts)
        self.window = float(window_minutes) * 60

    # --- the record, shared by every round -----------------------------------------------------------------------
    def _add(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        now = time.time()
        kept: list[dict[str, Any]] = []

        def change(state: Any) -> Any:
            old = state.get("events") if isinstance(state, dict) else None
            events = [e for e in (old if isinstance(old, list) else [])
                      if isinstance(e, dict) and isinstance(e.get("t"), (int, float)) and now - e["t"] < self.window]
            events = [*events, {**event, "t": now}][-500:]
            kept[:] = events
            return {"events": events}

        path = self.root / STATE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            update_json(path, change, {})
        except (OSError, ValueError) as error:          # never stops the queue: this round's memory only
            print(f"(cortacircuitos sin guardar: {type(error).__name__})")
            kept[:] = kept or [{**event, "t": now}]
        return kept

    def _reset(self) -> None:
        try:
            update_json(self.root / STATE, lambda state: {"events": []}, {})
        except (OSError, ValueError):
            pass

    # --- what the queue calls -----------------------------------------------------------------------------------
    def succeeded(self, slug: str = "") -> None:
        self._add({"slug": slug, "ok": True})

    def failed(self, slug: str, detail: str, lines: list[str] | None = None,
               error: BaseException | None = None) -> tuple[str, list[str]] | None:
        """(why, videos) when the queue should pause; None otherwise."""

        if NETWORK.search(detail or "") or (error is not None and NETWORK.search(f"{type(error).__name__}: {error}")):
            return None
        bug = bug_key(detail, lines, error)
        key = failure_key(detail, lines, error) or bug
        stage = stage_of(self.root, slug) or "?"
        events = self._add({"slug": slug, "ok": False, "key": key, "bug": bool(bug), "stage": stage})
        why = self._why(events, key, bool(bug), detail)
        if why:
            self._reset()                               # after the pause («Reanudar»), counted from zero
        return why

    def _why(self, events: list[dict[str, Any]], key: str | None, bug: bool, detail: str) -> tuple[str, list[str]] | None:
        failures = [e for e in events if e.get("ok") is False]
        if key:
            same = [e for e in failures if e.get("key") == key]
            videos = list(dict.fromkeys(str(e.get("slug") or "?") for e in same))
            if (bug and len(videos) >= 2) or (len(same) >= max(1, self.same_failure)
                                              and (bug or len(videos) >= 2)):
                return key, videos
        streak: list[dict[str, Any]] = []
        for event in reversed(events):                  # the failures since the last success, at this stage
            if event.get("ok") is not False or event.get("stage") != failures[-1].get("stage"):
                break
            streak.insert(0, event)
        stage = str(failures[-1].get("stage") or "?")
        if self.same_stage > 0 and len(streak) >= self.same_stage and stage != "?":
            videos = list(dict.fromkeys(str(e.get("slug") or "?") for e in streak))
            return f"{len(streak)} vídeos seguidos fallaron en la etapa {stage} (último: {detail.strip()[:200]})", videos
        attempts = [e for e in events if isinstance(e.get("ok"), bool)]
        if self.rate > 0 and len(attempts) >= max(1, self.min_attempts) and \
                len(failures) / len(attempts) >= self.rate:
            videos = list(dict.fromkeys(str(e.get("slug") or "?") for e in failures))
            return (f"{len(failures)} de {len(attempts)} intentos fallaron en las últimas "
                    f"{self.window / 3600:.0f} h (último: {detail.strip()[:200]})"), videos
        return None


def from_config(root: Path) -> Breaker:
    try:
        from .context import RunContext

        cfg: Any = RunContext.create("_cola", root=root).section("queue")
        return Breaker(root, int(cfg.get("breaker_same_stage", 3) or 0),
                       same_failure=int(cfg.get("breaker_same_failure", 3) or 0),
                       rate=float(cfg.get("breaker_rate", 0.8) or 0),
                       min_attempts=int(cfg.get("breaker_min_attempts", 6) or 0),
                       window_minutes=float(cfg.get("breaker_window_minutes", 180) or 180))
    except Exception:
        return Breaker(root)
