"""Meta tools: save, quit, restart_run."""

import time

from game.controller import press
from game.screens import close_screen
from tools import Tool, ToolResult, register


def _wait_for_render(seconds: float = 0.3) -> None:
    time.sleep(seconds)


class SaveTool(Tool):
    name = "save"
    description = "Save the game. Opens the menu and saves."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        press("escape")
        _wait_for_render()
        # In Qud's escape menu, 's' = save
        press("s")
        _wait_for_render()
        press("enter")
        return ToolResult(text="Game saved.")


class QuitTool(Tool):
    name = "quit"
    description = "Quit to the main menu."
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        press("escape")
        _wait_for_render()
        # In Qud's escape menu, 'q' = quit to menu
        press("q")
        _wait_for_render()
        press("enter")
        return ToolResult(text="Quit to main menu.")


class RestartRunTool(Tool):
    name = "restart_run"
    description = (
        "End the current run and start a new one. Signals the run manager "
        "to begin a new episode."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        # Signal the run manager via a module-level flag
        from run.manager import signal_restart
        signal_restart()
        return ToolResult(text="Signaled restart. The current episode will end.")


register(SaveTool())
register(QuitTool())
register(RestartRunTool())
