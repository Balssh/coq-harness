"""Meta tools: save, quit, restart_run.

During chargen, quit and restart_run are no-ops to prevent the model
from accidentally quitting the game or ending the episode.
"""

import time

from game.controller import press
from game.screens import close_screen
from memory.state import get_state
from tools import Tool, ToolResult, register


def _wait_for_render(seconds: float = 0.3) -> None:
    time.sleep(seconds)


def _in_chargen() -> bool:
    return get_state().phase == "chargen"


class SaveTool(Tool):
    name = "save"
    description = "Save the game. Opens the menu and saves."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

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

    def execute(self) -> ToolResult:
        if _in_chargen():
            return ToolResult(text="Quit is not available during character creation. Use 'back' instead.")
        press("escape")
        _wait_for_render()
        press("q")
        _wait_for_render()
        press("enter")
        return ToolResult(text="Quit to main menu.")


class RestartRunTool(Tool):
    name = "restart_run"
    description = (
        "End the current run and start a new one. Only works during play, "
        "not during character creation (no-op in chargen)."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        if _in_chargen():
            return ToolResult(text="Restart is not available during character creation. Keep going with chargen.")
        from run.manager import signal_restart
        signal_restart()
        return ToolResult(text="Signaled restart. The current episode will end.")


register(SaveTool())
register(QuitTool())
register(RestartRunTool())
