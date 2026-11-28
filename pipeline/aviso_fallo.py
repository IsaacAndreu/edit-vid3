"""The failure notice to the phone: what really happened in this attempt and when the next one is.

27-11: it named the stage of an earlier attempt, promised «en unas horas» when the queue retried in a minute, and the
same «❌ Falló» came for a wait (quota, budget) and for a restart. Now it says the kind of error, the stage of THIS
process (work/<vídeo>/current.json only when its pid is ours), which attempt it is (in a row and today), what the
attempt cost and how long it ran, and when the next one is (watch.retry_*, the daily cap, or «Reintentar» when no
watcher runs). Waits and restarts send nothing (main.is_failure). The same failure of the same video (its kind, stage
and first words, numbers aside) within `REPEAT_HOURS` is sent once: out/_avisos_fallo.json remembers.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any

from .context import RunContext
from .fileio import update_json

SENT = "_avisos_fallo.json"          # in out/
REPEAT_HOURS = 12


def _read(path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def stage_now(ctx: RunContext) -> str:
    current = _read(ctx.work_dir / "current.json")
    if not isinstance(current, dict) or current.get("pid") != os.getpid():
        return "antes de la primera etapa"
    return f"en la etapa {current.get('number')}/{current.get('of')} ({current.get('stage')})"


def spent_since(ctx: RunContext, started: float) -> float:
    entries = (_read(ctx.work_dir / "costs.json") or {})
    total = 0.0
    for entry in (entries.get("entries") if isinstance(entries, dict) else None) or []:
        try:
            at = datetime.fromisoformat(str(entry["at"]).replace("Z", "+00:00")).timestamp()
            if at >= started - 1:
                total += float(entry.get("usd") or 0)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return total


def _clock(seconds: float) -> str:
    return f"{seconds / 3600:.0f} h" if seconds >= 5400 else f"{max(1, round(seconds / 60)):.0f} min"


def next_try(ctx: RunContext, signature: Any, now: float) -> tuple[str, dict[str, Any]]:
    from . import reintentos

    beat = ctx.root / "out" / "_vigilar.latido"
    state = _read(ctx.root / "out" / "_vigilar.json")
    old = state.get(ctx.slug) if isinstance(state, dict) and isinstance(state.get(ctx.slug), dict) else None
    new = reintentos.record(old, signature, "ERROR", "", now)
    if not (beat.is_file() and now - beat.stat().st_mtime < 15 * 60) or (ctx.root / "out" / "_pausa").is_file():
        return "No se reintenta solo (el vigilante no está en marcha): «Reintentar» en el estudio.", new
    watch = ctx.section("watch")
    if int(new["dayFails"]) >= reintentos.day_cap(watch):
        return (f"Espera a mañana ({new['dayFails']} fallos hoy); «Reintentar» en el estudio lo suelta antes.", new)
    return f"Siguiente intento en {_clock(reintentos.wait_seconds(watch, new))}.", new


def text(ctx: RunContext, error: BaseException, *, started: float | None, signature: Any = "",
         now: float | None = None) -> str:
    now = time.time() if now is None else now
    message = str(error).strip() or type(error).__name__
    when, new = next_try(ctx, signature, now)
    attempt = f"intento {new['tries']}" + (f" ({new['dayFails']} hoy)" if int(new["dayFails"]) != int(new["tries"]) else "")
    facts = [attempt]
    if started is not None:
        facts.append(f"{_clock(now - started)} de trabajo")
        facts.append(f"{spent_since(ctx, started):.2f} $")
    return (f"❌ Falló {ctx.slug} {stage_now(ctx)}: {type(error).__name__}\n{message[:600]}\n\n"
            f"{' · '.join(facts)}\n{when}")


def first_time(ctx: RunContext, error: BaseException, stage: str, now: float | None = None) -> bool:
    """False when this video already sent this same failure within REPEAT_HOURS (it is remembered either way)."""

    now = time.time() if now is None else now
    words = re.sub(r"0x[0-9a-f]+|\d+(?:[.,]\d+)?", "#", str(error))[:120]
    key = f"{type(error).__name__}|{stage}|{words}"
    answer: list[bool] = []

    def change(sent: Any) -> Any:
        sent = sent if isinstance(sent, dict) else {}
        mine = sent.get(ctx.slug) if isinstance(sent.get(ctx.slug), dict) else {}
        again = mine.get("key") == key and now - float(mine.get("at") or 0) < REPEAT_HOURS * 3600
        answer.append(not again)
        sent[ctx.slug] = {"key": key, "at": float(mine.get("at") or now) if again else now,
                          "count": int(mine.get("count") or 1) + 1 if again else 1}
        return sent

    path = ctx.root / "out" / SENT
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        update_json(path, change, {})
    except (OSError, ValueError):
        return True
    return answer[-1] if answer else True
