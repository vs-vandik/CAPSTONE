"""Thin OpenAI client wrapper.

Single chokepoint for all model calls. Keep it dumb on purpose:
- one function, `generate(system, messages)`
- reads model + key from `settings`
- no streaming, no tool calls, no retries beyond the SDK's own
- raises on missing key rather than silently degrading

If we later want to support Anthropic, swap providers, or add caching,
this is the file to change. Nothing else should import `openai` directly.
"""

from typing import List, Dict, Optional

from openai import OpenAI

from app.core.config import settings


# Module-level client, lazily constructed so importing this module doesn't
# fail when OPENAI_API_KEY is unset (e.g. in tests, or when only running
# template-based agents).
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to backend/.env "
                "(see .env.example)."
            )
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
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
        RuntimeError: if OPENAI_API_KEY is unset.
        openai.OpenAIError: on API failures (let the caller decide how to
            handle; route handlers should catch and convert to HTTP 5xx).
    """
    client = _get_client()

    full_messages = [{"role": "system", "content": system}] + list(messages)

    resp = client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=full_messages,
        temperature=settings.TEMPERATURE if temperature is None else temperature,
        max_tokens=settings.MAX_TOKENS if max_tokens is None else max_tokens,
    )

    content = resp.choices[0].message.content or ""
    return content.strip()
