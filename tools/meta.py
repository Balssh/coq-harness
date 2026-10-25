"""Meta tools: save, quit, abandon, restart_run, close_menu.

Consolidated from 6 tools to 5:
- send_keys → removed (replaced by the generic press() tool)
- restart_episode → removed (harness handles restart after death automatically)

During chargen, quit, restart_run, and abandon are no-ops to prevent the
model from accidentally quitting the game or ending the episode.
"""

import time

from game.controller import press
from memory.state import get_state
from tools import Tool, ToolResult, register


def _wait_for_render(seconds: float = 0.3) -> None:
    time.sleep(seconds)


def _in_chargen() -> bool:
    return get_state().phase == "chargen"


class SaveTool(Tool):
    name = "save"
    description = "Save the game."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"play", "menu"}

    def execute(self) -> ToolResult:
        press("escape")
        _wait_for_render()
        press("s")
        _wait_for_render()
        press("enter")
        return ToolResult(text="Game saved.")


class QuitTool(Tool):
    name = "quit"
    description = (
        "Quit to the main menu. Only works during play, not during "
        "character creation (no-op in chargen to prevent accidental quit)."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"play", "menu"}

    def execute(self) -> ToolResult:
        if _in_chargen():
            return ToolResult(text="Quit is not available during character creation. Use 'back' instead.")
        press("escape")
        _wait_for_render()
        press("q")
        _wait_for_render()
        press("enter")
        return ToolResult(text="Quit to main menu.")


class AbandonTool(Tool):
    name = "abandon"
    description = (
        "Abandon the current run (Esc → Abandon). Terminates the episode "
        "cleanly without dying. Use when you are permanently stuck, the "
        "build is unviable, or the situation is hopeless."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"play"}

    def execute(self) -> ToolResult:
        if _in_chargen():
            return ToolResult(text="Abandon is not available during character creation.")
        press("escape")
        _wait_for_render(0.5)
        # Navigate to Abandon in the Esc menu. The model should verify via
        # screenshot. Send down arrows to find it, then enter.
        for _ in range(10):
            press("down")
            _wait_for_render(0.1)
        press("enter")
        _wait_for_render(0.5)
        press("enter")
        return ToolResult(
            text="Attempted to abandon the run. If a confirmation appeared, "
                 "it was confirmed. The episode should end."
        )


class RestartRunTool(Tool):
    name = "restart_run"
    description = (
        "End the current run and start a new one. Only works during play, "
        "not during character creation (no-op in chargen)."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"play"}

    def execute(self) -> ToolResult:
        if _in_chargen():
            return ToolResult(text="Restart is not available during character creation. Keep going with chargen.")
        from run.manager import signal_restart
        signal_restart()
        return ToolResult(text="Signaled restart. The current episode will end.")


class CloseMenuTool(Tool):
    name = "close_menu"
    description = (
        "Close an open menu or dialog (Escape). Use this when a menu screen, "
        "dialogue, or context popup is visible on screen. "
        "Does NOT clear the message log — the log is a scrolling history "
        "and old messages stay visible. "
        "Does NOT dismiss '>press [Space]' prompts — use press(['space']) "
        "for those. Does NOT advance the turn."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False
    screens = {"play", "menu", "dialogue", "trade"}

    def execute(self) -> ToolResult:
        press("escape")
        _wait_for_render(0.2)
        return ToolResult(text="Pressed Escape — closed any open menu/dialog.")


register(SaveTool())
register(QuitTool())
register(AbandonTool())
register(RestartRunTool())
register(CloseMenuTool())
