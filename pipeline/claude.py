"""Claude (Anthropic) as a second provider: script drafts (`guion.model`) and the revisor (`revisor.model`), whenever
the configured model is a `claude-…` one. Off unless you name one: every other call stays on its own provider.

A second point of view on purpose: the judge that picks the footage is OpenAI's, so a Claude revisor does not share
its blind spots. The key is ANTHROPIC_API_KEY (.env); its spending goes to the same costs log, provider «anthropic».
"""

from __future__ import annotations

import base64
import re
import time
from typing import Any

from .context import RunContext
from .costs import record_cost

DEFAULT_MODEL = "claude-opus-5-5"
# $/million tokens of the models we name; `usd_per_mtok` in the section overrides them
PRICES = {"claude-opus-5-5": {"input": 4.0, "output": 20.0, "input_cache_hit": 0.2},
          "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "input_cache_hit": 0.1},
          "claude-haiku-5-5": {"input": 0.1, "output": 0.5, "input_cache_hit": 0.01}}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeError(RuntimeError):
    pass


TRANSIENT_TYPES = {"RemoteProtocolError", "ReadError", "ReadTimeout", "WriteError", "ConnectError", "ConnectTimeout",
                   "PoolTimeout", "APIConnectionError", "APITimeoutError", "InternalServerError", "OverloadedError",
                   "ServiceUnavailableError", "RateLimitError"}
TRANSIENT_TEXT = re.compile(r"peer closed connection|incomplete chunked read|connection reset|overloaded|"
                            r"Error code: (?:429|500|502|503|504|529)\b", re.I)


def transient(error: BaseException) -> bool:
    """A failure of the connection or a busy Claude, not of the request: asking again usually works."""

    return type(error).__name__ in TRANSIENT_TYPES or bool(TRANSIENT_TEXT.search(f"{type(error).__name__}: {error}"))


def is_claude(model: str | None) -> bool:
    return str(model or "").startswith("claude-")


def cost(model: str, usage: Any, prices: dict[str, Any] | None = None) -> float:
    """Dollars of one reply, from its usage (cache reads at their own price, cache writes at 1.25× input)."""

    p = {**PRICES.get(model, PRICES[DEFAULT_MODEL]), **(prices or {})}
    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    written = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    fresh = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    return (fresh * float(p["input"]) + written * float(p["input"]) * 1.25
            + read * float(p.get("input_cache_hit", float(p["input"]) / 10)) + out * float(p["output"])) / 1e6


UNSUPPORTED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
               "pattern", "format", "minItems", "maxItems"}


def plain_schema(schema: Any) -> Any:
    """The schema without the constraints structured outputs may refuse (numeric ranges, lengths…): the judge's asks
    for a score between 0 and 1, which the prompt already says and `usable` checks."""

    if isinstance(schema, dict):
        return {k: plain_schema(v) for k, v in schema.items() if k not in UNSUPPORTED}
    if isinstance(schema, list):
        return [plain_schema(v) for v in schema]
    return schema


def image_block(jpeg: bytes) -> dict[str, Any]:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(jpeg).decode()}}


def ask(ctx: RunContext, *, stage: str, system: str, content: str | list[dict[str, Any]], cfg: dict[str, Any],
        max_tokens: int = 16000, schema: dict[str, Any] | None = None,
        client: Any = None) -> tuple[str, float]:
    """One request to Claude, streamed (long scripts never hit the HTTP timeout): (the reply's text, its dollars).
    `schema`: the reply is JSON that meets it (structured outputs). On a policy decline the API retries the same
    request on another model by itself (server-side fallbacks); a reply cut short or declined in the end raises."""

    model = str(cfg.get("model") or DEFAULT_MODEL)
    from .budget import before_paid_call

    before_paid_call(ctx)
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=ctx.env("ANTHROPIC_API_KEY"), max_retries=2)
    effort = cfg.get("effort", "high")
    # effort «none»: not sent at all (Haiku, 27-11: a model that does not take it would fail every request)
    output: dict[str, Any] = {} if str(effort).lower() in ("none", "", "false") or effort is None else {"effort": str(effort)}
    if schema is not None:
        output["format"] = {"type": "json_schema", "schema": plain_schema(schema)}
    attempts = max(1, int(cfg.get("network_retries", 3)) + 1)
    for attempt in range(attempts):
        try:
            with client.beta.messages.stream(
                model=model, max_tokens=max_tokens, betas=[FALLBACK_BETA], fallbacks="default",
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],   # the same rules
                messages=[{"role": "user", "content": content}], **({"output_config": output} if output else {}),
            ) as stream:
                reply = stream.get_final_message()
            break
        except Exception as error:
            # 27-11: «peer closed connection without sending complete message body» in the middle of a streamed
            # reply failed three videos in a row and paused the queue: a cut connection is asked again
            if attempt + 1 >= attempts or not transient(error):
                raise
            wait = float(cfg.get("network_wait_seconds", 10)) * (attempt + 1)
            print(f"   Claude: conexión cortada ({type(error).__name__}); otra vez en {wait:.0f} s")
            time.sleep(wait)
    usd = cost(str(getattr(reply, "model", model) or model), reply.usage, cfg.get("usd_per_mtok"))
    record_cost(ctx, stage=stage, provider="anthropic", operation=model, usd=usd,
                details={"inputTokens": getattr(reply.usage, "input_tokens", 0),
                         "cachedTokens": getattr(reply.usage, "cache_read_input_tokens", 0),
                         "outputTokens": getattr(reply.usage, "output_tokens", 0)})
    if reply.stop_reason == "refusal":
        raise ClaudeError(f"{model} no quiso responder ({getattr(reply.stop_details, 'category', None) or 'sin motivo'})")
    if reply.stop_reason == "max_tokens":
        raise ClaudeError(f"{model} cortó la respuesta (max_tokens={max_tokens})")
    text = "".join(block.text for block in reply.content if block.type == "text").strip()
    if not text:
        raise ClaudeError(f"{model} respondió sin texto")
    return text, usd
