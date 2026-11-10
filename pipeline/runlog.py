"""Console + file logging for a pipeline run.

The console stays terse (what the operator needs to follow the run); the
optional log file keeps every detail, including the original error text from
yt-dlp, ffmpeg and the HTTP APIs.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


LOGGER_NAME = "edit_vid3"
log = logging.getLogger(LOGGER_NAME)

_CONSOLE_HANDLER_NAME = "edit-vid3-console"
_FILE_HANDLER_NAME = "edit-vid3-file"


def configure(log_path: Path | None = None, *, verbose: bool = False) -> None:
    """(Re)configure handlers. Safe to call more than once per process."""

    for handler in list(log.handlers):
        if handler.get_name() in {_CONSOLE_HANDLER_NAME, _FILE_HANDLER_NAME}:
            log.removeHandler(handler)
            handler.close()

    log.setLevel(logging.DEBUG)
    log.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.set_name(_CONSOLE_HANDLER_NAME)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(console)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.set_name(_FILE_HANDLER_NAME)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(message)s")
        )
        log.addHandler(file_handler)


def short_error(error: BaseException, *, limit: int = 300) -> str:
    """One-line, bounded description of an exception for operator messages."""

    text = " ".join(str(error).split())
    if not text:
        return type(error).__name__
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return f"{type(error).__name__}: {text}"
