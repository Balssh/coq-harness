"""MCP-style tools that call the in-game MCP server.

These replace the screenshot-based tools. Each tool maps directly to
a command sent to the C# mod's MCP server.
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any

from mcp.client import McpClient, McpError, get_client


@dataclass
class ToolResult:
    text: str = ""
    error: bool = False
    data: dict = field(default_factory=dict)


class Tool(ABC):
    name: str
    description: str
    parameters: dict
    advances_turn: bool = False
    screens: set[str] | None = None


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())


def tools_for_screen(screen: str) -> list[Tool]:
    return [
        t for t in _REGISTRY.values()
        if t.screens is None or screen in t.screens
    ]


def tool_schemas(screen: str | None = None) -> list[dict]:
    tools = tools_for_screen(screen) if screen else all_tools()
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in tools
    ]


def execute_tool(name: str, args: dict) -> ToolResult:
    """Execute a tool by sending a command to the MCP server."""
    tool = get_tool(name)
    if tool is None:
        return ToolResult(
            error=True,
            text=f"Unknown tool: {name!r}. Available tools: {', '.join(sorted(_REGISTRY))}",
        )

    if args is None:
        args = {}

    import jsonschema
    try:
        jsonschema.validate(args, tool.parameters)
    except jsonschema.ValidationError as exc:
        return ToolResult(
            error=True,
            text=f"Invalid arguments for '{name}': {exc.message} (at {list(exc.absolute_path)})",
        )

    try:
        client = get_client()
        result = client.send_command(tool.name, **args)

        if result.get("error"):
            return ToolResult(error=True, text=result["error"], data=result)

        ok = result.get("ok", False)
        action = result.get("action", name)

        if ok:
            return ToolResult(
                text=f"Action '{action}' completed successfully.",
                data=result,
            )
        else:
            return ToolResult(
                error=True,
                text=f"Action '{action}' did not return ok status: {result}",
                data=result,
            )

    except McpError as exc:
        return ToolResult(error=True, text=f"MCP error: {exc}")
    except Exception as exc:
        return ToolResult(error=True, text=f"Tool '{name}' failed: {exc}")


_DIRECTIONS_8 = ["up", "down", "left", "right", "up_left", "up_right", "down_left", "down_right"]
_DIRECTIONS_4 = ["up", "down", "left", "right"]
_PLAY_SCREENS = {"play"}


class MoveTool(Tool):
    name = "move"
    description = (
        "Move one tile in a direction. Bump into enemies to attack, doors to open them. "
        "Use this to explore, approach enemies, or retreat."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": _DIRECTIONS_8,
                "description": "Compass direction to move",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS


class RestTool(Tool):
    name = "wait"
    description = (
        "Wait (pass turns) to heal or let time pass. Use to recover HP, "
        "wait for NPCs, or pass time. This is also the fallback action when unsure."
    )
    parameters = {
        "type": "object",
        "properties": {
            "turns": {
                "type": "integer",
                "minimum": 1,
                "default": 1,
                "description": "Number of turns to wait",
            }
        },
    }
    advances_turn = True
    screens = _PLAY_SCREENS


class InteractTool(Tool):
    name = "interact"
    description = (
        "Interact with something in an adjacent tile. Opens a context menu "
        "with actions like: talk/chat, open, take, butcher, harvest, trade, etc. "
        "You MUST be adjacent to the target."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": _DIRECTIONS_8,
                "description": "Direction of the thing to interact with",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS


class GetTool(Tool):
    name = "get"
    description = "Pick up item(s) on your current tile."
    parameters = {"type": "object", "properties": {}}
    advances_turn = True
    screens = _PLAY_SCREENS


class UseItemTool(Tool):
    name = "use_item"
    description = (
        "Use an item from your inventory. Actions: equip (wear/wield), drop, "
        "quaff (drink), eat, unequip."
    )
    parameters = {
        "type": "object",
        "properties": {
            "item": {
                "type": "string",
                "description": "Name of the item (partial match is OK)",
            },
            "item_action": {
                "type": "string",
                "enum": ["equip", "drop", "quaff", "eat", "unequip"],
                "description": "What to do with the item",
            },
        },
        "required": ["item", "item_action"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS


class PressKeyTool(Tool):
    name = "press_key"
    description = (
        "Press a single key. Use for: dismissing '>press [Space]' prompts (key=' '), "
        "selecting a letter/number in a menu (key='1', key='a'), "
        "navigating menus with arrows (key='up', key='enter', key='escape'). "
        "Do NOT use for movement or combat - use the dedicated tools."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The key to press (e.g. ' ', 'enter', 'escape', '1', 'a')",
            }
        },
        "required": ["key"],
    }
    advances_turn = False
    screens = None


class PressCommandTool(Tool):
    name = "press_command"
    description = (
        "Send a raw Qud command by ID. Use for commands not covered by "
        "dedicated tools (e.g. 'CmdFire' to shoot, 'CmdReload', 'CmdSoar'). "
        "Set advances_turn=true if the command consumes a turn (e.g. CmdFire)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Qud command ID (e.g. 'CmdFire', 'CmdReload')",
            },
            "advances_turn": {
                "type": "boolean",
                "default": False,
                "description": "Whether this command advances the game turn",
            },
        },
        "required": ["command"],
    }
    advances_turn = False
    screens = None


class OpenScreenTool(Tool):
    name = "open_screen"
    description = (
        "Open a game screen (inventory, equipment, skills, character, "
        "quests, journal, abilities, mutations, map, factions)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "screen": {
                "type": "string",
                "enum": [
                    "inventory", "equipment", "skills", "character",
                    "quests", "journal", "abilities", "mutations",
                    "map", "factions",
                ],
                "description": "Which screen to open",
            }
        },
        "required": ["screen"],
    }
    advances_turn = False
    screens = None


class CloseMenuTool(Tool):
    name = "close_menu"
    description = "Close an open menu or dialog (Escape)."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = None


class ChooseOptionTool(Tool):
    name = "choose_option"
    description = (
        "Select a numbered option in a dialogue or menu (1-9). "
        "Use whenever you see numbered choices."
    )
    parameters = {
        "type": "object",
        "properties": {
            "option": {
                "type": "integer",
                "minimum": 1,
                "maximum": 9,
                "description": "The option number to select (1-9)",
            }
        },
        "required": ["option"],
    }
    advances_turn = False
    screens = None


class AutoExploreTool(Tool):
    name = "auto_explore"
    description = (
        "Trigger Qud's built-in auto-explore. The game moves you automatically, "
        "exploring unvisited tiles. Stops when it spots a hostile or finds "
        "something interesting. Advances MANY turns at once."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True
    screens = _PLAY_SCREENS


class TravelTool(Tool):
    name = "travel"
    description = (
        "Travel to the edge of the current zone in a cardinal direction. "
        "The game auto-pathfinds you to that edge and loads the adjacent zone. "
        "Advances many turns."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": _DIRECTIONS_4,
                "description": "Cardinal direction toward the zone edge",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS


class GoStairsTool(Tool):
    name = "go_stairs"
    description = "Take stairs up or down. You must be standing on a staircase tile."
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "'up' for <, 'down' for >",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS


class SaveTool(Tool):
    name = "save"
    description = "Save the game."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _PLAY_SCREENS


class QuitTool(Tool):
    name = "quit"
    description = "Quit to the main menu."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _PLAY_SCREENS


class AbandonTool(Tool):
    name = "abandon"
    description = (
        "Abandon the current run. Terminates the episode cleanly without dying. "
        "Use when permanently stuck or the situation is hopeless."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _PLAY_SCREENS


class LookTool(Tool):
    name = "look"
    description = "Enter look mode to inspect tiles/creatures."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _PLAY_SCREENS


class ShowLabelsTool(Tool):
    name = "show_labels"
    description = "Show item/entity labels on screen."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _PLAY_SCREENS


register(MoveTool())
register(RestTool())
register(InteractTool())
register(GetTool())
register(UseItemTool())
register(PressKeyTool())
register(PressCommandTool())
register(OpenScreenTool())
register(CloseMenuTool())
register(ChooseOptionTool())
register(AutoExploreTool())
register(TravelTool())
register(GoStairsTool())
register(SaveTool())
register(QuitTool())
register(AbandonTool())
register(LookTool())
register(ShowLabelsTool())
