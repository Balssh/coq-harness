"""Interaction tools: get, drop, equip, unequip, quaff, eat, talk, trade,
interact, choose_option.

Menu-based tools follow the pattern:
  1. Open the relevant screen
  2. Wait for it to render
  3. Press the slot letter
  4. Handle sub-menus (model drives follow-up via screenshot)

Keybindings verified against the Caves of Qud research brief (post-1.0).
"""

import time

from game.controller import chord, press
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


class InteractTool(Tool):
    name = "interact"
    description = (
        "Interact with something in an adjacent tile (Space + direction). "
        "Opens a context menu with actions like: talk/chat, open, take, "
        "butcher, harvest, etc. You must be adjacent to the target. "
        "After calling this, look at the screenshot — a context menu or "
        "dialogue will appear. Use choose_option to pick from numbered menus."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down", "left", "right",
                          "up_left", "up_right", "down_left", "down_right"],
                "description": "Direction of the thing to interact with",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True

    def execute(self, direction: str) -> ToolResult:
        # Space + direction = interact context menu in Qud
        press("space")
        time.sleep(0.1)
        press(direction)
        _wait_for_render()
        return ToolResult(
            text=f"Opened interaction menu toward {direction}. "
                 "Look at the screenshot for available actions."
        )


class TalkTool(Tool):
    name = "talk"
    description = (
        "Initiate conversation with an adjacent NPC via the interact menu "
        "(Space + direction). You must be next to a creature. After this, "
        "a dialogue screen appears — use choose_option to pick responses "
        "by their number."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down", "left", "right",
                          "up_left", "up_right", "down_left", "down_right"],
                "description": "Direction of the NPC to talk to",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True

    def execute(self, direction: str) -> ToolResult:
        # Open interact menu then the model picks "chat" from the context menu
        press("space")
        time.sleep(0.1)
        press(direction)
        _wait_for_render()
        return ToolResult(
            text=f"Opened interaction menu toward {direction}. "
                 "If a context menu appeared, use choose_option or send_keys "
                 "to select 'Chat' or the talk option. "
                 "If a dialogue screen appeared, use choose_option to respond."
        )


class TradeTool(Tool):
    name = "trade"
    description = (
        "Open trade with an adjacent NPC. Talks to them and selects the "
        "trade option. From an open conversation, you can also press Tab "
        "to open trade directly."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down", "left", "right",
                          "up_left", "up_right", "down_left", "down_right"],
                "description": "Direction of the NPC to trade with",
            }
        },
        "required": ["direction"],
    }
    advances_turn = True

    def execute(self, direction: str) -> ToolResult:
        press("space")
        time.sleep(0.1)
        press(direction)
        _wait_for_render()
        return ToolResult(
            text=f"Opened interaction menu toward {direction}. "
                 "Select the trade option from the context menu, or if already "
                 "in dialogue, the trade option / Tab key."
        )


class ChooseOptionTool(Tool):
    name = "choose_option"
    description = (
        "Select a numbered option in a dialogue or menu. Qud's post-1.0 UI "
        "uses digit keys for dialogue choices — press the number shown next "
        "to the option. Use this whenever you see numbered choices "
        "(dialogue responses, context menus, etc.)."
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

    def execute(self, option: int) -> ToolResult:
        press(str(option))
        _wait_for_render()
        return ToolResult(text=f"Selected option {option}.")


register(GetTool())
register(DropTool())
register(EquipTool())
register(UnequipTool())
register(QuaffTool())
register(EatTool())
register(InteractTool())
register(TalkTool())
register(TradeTool())
register(ChooseOptionTool())
