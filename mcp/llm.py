"""Mistral Large 4 API integration (text-only, no images)."""

import os
import time

from mistralai.client import Mistral

MODEL = "mistral-large-latest"

MAX_API_RETRIES = 5
RETRY_BASE_DELAY = 2.0

_client: Mistral | None = None


def _get_client() -> Mistral:
    global _client
    if _client is None:
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY environment variable not set")
        _client = Mistral(api_key=api_key)
    return _client


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status in (429, 500, 502, 503, 504)
    exc_name = type(exc).__name__.lower()
    return any(kw in exc_name for kw in ("timeout", "connection", "network"))


def call_llm(messages: list[dict]) -> str:
    """Call ML4, return the raw text response. Retries on transient API errors."""
    client = _get_client()
    last_exc: Exception | None = None
    for attempt in range(MAX_API_RETRIES):
        try:
            response = client.chat.complete(model=MODEL, messages=messages)
            return response.choices[0].message.content or ""
        except Exception as exc:
            last_exc = exc
            if _is_retryable(exc) and attempt < MAX_API_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[llm] API error (attempt {attempt + 1}/{MAX_API_RETRIES}): {exc}")
                print(f"[llm] Retrying in {delay:.0f}s...")
                time.sleep(delay)
            else:
                raise
    raise last_exc
