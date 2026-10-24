"""Info tools: open_screen, read_log, read_stats, look, show_labels.

Consolidated from 11 tools to 5:
- character_sheet, inventory, skills, quests, journal, abilities, mutations
  → open_screen(screen) — one tool, enum parameter
- read_log, read_stats — kept separate (different regions, no screen change)
- look → look (kept, enters look mode)
- alt_overlay → show_labels (renamed for clarity)
"""

import time

from game.controller import chord, hold, press, release
from game.screens import close_screen, open_screen as _open_screen
from perception.capture import capture_region
from tools import Tool, ToolResult, image_to_png_bytes, register


def _wait_for_render(seconds: float = 0.3) -> None:
    time.sleep(seconds)


_INFO_SCREENS = {"play", "menu"}


class OpenScreenTool(Tool):
    name = "open_screen"
    description = (
        "Open a game screen (inventory, equipment, skills, character sheet, "
        "quests, journal, abilities, mutations) and return a screenshot of it. "
        "Use this to read your items, stats, quests, or abilities. "
        "Close the screen with press(['escape']) when done."
    )
    parameters = {
        "type": "object",
        "properties": {
            "screen": {
                "type": "string",
                "enum": [
                    "inventory", "equipment", "skills", "character",
                    "quests", "journal", "abilities", "mutations",
                ],
                "description": "Which screen to open",
            }
        },
        "required": ["screen"],
    }
    advances_turn = False
    screens = _INFO_SCREENS

    def execute(self, screen: str) -> ToolResult:
        _open_screen(screen)
        _wait_for_render()
        img = capture_region("viewport")
        return ToolResult(
            text=f"Opened {screen} screen. Read the screenshot. "
                 "Close with press(['escape']) when done.",
            image=image_to_png_bytes(img),
        )


class ReadLogTool(Tool):
    name = "read_log"
    description = (
        "Read the message log at full resolution. Returns a screenshot of "
        "the recent message log. Use to check combat results, item pickups, "
        "quest updates, etc."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _INFO_SCREENS

    def execute(self) -> ToolResult:
        img = capture_region("log")
        return ToolResult(image=image_to_png_bytes(img))


class ReadStatsTool(Tool):
    name = "read_stats"
    description = (
        "Read the stats bar and abilities bar. Returns screenshots of both. "
        "Use when you need fresh HP, hunger, level, or ability info."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = _INFO_SCREENS

    def execute(self) -> ToolResult:
        stats_img = capture_region("stats")
        abilities_img = capture_region("abilities")
        return ToolResult(
            images={
                "stats": image_to_png_bytes(stats_img),
                "abilities": image_to_png_bytes(abilities_img),
            }
        )


class LookTool(Tool):
    name = "look"
    description = (
        "Enter look mode. Returns a screenshot of the viewport. In look mode, "
        "use move() to move the cursor and inspect tiles. The description "
        "of the tile under the cursor appears in the message log. "
        "Press escape to exit look mode."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"play"}

    def execute(self) -> ToolResult:
        chord(["shift", "l"])
        _wait_for_render()
        img = capture_region("viewport")
        return ToolResult(
            text="Entered look mode. Use move() to move the cursor. "
                 "Press escape to exit look mode.",
            image=image_to_png_bytes(img),
        )


class ShowLabelsTool(Tool):
    name = "show_labels"
    description = (
        "Show item/entity labels (hold Alt). Returns a screenshot with "
        "labels visible. Useful for identifying items on the ground or "
        "NPCs in the viewport."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"play"}

    def execute(self) -> ToolResult:
        hold("alt")
        _wait_for_render(0.2)
        img = capture_region("viewport")
        release("alt")
        return ToolResult(image=image_to_png_bytes(img))


register(OpenScreenTool())
register(ReadLogTool())
register(ReadStatsTool())
register(LookTool())
register(ShowLabelsTool())
