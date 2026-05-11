"""Thin LLM client wrapper, pointed at DigitalOcean Serverless Inference.

DO exposes an OpenAI-compatible endpoint, so we keep using the `openai`
SDK as the transport. Provider can be swapped to OpenAI direct (or any
other OpenAI-compatible host) by changing `LLM_BASE_URL` and
`MODEL_ACCESS_KEY` in `.env`. Nothing else needs to change.

Single chokepoint for all chat-completion calls. Keep it dumb on purpose:
- one function, `generate(system, messages)`
- reads model + key + base URL from `settings`
- no streaming, no tool calls, no retries beyond the SDK's own
- raises on missing key rather than silently degrading

If we later want to swap providers, add caching, or instrument tokens,
this is the file to change. Nothing else should import `openai` directly.

Tokens used by chat completions are accumulated in `usage_totals` so
diagnostic scripts (e.g. smoke tests) can read totals without us having
to thread a return value through every caller. Reset with `reset_usage()`.
"""

from typing import Dict, List, Optional

from openai import OpenAI

from app.core.config import settings


# Module-level client, lazily constructed so importing this module doesn't
# fail when MODEL_ACCESS_KEY is unset (e.g. in tests, or when only running
# template-based agents).
_client: Optional[OpenAI] = None


# Running totals of token usage across this process. Read-only for callers.
# Embeddings are tracked separately by store.py if it ever needs to.
usage_totals: Dict[str, int] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "calls": 0,
}


def reset_usage() -> None:
    """Zero out the running token totals. Call before timed sections."""
    for k in usage_totals:
        usage_totals[k] = 0


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.MODEL_ACCESS_KEY:
            raise RuntimeError(
                "MODEL_ACCESS_KEY is not set. Add a DigitalOcean model "
                "access key to backend/.env (see .env.example). Create "
                "one at https://cloud.digitalocean.com/inference."
            )
        _client = OpenAI(
            api_key=settings.MODEL_ACCESS_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return _client


def generate(
    system: str,
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Run a single chat completion and return the assistant text.

    Args:
        system: System prompt. Goes in as the first message.
        messages: Conversation history as `[{"role": "user"|"assistant",
            "content": str}, ...]`. Do NOT include a system message here;
            pass it via `system`.
        model: Override `settings.LLM_MODEL` for this call.
        temperature: Override `settings.TEMPERATURE`.
        max_tokens: Override `settings.MAX_TOKENS`.

    Returns:
        The assistant's reply text. Stripped of leading/trailing whitespace.

    Raises:
        RuntimeError: if MODEL_ACCESS_KEY is unset.
        openai.OpenAIError: on API failures (let the caller decide how to
            handle; route handlers should catch and convert to HTTP 5xx).
    """
    client = _get_client()

    full_messages = [{"role": "system", "content": system}] + list(messages)

    resp = client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=full_messages,
        temperature=settings.TEMPERATURE if temperature is None else temperature,
        # DO docs deprecate `max_tokens` in favor of `max_completion_tokens`
        # but the OpenAI SDK still accepts and forwards `max_tokens`
        # without warnings, and DO accepts both. Keeping the simpler name
        # for now; revisit if the SDK starts warning.
        max_tokens=settings.MAX_TOKENS if max_tokens is None else max_tokens,
    )

    usage = getattr(resp, "usage", None)
    if usage is not None:
        usage_totals["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        usage_totals["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
        usage_totals["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
    usage_totals["calls"] += 1

    content = resp.choices[0].message.content or ""
    return content.strip()
