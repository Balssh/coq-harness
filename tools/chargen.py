"""Chargen tools: select, confirm, back, name_random.

Used during character creation. No turn clock — chargen has its own flow.
"""

from game.controller import press
from tools import Tool, ToolResult, register


class SelectTool(Tool):
    name = "select"
    description = (
        "Navigate a menu option in a direction (up/down/left/right). "
        "Used during character creation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down", "left", "right"],
            }
        },
        "required": ["direction"],
    }
    advances_turn = False

    def execute(self, direction: str) -> ToolResult:
        press(direction)
        return ToolResult(text=f"Selected {direction}.")


class ConfirmTool(Tool):
    name = "confirm"
    description = "Confirm the current selection (Enter). Used during character creation."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        press("enter")
        return ToolResult(text="Confirmed.")


class BackTool(Tool):
    name = "back"
    description = "Go back (Escape). Used during character creation."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        press("escape")
        return ToolResult(text="Went back.")


class NameRandomTool(Tool):
    name = "name_random"
    description = (
        "Accept a randomly generated character name. No typing needed. "
        "Used at the end of character creation."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        # In Qud chargen, there's usually a "random name" button or you just
        # press Enter/tab to accept the random name
        press("tab")
        return ToolResult(text="Accepted random name.")


register(SelectTool())
register(ConfirmTool())
register(BackTool())
register(NameRandomTool())
