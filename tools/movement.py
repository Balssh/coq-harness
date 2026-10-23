"""Movement tools: move, rest, go_stairs, auto_explore, wait,
wait_until_healed, move_to_zone_edge."""

import time

from game.controller import chord, press
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
        # In Qud: '-' goes up (<), '+' (shift+=) goes down (>)
        if direction == "up":
            press("-")
            return ToolResult(text="Went up the stairs.")
        else:
            from game.controller import chord
            chord(["shift", "="])
            return ToolResult(text="Went down the stairs.")


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
        "Trigger Qud's built-in auto-explore (bound key). The game moves you "
        "automatically, exploring unvisited tiles. Auto-explore stops when it "
        "spots a hostile, finds something interesting, or finishes. It advances "
        "MANY turns at once — the message log will show why it stopped "
        "(e.g. 'Autoexplore interrupted: hostile spotted'). Use this to "
        "systematically clear a level instead of moving tile by tile."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True

    def execute(self) -> ToolResult:
        # Qud's auto-explore is bound to a key the player sets; the default
        # binding in modern Qud is typically 'e' but is remappable. We send
        # the explore command via the game's autoact system.
        # The exact key varies — this sends the most common default.
        # TODO: verify in-game and update. Common defaults: 'e' or a function key.
        press("e")
        return ToolResult(
            text="Triggered auto-explore. The game will explore automatically. "
                 "Check the message log for the stop reason when it finishes."
        )


class WaitUntilHealedTool(Tool):
    name = "wait_until_healed"
    description = (
        "Rest until fully healed (or nearly so). Uses Qud's 'wait until healed' "
        "command (~ key). Advances many turns at once. The game stops resting "
        "when you are healed or when something interrupts you (enemy approaches, "
        "etc.). Use this to recover HP safely between fights."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True

    def execute(self) -> ToolResult:
        # '~' is shift+` (backtick) in Qud = wait until healed
        chord(["shift", "`"])
        return ToolResult(
            text="Waiting until healed. The game will rest until HP is recovered "
                 "or something interrupts."
        )


class MoveToZoneEdgeTool(Tool):
    name = "move_to_zone_edge"
    description = (
        "Travel to the edge of the current zone in a cardinal direction. "
        "Uses Shift+Enter + direction — the game auto-pathfinds you to that "
        "edge and loads the adjacent zone. This is the overland travel "
        "primitive: chain calls to walk between nearby zones (e.g. Joppa to "
        "the desert to Red Rock). Only N/S/E/W — no diagonals."
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

    def execute(self, direction: str) -> ToolResult:
        # Shift+Enter + direction = travel to zone edge
        chord(["shift", "enter"])
        time.sleep(0.1)
        press(direction)
        return ToolResult(
            text=f"Traveling to the {direction} zone edge. "
                 "This may take many turns — the game auto-pathfinds."
        )


register(MoveTool())
register(RestTool())
register(GoStairsTool())
register(WaitTool())
register(AutoExploreTool())
register(WaitUntilHealedTool())
register(MoveToZoneEdgeTool())
