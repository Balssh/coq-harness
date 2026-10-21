"""Movement tools: move, rest, go_stairs, auto_explore, wait."""

import time

from game.controller import press
from tools import Tool, ToolResult, register

_DIRECTIONS = ["up", "down", "left", "right",
               "up_left", "up_right", "down_left", "down_right"]


class MoveTool(Tool):
    name = "move"
    description = (
        "Move one tile in a direction. The game world is a grid; you move "
        "one tile at a time. Use this to explore, approach enemies, or retreat."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": _DIRECTIONS,
                "description": "Compass direction to move",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True

    def execute(self, direction: str) -> ToolResult:
        press(direction)
        return ToolResult(text=f"Moved {direction}.")


class RestTool(Tool):
    name = "rest"
    description = (
        "Rest (pass turns) to heal or wait. If turns is omitted, rest until "
        "something happens (e.g., an enemy approaches)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "turns": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of turns to rest. Omit to rest indefinitely.",
            }
        },
    }
    advances_turn = True

    def execute(self, turns: int | None = None) -> ToolResult:
        # In Qud, '.' is the wait/rest key
        if turns is None:
            press(".")
            return ToolResult(text="Resting (waiting for something to happen).")
        else:
            for _ in range(turns):
                press(".")
            return ToolResult(text=f"Rested for {turns} turn(s).")


class GoStairsTool(Tool):
    name = "go_stairs"
    description = (
        "Take stairs up or down. You must be standing on a staircase tile."
    )
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

    def execute(self, direction: str) -> ToolResult:
        # In Qud, '<' and '>' take stairs
        key = "<" if direction == "up" else ">"
        press(key)
        return ToolResult(text=f"Went {direction} the stairs.")


class WaitTool(Tool):
    name = "wait"
    description = (
        "Do nothing, pass one turn. Use to wait for NPCs, enemies, or other "
        "events. Also the fallback action when unsure what to do."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True

    def execute(self) -> ToolResult:
        press(".")
        return ToolResult(text="Waited one turn.")


class AutoExploreTool(Tool):
    name = "auto_explore"
    description = (
        "Automatically explore the current level. The harness will move you "
        "to unexplored adjacent tiles until none remain or you are interrupted. "
        "Use when you want to systematically discover the area."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True

    def execute(self) -> ToolResult:
        # Harness-side exploration loop.
        # For now, a simple implementation: move in a spiral-ish pattern.
        # A more sophisticated version would track visited tiles via screenshots.
        # This is a placeholder that does a basic sweep.
        from client.bridge_client import get_client
        client = get_client()

        # Simple sweep: try each direction, wait for change, continue
        # This is intentionally simple — the model can interrupt by calling
        # another tool on the next turn.
        pattern = ["up", "right", "down", "left"] * 3  # rough sweep
        moved = 0
        for direction in pattern:
            press(direction)
            changed = client.wait_for_change(timeout=2.0)
            if changed:
                moved += 1
            # If no change, we probably hit a wall — try next direction
        return ToolResult(text=f"Auto-explored: moved {moved} tiles in a sweep pattern.")


register(MoveTool())
register(RestTool())
register(GoStairsTool())
register(WaitTool())
register(AutoExploreTool())
