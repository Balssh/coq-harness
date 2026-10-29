"""The game as the model sees it: mcp_server.py, spoken to over stdio MCP.

The harness launches the same MCP server that Vibe or Claude Code use, so the
model plays with exactly those tools. A few tools are hidden from the model
because the harness handles them (saves, loading, chargen) or they are
legacy/debug tools.
"""

import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HIDDEN_TOOLS = {
    "get_state_raw",                          # huge JSON; the harness records it
    "save_game", "continue_game", "start_new_game", "chargen_auto", "chargen_presets", "list_saves",
    "quit_to_menu", "quit_game", "abandon",   # run lifecycle is the harness's job
    "choose_option", "confirm_popup",         # duplicates of respond_popup
    "press_key", "focus_window", "look",      # legacy key injection / look mode
}


class Game:
    def __init__(self, repo_root: Path, python: str | None = None, hidden: set[str] | None = None):
        self.repo_root = repo_root
        self.python = python or sys.executable
        self.hidden = HIDDEN_TOOLS if hidden is None else hidden
        self.tools: list = []
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "Game":
        params = StdioServerParameters(command=self.python, args=[str(self.repo_root / "mcp_server.py")],
                                       cwd=str(self.repo_root))
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        self.tools = (await self._session.list_tools()).tools
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    def model_tools(self) -> list[dict]:
        """Function-calling schemas for the tools the model may use."""
        out = []
        for t in self.tools:
            if t.name in self.hidden:
                continue
            params = dict(t.input_schema or {"type": "object", "properties": {}})
            params.pop("title", None)
            props = {k: {kk: vv for kk, vv in v.items() if kk != "title"}
                     for k, v in (params.get("properties") or {}).items()}
            params["properties"] = props
            out.append({"type": "function",
                        "function": {"name": t.name, "description": t.description or "", "parameters": params}})
        return out

    def is_game_tool(self, name: str) -> bool:
        return any(t.name == name for t in self.tools) and name not in self.hidden

    async def call(self, name: str, args: dict | None = None, timeout: float = 180.0) -> tuple[str, bool]:
        """Run a tool; returns (text, is_error)."""
        assert self._session is not None
        try:
            res = await self._session.call_tool(name, args or {}, read_timeout_seconds=timeout)
        except Exception as e:  # MCP errors (bad args, timeouts) go back to the model as text
            return f"ERROR calling {name}: {e}", True
        text = "\n".join(getattr(c, "text", "") for c in res.content).strip()
        return text, bool(res.is_error)

    async def raw_state(self) -> dict:
        text, err = await self.call("get_state_raw")
        if err:
            return {"error": text}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": text[:500]}
