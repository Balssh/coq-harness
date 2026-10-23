"""Screen keybindings and helpers.

Keybindings verified against the Caves of Qud research brief (post-1.0):
  I = Inventory, E = Equipment, P = Skills, X = Character sheet,
  Q = Quests, J = Journal, A = Abilities, M = Mutations, L = Look.
Uppercase letters are sent as shift+letter chords.

The model detects which screen it's on (via screenshot) and reports it
in its Decision. The harness trusts the model's report.
"""

from enum import Enum

from game.controller import press

# Keybindings: screen name -> key (or chord as list).
# Uppercase Qud keys (I, E, P, X, Q, J, A, M, L) are shift+letter chords.
SCREEN_KEYS: dict[str, str | list[str]] = {
    "inventory":   ["shift", "i"],
    "equipment":   ["shift", "e"],
    "skills":      "p",
    "character":   "x",
    "quests":      ["shift", "q"],
    "journal":     ["shift", "j"],
    "abilities":   ["shift", "a"],
    "mutations":   ["shift", "m"],
    "look":        ["shift", "l"],
    "map":         "m",
    "factions":    ["shift", "f"],
}


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
    TITLE       = "title"
    MODE_SELECT = "mode_select"
    CHARGEN     = "chargen"
    PLAY        = "play"
    MENU        = "menu"
    DIALOGUE    = "dialogue"
    TRADE       = "trade"
    WORLD_MAP   = "world_map"
    DEATH       = "death"
    UNKNOWN     = "unknown"
