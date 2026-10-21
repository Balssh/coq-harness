"""Screen keybindings and helpers.

Maps screen names to the keys that open them. All keybindings are
placeholders — must be verified in-game via Esc -> k.

The model detects which screen it's on (via screenshot) and reports it
in its Decision. The harness trusts the model's report.
"""

from enum import Enum

from game.controller import press

# Keybindings: screen name -> key (or chord as list).
# ALL VALUES ARE PLACEHOLDERS — verify in-game via Esc -> k.
SCREEN_KEYS: dict[str, str | list[str]] = {
    "inventory":   "e",
    "character":   "C",       # Shift+c — represented as chord below
    "skills":      "S",
    "quests":      "j",
    "map":         "M",
    "look":        "l",
    "equipment":   "E",
    "mutations":   "m",
    "factions":    "F",
}

# Override entries that need chords
SCREEN_KEYS["character"] = ["shift", "c"]
SCREEN_KEYS["skills"]    = ["shift", "s"]
SCREEN_KEYS["map"]       = ["shift", "m"]
SCREEN_KEYS["equipment"] = ["shift", "e"]
SCREEN_KEYS["factions"]  = ["shift", "f"]


def open_screen(name: str) -> None:
    """Open a named screen by pressing its keybinding.
    Raises KeyError if name is not in SCREEN_KEYS."""
    key = SCREEN_KEYS[name]
    if isinstance(key, list):
        from game.controller import chord
        chord(key)
    else:
        press(key)


def close_screen() -> None:
    """Close the current menu/screen (Escape)."""
    press("escape")


class Screen(Enum):
    CHARGEN = "chargen"
    PLAY    = "play"
    MENU    = "menu"
    DEATH   = "death"
    UNKNOWN = "unknown"
