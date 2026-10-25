"""Tool framework: base class, registry, screen-based filtering, and execution.

Tools are the semantic API the model calls. The model never emits raw keys
directly — it calls tools by name with arguments. The generic `press` tool
is the escape hatch for anything not covered by a dedicated tool.

Screen-based filtering: each tool declares which screens it's relevant on.
The agent only sees tools for the current screen, reducing choice overload.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import jsonschema


@dataclass
class ToolResult:
    text: str = ""
    image: bytes | None = None       # PNG bytes
    images: dict[str, bytes] = field(default_factory=dict)  # named PNG bytes
    error: bool = False


class Tool(ABC):
    name: str
    description: str
    parameters: dict                 # JSON Schema
    advances_turn: bool = False
    screens: set[str] | None = None  # None = available on all screens

    @abstractmethod
    def execute(self, **params) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())


def tools_for_screen(screen: str) -> list[Tool]:
    """Return tools relevant to the given screen.

    Tools with `screens=None` are always available.
    Tools with `screens` set are only available when the current screen
    is in that set.
    """
    return [
        t for t in _REGISTRY.values()
        if t.screens is None or screen in t.screens
    ]


def tool_schemas(screen: str | None = None) -> list[dict]:
    """Returns [{name, description, parameters}] for the system prompt.

    If screen is provided, only tools relevant to that screen are returned.
    """
    tools = tools_for_screen(screen) if screen else all_tools()
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in tools
    ]


def validate_args(tool: Tool, args: dict) -> str | None:
    """Validate args against the tool's JSON Schema. Returns error string or None."""
    try:
        jsonschema.validate(instance=args, schema=tool.parameters)
        return None
    except jsonschema.ValidationError as exc:
        return f"Invalid arguments for {tool.name}: {exc.message}"


def execute_tool(name: str, args: dict) -> ToolResult:
    """Look up, validate, and execute a tool. Never raises — errors become ToolResult."""
    tool = get_tool(name)
    if tool is None:
        return ToolResult(
            error=True,
            text=f"Unknown tool: {name!r}. Available tools: {', '.join(sorted(_REGISTRY))}",
        )
    err = validate_args(tool, args)
    if err:
        return ToolResult(error=True, text=err)
    try:
        return tool.execute(**args)
    except Exception as exc:
        return ToolResult(error=True, text=f"Tool {name!r} failed: {exc}")


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

import io

from PIL import Image


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# Import all tool modules to trigger registration
from tools import movement, interaction, info, meta, chargen, press  # noqa: E402, F401
