"""Text LLM calls (DeepSeek, OpenAI-compatible) with JSON output, disk cache and cost logging.

Responses are cached in cache/llm/<sha256 of request>.json, so re-running a stage after a
crash, or after a later batch failed validation, never pays twice for the same prompt.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from openai import OpenAI

from .context import RunContext
from .costs import record_cost


DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class LLMError(RuntimeError):
    pass


def _within(seconds: float, call):
    """The call, or TimeoutError after `seconds` of wall clock. The API keeps a slow request alive by sending blank
    lines, so the client's read timeout never fires: a planner call once hung for six hours."""

    import queue
    import threading

    box: "queue.Queue[tuple[bool, Any]]" = queue.Queue()

    def run() -> None:
        try:
            box.put((True, call()))
        except BaseException as error:          # handed back to the caller
            box.put((False, error))

    threading.Thread(target=run, daemon=True).start()
    try:
        ok, value = box.get(timeout=seconds)
    except queue.Empty:
        raise TimeoutError from None
    if not ok:
        raise value
    return value


def complete_json(
    ctx: RunContext,
    *,
    stage: str,
    system: str,
    user: str,
    section: str,
    max_tokens: int = 8000,
    use_cache: bool = True,
) -> dict[str, Any]:
    cfg = ctx.section(section)
    model = str(cfg.get("model", "deepseek-flash"))
    thinking = bool(cfg.get("thinking", False))
    request = {"model": model, "thinking": thinking, "system": system, "user": user, "max_tokens": max_tokens}
    key = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cache_path = ctx.cache_dir / "llm" / f"{key}.json"
    if use_cache and cache_path.is_file():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))["parsed"]
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    client = OpenAI(api_key=ctx.env("LLM_API_KEY"), base_url=str(cfg.get("base_url", DEEPSEEK_BASE_URL)),
                    timeout=120, max_retries=1)
    deadline = float(cfg.get("timeout_seconds", 420))
    response = None
    for attempt in range(int(cfg.get("deadline_retries", 2)) + 1):
        try:
            response = _within(deadline, lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}},
            ))
            break
        except TimeoutError:
            print(f"   {model} no terminó en {deadline:.0f} s (intento {attempt + 1}); repito la petición")
    if response is None:
        raise LLMError(f"{model} no respondió a tiempo ({deadline:.0f} s, varias veces): el servicio va saturado")
    usage = response.usage
    if usage is not None:
        prices = cfg.get("usd_per_mtok", {})
        cached_tokens = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
        miss_tokens = max(0, int(usage.prompt_tokens) - cached_tokens)
        usd = (
            cached_tokens * float(prices.get("input_cache_hit", 0.0))
            + miss_tokens * float(prices.get("input", 0.0))
            + int(usage.completion_tokens) * float(prices.get("output", 0.0))
        ) / 1_000_000
        record_cost(
            ctx,
            stage=stage,
            provider="deepseek",
            operation=model,
            usd=usd,
            details={"inputTokens": usage.prompt_tokens, "cachedTokens": cached_tokens, "outputTokens": usage.completion_tokens},
        )

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise LLMError(f"{model} truncó la respuesta (max_tokens={max_tokens}).")
    try:
        parsed = json.loads(choice.message.content or "")
    except json.JSONDecodeError as error:
        raise LLMError(f"{model} devolvió JSON inválido: {error}") from error
    if not isinstance(parsed, dict):
        raise LLMError(f"{model} devolvió JSON que no es un objeto.")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"request": request, "parsed": parsed}, ensure_ascii=False) + "\n", encoding="utf-8")
    return parsed
