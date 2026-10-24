"""Interaction tools: get, use_item, interact, choose_option.

Consolidated from 10 tools to 4:
- drop, equip, unequip, quaff, eat → use_item(slot, action)
- talk, trade, interact → interact(direction, action?)
- get → kept (simple, high-frequency)
- choose_option → kept (dialogue/menus)
"""

import time

from game.controller import chord, press
from game.screens import close_screen, open_screen
from tools import Tool, ToolResult, register


def _wait_for_render(seconds: float = 0.3) -> None:
    time.sleep(seconds)


_PLAY_SCREENS = {"play"}
_MENU_SCREENS = {"play", "menu", "dialogue", "trade"}


class GetTool(Tool):
    name = "get"
    description = (
        "Pick up item(s) on your current tile. If multiple items are present, "
        "a menu appears — look at the screenshot and select which to pick up."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = True
    screens = _PLAY_SCREENS

    def execute(self) -> ToolResult:
        press("g")
        _wait_for_render()
        return ToolResult(
            text="Pressed get. If a pickup menu appeared, look at the screenshot "
                 "and select an item."
        )


class UseItemTool(Tool):
    name = "use_item"
    description = (
        "Use an item from your inventory. Opens the inventory, selects the "
        "item in the given slot, and performs the action. For 'unequip', "
        "opens the equipment screen instead. If a sub-menu appears "
        "(e.g. 'Equip on which hand?'), look at the screenshot and press "
        "the appropriate key with press()."
    )
    parameters = {
        "type": "object",
        "properties": {
            "slot": {
                "type": "string",
                "pattern": "^[a-z]$",
                "description": "Inventory slot letter (a-z)",
            },
            "action": {
                "type": "string",
                "enum": ["equip", "drop", "quaff", "eat", "unequip"],
                "description": (
                    "What to do with the item: "
                    "equip (wear/wield), drop, quaff (drink), eat, unequip"
                ),
            },
        },
        "required": ["slot", "action"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS

    def execute(self, slot: str, action: str) -> ToolResult:
        if action == "unequip":
            open_screen("equipment")
            _wait_for_render()
            press(slot)
            _wait_for_render()
            press("t")  # take off in equipment screen
            _wait_for_render()
            press("enter")
            close_screen()
            return ToolResult(text=f"Unequipped item in slot {slot}.")

        open_screen("inventory")
        _wait_for_render()
        press(slot)
        _wait_for_render()

        key_map = {
            "equip": "w",   # wear/wield
            "drop": "d",    # drop
            "quaff": "q",   # quaff
            "eat": "e",     # eat
        }
        key = key_map[action]
        press(key)
        _wait_for_render()

        if action == "drop":
            press("enter")
            close_screen()

        return ToolResult(
            text=f"{action.capitalize()}ed item in slot {slot}. "
                 "If a sub-menu appeared, look at the screenshot and respond."
        )


class InteractTool(Tool):
    name = "interact"
    description = (
        "Interact with something in an adjacent tile (Space + direction). "
        "Opens a context menu with actions like: talk/chat, open, take, "
        "butcher, harvest, trade, etc. You must be adjacent to the target. "
        "After calling this, look at the screenshot — a context menu or "
        "dialogue will appear. Use choose_option or press() to navigate."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down", "left", "right",
                          "up_left", "up_right", "down_left", "down_right"],
                "description": "Direction of the thing to interact with",
            },
        },
        "required": ["direction"],
    }
    advances_turn = True
    screens = _PLAY_SCREENS

    def execute(self, direction: str) -> ToolResult:
        press("space")
        time.sleep(0.1)
        press(direction)
        _wait_for_render()
        return ToolResult(
            text=f"Opened interaction menu toward {direction}. "
                 "Look at the screenshot for available actions."
        )


class ChooseOptionTool(Tool):
    name = "choose_option"
    description = (
        "Select a numbered option in a dialogue or menu. Qud's UI uses "
        "digit keys for choices — press the number shown next to the option. "
        "Use this whenever you see numbered choices (dialogue responses, "
        "context menus, etc.)."
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
    screens = _MENU_SCREENS

    def execute(self, option: int) -> ToolResult:
        press(str(option))
        _wait_for_render()
        return ToolResult(text=f"Selected option {option}.")


register(GetTool())
register(UseItemTool())
register(InteractTool())
register(ChooseOptionTool())
