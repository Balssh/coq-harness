"""Interaction tools: get, drop, equip, unequip, quaff, eat, talk, trade.

Menu-based tools follow the pattern:
  1. Open the relevant screen
  2. Wait for it to render
  3. Press the slot letter
  4. Handle sub-menus (model drives follow-up via screenshot)

Keybindings are placeholders — verify in-game via Esc -> k.
"""

import time

from game.controller import press
from game.screens import close_screen, open_screen
from tools import Tool, ToolResult, register


def _wait_for_render(seconds: float = 0.3) -> None:
    """Brief pause for a menu to render after a key press."""
    time.sleep(seconds)


class GetTool(Tool):
    name = "get"
    description = (
        "Pick up item(s) on your current tile. If multiple items are present, "
        "a menu appears — look at the screenshot and select which to pick up."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True

    def execute(self) -> ToolResult:
        press("g")  # 'g' = get in Qud
        _wait_for_render()
        return ToolResult(
            text="Pressed get. If a pickup menu appeared, look at the screenshot "
                 "and select an item by calling the appropriate tool."
        )


class DropTool(Tool):
    name = "drop"
    description = (
        "Drop an item from your inventory. Opens the inventory, selects the "
        "item in the given slot letter (a-z), and drops it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slot": {
                "type": "string",
                "pattern": "^[a-z]$",
                "description": "Inventory slot letter (a-z)",
            }
        },
        "required": ["slot"],
    }
    advances_turn = True

    def execute(self, slot: str) -> ToolResult:
        open_screen("inventory")
        _wait_for_render()
        press(slot)
        _wait_for_render()
        # In Qud's inventory, 'd' drops the selected item
        press("d")
        _wait_for_render()
        press("enter")
        close_screen()
        return ToolResult(text=f"Dropped item in slot {slot}.")


class EquipTool(Tool):
    name = "equip"
    description = (
        "Equip an item from your inventory. Opens the inventory, selects the "
        "item in the given slot, and equips it. If a sub-menu appears (e.g., "
        "'Equip on which hand?'), look at the screenshot and select."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slot": {
                "type": "string",
                "pattern": "^[a-z]$",
                "description": "Inventory slot letter (a-z)",
            }
        },
        "required": ["slot"],
    }
    advances_turn = True

    def execute(self, slot: str) -> ToolResult:
        open_screen("inventory")
        _wait_for_render()
        press(slot)
        _wait_for_render()
        # In Qud's inventory, 'w' = wear/wield the selected item
        press("w")
        _wait_for_render()
        return ToolResult(
            text=f"Attempted to equip item in slot {slot}. "
                 "If a sub-menu appeared (e.g., which hand/body part), "
                 "look at the screenshot and press the appropriate key."
        )


class UnequipTool(Tool):
    name = "unequip"
    description = (
        "Unequip an item. Opens the equipment screen, selects the item in "
        "the given slot, and unequips it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slot": {
                "type": "string",
                "pattern": "^[a-z]$",
                "description": "Equipment slot letter (a-z)",
            }
        },
        "required": ["slot"],
    }
    advances_turn = True

    def execute(self, slot: str) -> ToolResult:
        open_screen("equipment")
        _wait_for_render()
        press(slot)
        _wait_for_render()
        # In Qud's equipment screen, 't' = take off
        press("t")
        _wait_for_render()
        press("enter")
        close_screen()
        return ToolResult(text=f"Unequipped item in slot {slot}.")


class QuaffTool(Tool):
    name = "quaff"
    description = (
        "Quaff (drink) a liquid from your inventory. Opens the inventory, "
        "selects the item in the given slot, and drinks it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slot": {
                "type": "string",
                "pattern": "^[a-z]$",
                "description": "Inventory slot letter (a-z)",
            }
        },
        "required": ["slot"],
    }
    advances_turn = True

    def execute(self, slot: str) -> ToolResult:
        open_screen("inventory")
        _wait_for_render()
        press(slot)
        _wait_for_render()
        # In Qud's inventory, 'q' = quaff
        press("q")
        _wait_for_render()
        close_screen()
        return ToolResult(text=f"Quaffed item in slot {slot}.")


class EatTool(Tool):
    name = "eat"
    description = (
        "Eat an item from your inventory. Opens the inventory, selects the "
        "item in the given slot, and eats it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slot": {
                "type": "string",
                "pattern": "^[a-z]$",
                "description": "Inventory slot letter (a-z)",
            }
        },
        "required": ["slot"],
    }
    advances_turn = True

    def execute(self, slot: str) -> ToolResult:
        open_screen("inventory")
        _wait_for_render()
        press(slot)
        _wait_for_render()
        # In Qud's inventory, 'e' = eat (when food is selected)
        # Note: 'e' also opens inventory, so we need to be careful.
        # Actually in the inventory screen, pressing the slot then 'e' eats.
        press("e")
        _wait_for_render()
        close_screen()
        return ToolResult(text=f"Ate item in slot {slot}.")


class TalkTool(Tool):
    name = "talk"
    description = (
        "Initiate conversation with an adjacent NPC. You must be next to "
        "a creature to talk. Dialogue choices are handled via the screenshot."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True

    def execute(self) -> ToolResult:
        # In Qud, Ctrl+d or just 'd' in some contexts initiates conversation
        # Actually, talking is done by pressing 'c' (chat) when adjacent
        press("c")
        _wait_for_render()
        return ToolResult(
            text="Initiated conversation. If a dialogue menu appeared, "
                 "look at the screenshot and select a response."
        )


class TradeTool(Tool):
    name = "trade"
    description = (
        "Initiate trade with an adjacent NPC. Starts a conversation and "
        "selects the trade option."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True

    def execute(self) -> ToolResult:
        press("c")
        _wait_for_render()
        return ToolResult(
            text="Initiated conversation for trade. If a dialogue menu appeared "
                 "with a trade option, select it."
        )


register(GetTool())
register(DropTool())
register(EquipTool())
register(UnequipTool())
register(QuaffTool())
register(EatTool())
register(TalkTool())
register(TradeTool())
