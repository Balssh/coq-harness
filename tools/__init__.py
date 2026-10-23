"""Tool framework: base class, registry, and execution.

Tools are the semantic API the model calls. The model never emits raw keys.
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


def tool_schemas() -> list[dict]:
    """Returns [{name, description, parameters}] for the system prompt."""
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in _REGISTRY.values()
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
from tools import movement, interaction, info, meta, chargen  # noqa: E402, F401

