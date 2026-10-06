"""The queue pauses itself while YouTube blocks this connection, and resumes on its own when it lets through again.

On 05-10 YouTube blocked the home connection («not a bot», 429) and every video in the queue ran into it one after
another: half-searched candidates, failed downloads, chalkboard videos, money spent for nothing. Now the first video
that meets the block raises YouTubeBlocked: the watcher writes out/_pausa_youtube, sends one Telegram message,
starts no other video, tries a 10-second download every `watch.youtube_probe_minutes` (60) and, when it works,
removes the pause, says so on Telegram and goes on with the queue.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

FLAG = "out/_pausa_youtube"


class YouTubeBlocked(RuntimeError):
    """YouTube refuses this connection (bot check, 429): the whole queue waits, not just this video."""


def paused(root: Path) -> dict[str, Any] | None:
    path = root / FLAG
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {"at": path.stat().st_mtime, "reason": "YouTube bloqueado"}


def pause(root: Path, reason: str) -> None:
    """Pause the queue (once: a second blocked video does not send another message)."""

    if paused(root):
        return
    path = root / FLAG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": time.time(), "reason": reason[:300], "checked": time.time()}), encoding="utf-8")
    _tell(root, "⛔ YouTube ha bloqueado la conexión: cola en pausa para no gastar en vídeos sin imágenes.\n"
                f"{reason[:300]}\n\nPruebo YouTube cada hora y sigo solo en cuanto deje pasar.")


def resume(root: Path) -> None:
    (root / FLAG).unlink(missing_ok=True)
    _tell(root, "✅ YouTube vuelve a dejar descargar: la cola sigue.")


def due(root: Path, minutes: float) -> bool:
    state = paused(root) or {}
    return time.time() - float(state.get("checked") or state.get("at") or 0) >= minutes * 60


def probe(root: Path) -> bool:
    """A 10-second download as the queue would make it (a child process, cut off after 90 s)."""

    from .context import RunContext
    from .sourcing import cookie_sets
    from .ytcheck import _try

    ctx = RunContext.create("_ytcheck", root=root)
    yt_cfg = ctx.section("sourcing").get("youtube", {})
    try:                         # with the account's cookies when the queue uses them, as it would download
        cookies = str(yt_cfg.get("cookies", "")).lower() != "never" and bool(cookie_sets(ctx, yt_cfg))
    except Exception:
        cookies = False
    state = paused(root) or {}
    path = root / FLAG
    if path.is_file():
        path.write_text(json.dumps({**state, "checked": time.time()}), encoding="utf-8")
    result = _try(ctx, "prueba de YouTube (cola en pausa)", cookies=cookies, ipv4=True)
    return not result.get("error") and not result.get("timeout") and float(result.get("mb") or 0) > 0


def _tell(root: Path, text: str) -> None:
    try:
        from .context import RunContext
        from .notify import telegram

        telegram(RunContext.create("_ytpause", root=root), text)
    except Exception:            # a message is never worth stopping the queue for
        pass
