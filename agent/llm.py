"""Mistral Large 4 API integration."""

import base64
import io
import os

from mistralai.client import Mistral
from PIL import Image

MODEL = "mistral-large-latest"

_client: Mistral | None = None


def _get_client() -> Mistral:
    global _client
    if _client is None:
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY environment variable not set")
        _client = Mistral(api_key=api_key)
    return _client


def image_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def png_bytes_to_base64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def _image_content(base64_data: str) -> dict:
    return {
        "type": "image_url",
        "image_url": f"data:image/png;base64,{base64_data}",
    }


def call_llm(messages: list[dict]) -> str:
    """Call ML4, return the raw text response."""
    client = _get_client()
    response = client.chat.complete(model=MODEL, messages=messages)
    return response.choices[0].message.content or ""


def call_llm_with_images(
    messages: list[dict],
    images: dict[str, bytes],
    image_labels: dict[str, str] | None = None,
) -> str:
    """Call ML4 with images attached to the last user message.

    Args:
        messages: conversation messages (system + history + last user text)
        images: {"viewport": png_bytes, "log": png_bytes, ...}
        image_labels: optional {"viewport": "Game viewport", ...} for captions
    """
    # Build content parts for the last user message
    last = messages[-1]
    text = last["content"] if isinstance(last["content"], str) else str(last["content"])

    parts: list[dict] = [{"type": "text", "text": text}]
    for name, png_bytes in images.items():
        label = (image_labels or {}).get(name, name)
        parts.append({"type": "text", "text": f"\n[{label}]"})
        parts.append(_image_content(png_bytes_to_base64(png_bytes)))

    messages = messages[:-1] + [{"role": "user", "content": parts}]
    return call_llm(messages)
