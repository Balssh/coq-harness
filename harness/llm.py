"""Chat-completions client for OpenAI-compatible APIs (Mistral by default).

Uses only the standard library so any provider with a /chat/completions
endpoint and function calling can be plugged in through a preset or
--base-url. Reasoning is read from Mistral's "thinking" content chunks and
from the `reasoning_content` / `reasoning` fields other providers use.
"""

import asyncio
import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

PRESETS = {
    # Mistral wants tool_choice "any" where OpenAI says "required".
    # Left to itself, mistral-large-4 skips reasoning on most steps (164 of 208 in the first live
    # run); with reasoning_effort "high" it reasons every step at a few seconds' cost.
    "mistral": {"base_url": "https://api.mistral.ai/v1", "key_env": "MISTRAL_API_KEY",
                "model": "mistral-large-4", "tool_choice": "any", "reasoning": "high"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY",
               "model": None, "tool_choice": "required"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY",
                   "model": None, "tool_choice": "required"},
}

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    raw_arguments: str


@dataclass
class Reply:
    text: str
    reasoning: str
    tool_calls: list[ToolCall]
    usage: dict
    latency: float
    finish_reason: str = ""
    error: str = ""

    def as_message(self) -> dict:
        """The assistant message to keep in the conversation (reasoning dropped)."""
        msg: dict = {"role": "assistant", "content": self.text or ""}
        if self.tool_calls:
            msg["tool_calls"] = [{"id": c.id, "type": "function",
                                  "function": {"name": c.name, "arguments": c.raw_arguments}}
                                 for c in self.tool_calls]
        return msg


def _read_env_file(path: Path, name: str) -> str | None:
    try:
        for line in path.read_text().splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return None


def find_api_key(name: str, repo_root: Path) -> str | None:
    """$NAME, else NAME= in the repo's .env, else in ~/.vibe/.env (Mistral Vibe's key file)."""
    return (os.environ.get(name)
            or _read_env_file(repo_root / ".env", name)
            or _read_env_file(Path.home() / ".vibe" / ".env", name))


def _split_content(content) -> tuple[str, str]:
    """(text, reasoning) from a string or a list of typed chunks."""
    if content is None:
        return "", ""
    if isinstance(content, str):
        return content, ""
    text, reasoning = [], []
    for chunk in content:
        if not isinstance(chunk, dict):
            continue
        kind = chunk.get("type")
        if kind == "text":
            text.append(chunk.get("text", ""))
        elif kind == "thinking":
            inner = chunk.get("thinking")
            if isinstance(inner, list):
                reasoning += [c.get("text", "") for c in inner if isinstance(c, dict)]
            elif isinstance(inner, str):
                reasoning.append(inner)
    return "".join(text).strip(), "\n".join(reasoning).strip()


@dataclass
class ChatClient:
    model: str
    base_url: str
    api_key: str
    tool_choice: str = "auto"
    temperature: float | None = None
    max_tokens: int = 4096
    extra_body: dict = field(default_factory=dict)
    timeout: float = 240.0
    max_retries: int = 6

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        delay = 2.0
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:1000]
                if e.code not in RETRY_STATUS or attempt == self.max_retries - 1:
                    raise RuntimeError(f"HTTP {e.code}: {detail}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"network error: {e}") from None
            time.sleep(delay + random.random())
            delay = min(delay * 2, 60)
        raise RuntimeError("unreachable")

    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   max_tokens: int | None = None) -> Reply:
        body: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens or self.max_tokens}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = self.tool_choice
        if self.temperature is not None:
            body["temperature"] = self.temperature
        body.update(self.extra_body)
        start = time.monotonic()
        data = await asyncio.to_thread(self._post, body)
        latency = time.monotonic() - start
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text, reasoning = _split_content(msg.get("content"))
        reasoning = reasoning or msg.get("reasoning_content") or msg.get("reasoning") or ""
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") or {}
            raw = fn.get("arguments") or "{}"
            if isinstance(raw, dict):
                args, raw = raw, json.dumps(raw)
            else:
                try:
                    args = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError:
                    # Keep only a preview: a degenerate reply once filled the arguments with
                    # thousands of spaces, and the whole string stayed in the context.
                    args, raw = {"__invalid_json__": " ".join(raw.split())[:300]}, "{}"
            calls.append(ToolCall(id=c.get("id") or f"call{len(calls)}", name=fn.get("name", ""),
                                  arguments=args if isinstance(args, dict) else {}, raw_arguments=raw))
        return Reply(text=text, reasoning=reasoning, tool_calls=calls, usage=data.get("usage") or {},
                     latency=latency, finish_reason=choice.get("finish_reason") or "")


def make_client(provider: str, repo_root: Path, model: str | None = None, base_url: str | None = None,
                key_env: str | None = None, reasoning: str | None = None, **kwargs) -> ChatClient:
    """reasoning: a reasoning_effort value; None uses the preset's, "default" sends none."""
    preset = dict(PRESETS.get(provider, {"base_url": None, "key_env": "OPENAI_API_KEY",
                                         "model": None, "tool_choice": "required"}))
    base_url = base_url or preset["base_url"]
    model = model or preset["model"]
    key_env = key_env or preset["key_env"]
    if not base_url:
        raise SystemExit(f"provider {provider!r} needs --base-url")
    if not model:
        raise SystemExit(f"provider {provider!r} needs --model")
    key = find_api_key(key_env, repo_root)
    if not key:
        raise SystemExit(f"no API key: set {key_env} (environment, .env or ~/.vibe/.env)")
    reasoning = reasoning or preset.get("reasoning")
    extra = dict(kwargs.pop("extra_body", None) or {})
    if reasoning and reasoning != "default":
        extra.setdefault("reasoning_effort", reasoning)
    return ChatClient(model=model, base_url=base_url, api_key=key, tool_choice=preset["tool_choice"],
                      extra_body=extra, **kwargs)
