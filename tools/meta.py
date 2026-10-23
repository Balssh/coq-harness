"""Meta tools: save, quit, restart_run, abandon, send_keys, restart_episode.

During chargen, quit, restart_run, and abandon are no-ops to prevent the
model from accidentally quitting the game or ending the episode.
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


class AbandonTool(Tool):
    name = "abandon"
    description = (
        "Abandon the current run (Esc -> Abandon). Terminates the episode "
        "cleanly without dying. Use when you are permanently stuck, the "
        "build is unviable, or the situation is hopeless. This is the "
        "non-death way to end an episode."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        if _in_chargen():
            return ToolResult(text="Abandon is not available during character creation.")
        press("escape")
        _wait_for_render(0.5)
        # Navigate to Abandon in the Esc menu. The menu items vary, so we
        # send arrow keys to find it. In Qud's Esc menu, Abandon is typically
        # near the bottom.
        # Send several down arrows then enter — the model should verify via
        # screenshot. A safer approach: the model should read the menu.
        # For now, navigate: the Esc menu in Qud typically has:
        # Options, Game Info, Save and Quit, Abandon (or similar order)
        for _ in range(10):
            press("down")
            _wait_for_render(0.1)
        press("enter")
        _wait_for_render(0.5)
        # May need confirmation
        press("enter")
        return ToolResult(
            text="Attempted to abandon the run. If a confirmation appeared, "
                 "it was confirmed. The episode should end."
        )


class SendKeysTool(Tool):
    name = "send_keys"
    description = (
        "Send a bounded sequence of key presses. Use for menu navigation "
        "that doesn't fit a dedicated tool: arrow-key menu selection, "
        "keyboard shortcuts in screens, etc. Each element is a key name "
        "(e.g. 'up', 'down', 'enter', 'escape', 'a', 'shift') or a chord "
        "as a list (e.g. ['shift', 'a']). Maximum 10 keys per call. "
        "Do NOT use this for movement or combat — use the dedicated tools."
    )
    parameters = {
        "type": "object",
        "properties": {
            "keys": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
                "maxItems": 10,
                "description": "Sequence of keys or chords to send",
            }
        },
        "required": ["keys"],
    }
    advances_turn = False

    def execute(self, keys: list) -> ToolResult:
        from game.controller import chord
        sent = []
        for key in keys:
            if isinstance(key, list):
                chord(key)
                sent.append("+".join(key))
            else:
                press(key)
                sent.append(key)
            _wait_for_render(0.15)
        return ToolResult(text=f"Sent keys: {' '.join(sent)}")


class RestartEpisodeTool(Tool):
    name = "restart_episode"
    description = (
        "Execute the full restart sequence after death: Space at the tombstone "
        "-> title screen -> New Game -> mode select -> preset. Use this when "
        "you are on the death screen and want to start a new run immediately. "
        "The harness normally handles this, but this tool lets the model "
        "trigger it explicitly."
    )
    parameters = {"type": "object", "properties": {}}
    advances_turn = False

    def execute(self) -> ToolResult:
        # Space at tombstone -> title
        press("space")
        _wait_for_render(1.0)
        # Title -> New Game (Enter, since New Game is the default cursor)
        press("enter")
        _wait_for_render(1.0)
        # Mode select -> Classic (Enter, since Classic is typically default)
        press("enter")
        _wait_for_render(1.0)
        # Preset screen -> first preset (Enter)
        press("enter")
        _wait_for_render(0.5)
        return ToolResult(
            text="Restart sequence executed: tombstone -> title -> New Game -> "
                 "Classic -> preset selected. Chargen should begin shortly."
        )


register(SaveTool())
register(QuitTool())
register(RestartRunTool())
register(AbandonTool())
register(SendKeysTool())
register(RestartEpisodeTool())
