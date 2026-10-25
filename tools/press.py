"""Generic key-press tool — the escape hatch for anything without a dedicated tool.

The model is smart. It reads the keymap in the system prompt and sends keys
directly when no dedicated tool fits the situation.
"""

import time

from game.controller import chord, press
from tools import Tool, ToolResult, register


def _wait_for_render(seconds: float = 0.15) -> None:
    time.sleep(seconds)


class PressTool(Tool):
    name = "press"
    description = (
        "Send a bounded sequence of key presses. Each element is a key name "
        "(e.g. 'up', 'enter', 'escape', 'a', 'shift') or a chord as a list "
        "(e.g. ['shift', 'i']). Maximum 10 keys per call. Use this for any "
        "action not covered by a dedicated tool — menu navigation, inventory "
        "actions on specific slots, dialogue choices, etc. Consult the keymap "
        "in the system prompt for the correct keys. Do NOT use this for "
        "movement — use move() instead."
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
    screens = None  # available everywhere

    def execute(self, keys: list) -> ToolResult:
        sent = []
        for key in keys:
            if isinstance(key, list):
                chord(key)
                sent.append("+".join(key))
            else:
                press(key)
                sent.append(key)
            _wait_for_render()
        return ToolResult(text=f"Sent keys: {' '.join(sent)}")


register(PressTool())
