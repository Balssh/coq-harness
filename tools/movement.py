"""Movement tools: move, go_stairs, rest, auto_explore, travel, wait_until_healed.

Consolidated from 7 tools to 6. `wait` merged into `rest(turns=1)`.
`move_to_zone_edge` renamed to `travel` for brevity.
All tools are screen-filtered to 'play'.
"""

import time

from game.controller import chord, press
from tools import Tool, ToolResult, register

_DIRECTIONS = ["up", "down", "left", "right",
               "up_left", "up_right", "down_left", "down_right"]

_PLAY_SCREENS = {"play"}


class MoveTool(Tool):
    name = "move"
    description = (
        "Move one tile in a direction. The game world is a grid; you move "
        "one tile at a time. Bump into enemies to attack, doors to open them."
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
    screens = _PLAY_SCREENS

    def execute(self, direction: str) -> ToolResult:
        press(direction)
        return ToolResult(text=f"Moved {direction}.")


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

    def execute(self, direction: str) -> ToolResult:
        if direction == "up":
            press("-")
            return ToolResult(text="Went up the stairs.")
        else:
            chord(["shift", "="])
            return ToolResult(text="Went down the stairs.")


class RestTool(Tool):
    name = "rest"
    description = (
        "Rest (pass turns) to heal or wait. Rests for the given number of turns, "
        "or indefinitely if turns is omitted. Use to recover HP, wait for NPCs, "
        "or pass time. Also the fallback action when unsure."
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
    screens = _PLAY_SCREENS

    def execute(self, turns: int | None = None) -> ToolResult:
        if turns is None:
            press("num_5")
            return ToolResult(text="Resting (waiting for something to happen).")
        else:
            for _ in range(turns):
                press("num_5")
            return ToolResult(text=f"Rested for {turns} turn(s).")


class AutoExploreTool(Tool):
    name = "auto_explore"
    description = (
        "Trigger Qud's built-in auto-explore. The game moves you automatically, "
        "exploring unvisited tiles. Stops when it spots a hostile, finds something "
        "interesting, or finishes. Advances MANY turns at once — check the message "
        "log for the stop reason."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True
    screens = _PLAY_SCREENS

    def execute(self) -> ToolResult:
        press("num_0")
        return ToolResult(
            text="Triggered auto-explore. The game will explore automatically. "
                 "Check the message log for the stop reason when it finishes."
        )


class TravelTool(Tool):
    name = "travel"
    description = (
        "Travel to the edge of the current zone in a cardinal direction. "
        "The game auto-pathfinds you to that edge and loads the adjacent zone. "
        "Chain calls to walk between nearby zones (e.g. Joppa to the desert to "
        "Red Rock). Only N/S/E/W — no diagonals. Advances many turns."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down", "left", "right"],
                "description": "Cardinal direction toward the zone edge",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS

    def execute(self, direction: str) -> ToolResult:
        chord(["shift", "enter"])
        time.sleep(0.1)
        press(direction)
        return ToolResult(
            text=f"Traveling to the {direction} zone edge. "
                 "This may take many turns — the game auto-pathfinds."
        )


class WaitUntilHealedTool(Tool):
    name = "wait_until_healed"
    description = (
        "Rest until fully healed. The game stops resting when you are healed "
        "or when something interrupts you (enemy approaches, etc.). "
        "Advances many turns at once."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True
    screens = _PLAY_SCREENS

    def execute(self) -> ToolResult:
        chord(["shift", "`"])
        return ToolResult(
            text="Waiting until healed. The game will rest until HP is recovered "
                 "or something interrupts."
        )


register(MoveTool())
register(GoStairsTool())
register(RestTool())
register(AutoExploreTool())
register(TravelTool())
register(WaitUntilHealedTool())
