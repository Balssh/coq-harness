"""Info tools: character_sheet, inventory, skills, quests, read_log,
read_stats, look, alt_overlay.

These return cropped screenshots for the model to read. No turn advance.
"""

import time

from game.controller import chord, hold, press, release
from game.screens import close_screen, open_screen
from perception.capture import capture_region
from tools import Tool, ToolResult, image_to_png_bytes, register


def _wait_for_render(seconds: float = 0.3) -> None:
    time.sleep(seconds)


class CharacterSheetTool(Tool):
    name = "character_sheet"
    description = "Open the character sheet and return a screenshot of it."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        open_screen("character")
        _wait_for_render()
        img = capture_region("viewport")
        close_screen()
        return ToolResult(image=image_to_png_bytes(img))


class InventoryTool(Tool):
    name = "inventory"
    description = "Open the inventory and return a screenshot of it."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        open_screen("inventory")
        _wait_for_render()
        img = capture_region("viewport")
        close_screen()
        return ToolResult(image=image_to_png_bytes(img))


class SkillsTool(Tool):
    name = "skills"
    description = "Open the skills/abilities screen and return a screenshot."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        open_screen("skills")
        _wait_for_render()
        img = capture_region("viewport")
        close_screen()
        return ToolResult(image=image_to_png_bytes(img))


class QuestsTool(Tool):
    name = "quests"
    description = "Open the journal/quests screen and return a screenshot."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        open_screen("quests")
        _wait_for_render()
        img = capture_region("viewport")
        close_screen()
        return ToolResult(image=image_to_png_bytes(img))


class ReadLogTool(Tool):
    name = "read_log"
    description = (
        "Read the message log at full resolution. Returns a screenshot of "
        "the recent message log."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        img = capture_region("log")
        return ToolResult(image=image_to_png_bytes(img))


class ReadStatsTool(Tool):
    name = "read_stats"
    description = (
        "Read the stats bar and abilities bar. Returns screenshots of both. "
        "Use when you need fresh HP, hunger, level, or ability info without "
        "waiting for the periodic refresh."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

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
        "of the tile under the cursor appears in the message log."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        # 'L' (Shift+L) = look in Qud
        chord(["shift", "l"])
        _wait_for_render()
        img = capture_region("viewport")
        return ToolResult(
            text="Entered look mode. Use move() to move the cursor. "
                 "Press escape to exit look mode.",
            image=image_to_png_bytes(img),
        )


class AltOverlayTool(Tool):
    name = "alt_overlay"
    description = (
        "Show item/entity labels (hold Alt). Returns a screenshot with "
        "labels visible. Releases Alt when done."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        hold("alt")
        _wait_for_render(0.2)
        img = capture_region("viewport")
        release("alt")
        return ToolResult(image=image_to_png_bytes(img))


class JournalTool(Tool):
    name = "journal"
    description = (
        "Open the journal screen (Shift+J) and return a screenshot. "
        "Shows quest log, notes, and lore entries."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        open_screen("journal")
        _wait_for_render()
        img = capture_region("viewport")
        close_screen()
        return ToolResult(image=image_to_png_bytes(img))


class AbilitiesTool(Tool):
    name = "abilities"
    description = (
        "Open the abilities screen (Shift+A) and return a screenshot. "
        "Shows activated abilities, cooldowns, and the message log hotkey (Ctrl+M)."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        open_screen("abilities")
        _wait_for_render()
        img = capture_region("viewport")
        close_screen()
        return ToolResult(image=image_to_png_bytes(img))


class MutationsTool(Tool):
    name = "mutations"
    description = (
        "Open the mutations screen (Shift+M) and return a screenshot. "
        "Shows mutation powers and points available to spend."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        open_screen("mutations")
        _wait_for_render()
        img = capture_region("viewport")
        close_screen()
        return ToolResult(image=image_to_png_bytes(img))


register(CharacterSheetTool())
register(InventoryTool())
register(SkillsTool())
register(QuestsTool())
register(JournalTool())
register(AbilitiesTool())
register(MutationsTool())
register(ReadLogTool())
register(ReadStatsTool())
register(LookTool())
register(AltOverlayTool())
