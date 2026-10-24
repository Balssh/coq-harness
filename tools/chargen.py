"""Chargen tools: select, confirm, next, back.

Used during character creation. Screen-filtered to title, mode_select, and
chargen phases. No turn clock — chargen has its own flow.

Key bindings (verified in-game):
- Arrow keys: navigate options within a screen
- Enter (confirm): select the highlighted option
- Num 9 (next): proceed to the next chargen screen
- Escape (back): go back to the previous screen
"""

from game.controller import press
from tools import Tool, ToolResult, register

_CHARGEN_SCREENS = {"title", "mode_select", "chargen"}


class SelectTool(Tool):
    name = "select"
    description = (
        "Navigate a menu option in a direction (up/down/left/right). "
        "Used during character creation and title/mode screens."
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
    screens = _CHARGEN_SCREENS

    def execute(self, direction: str) -> ToolResult:
        press(direction)
        return ToolResult(text=f"Selected {direction}.")


class ConfirmTool(Tool):
    name = "confirm"
    description = (
        "Confirm the current selection (Enter). "
        "Use this to select highlighted options, accept names, "
        "and start the game from the starting-location screen."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _CHARGEN_SCREENS

    def execute(self) -> ToolResult:
        press("enter")
        return ToolResult(text="Confirmed.")


class NextTool(Tool):
    name = "next"
    description = (
        "Proceed to the next character-creation screen (Num 9). "
        "The bottom of the screen shows '[Num 9] Next' — use this to advance "
        "between screens (e.g. Attributes → Customize → Starting Location). "
        "Do NOT use this to select an option; use 'confirm' for that."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"chargen"}

    def execute(self) -> ToolResult:
        press("num_9")
        return ToolResult(text="Advanced to next screen.")


class BackTool(Tool):
    name = "back"
    description = "Go back (Escape). Used during character creation."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _CHARGEN_SCREENS

    def execute(self) -> ToolResult:
        press("escape")
        return ToolResult(text="Went back.")


register(SelectTool())
register(ConfirmTool())
register(NextTool())
register(BackTool())
