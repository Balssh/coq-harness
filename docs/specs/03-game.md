# Spec: Game (Controller + Screens)

## Purpose

Two modules that sit between the tools layer and the bridge client:

- `controller.py`: thin wrapper over the bridge client for sending keys. No game knowledge.
- `screens.py`: knows which keys open which Qud screens/menus. Provides open/close helpers.
  Defines the game phase enum used by the turn loop.

## Controller (`game/controller.py`)

Dumb key-sender. Tools call this instead of the bridge client directly.

```python
from client.bridge_client import get_client

def press(key: str) -> None:
    """Press and release a single key."""
    get_client().keys([key])

def chord(keys: list[str]) -> None:
    """Press a key combination, e.g. ["shift", "up"]."""
    get_client().keys(keys)

def hold(key: str) -> None:
    """Press and hold a key (release later with release())."""
    get_client().key_down(key)

def release(key: str) -> None:
    """Release a held key."""
    get_client().key_up(key)
```

No keymap, no game knowledge. The bridge already handles key name → VK code mapping.

## Screens (`game/screens.py`)

### Screen Keybindings

Maps screen names to the keys that open them. **All keybindings must be verified
in-game** via Esc → k (the wiki is outdated).

```python
SCREEN_KEYS: dict[str, str] = {
    "inventory":   "e",    # verify
    "character":   "C",    # verify (character sheet)
    "skills":      "S",    # verify
    "quests":      "j",    # verify (journal)
    "map":         "M",    # verify (world map)
    "look":        "l",    # verify
    "equipment":   "E",    # verify
    "mutations":   "m",    # verify
    "factions":    "F",    # verify
}
```

### Functions

```python
from game.controller import press

def open_screen(name: str) -> None:
    """Open a named screen by pressing its keybinding.
    Raises KeyError if name is not in SCREEN_KEYS."""
    press(SCREEN_KEYS[name])

def close_screen() -> None:
    """Close the current menu/screen (Escape)."""
    press("escape")
```

### Screen Enum

```python
from enum import Enum

class Screen(Enum):
    CHARGEN = "chargen"    # character creation screens
    PLAY    = "play"       # main game world view
    MENU    = "menu"       # any menu/inventory/sheet is open
    DEATH   = "death"      # death screen, episode over
    UNKNOWN = "unknown"    # can't tell
```

### Screen Detection

The **model** detects which screen it's on by looking at the screenshot. It reports
the screen in its decision output (see `agent/schemas.py`). The harness trusts the
model's report for loop logic:

- `Screen.PLAY` → use the turn clock (`wait_for_change`) after actions.
- `Screen.CHARGEN` → no turn clock; chargen has its own flow (see `run/creation.py`).
- `Screen.MENU` → no turn clock; menus are navigated by key presses.
- `Screen.DEATH` → end the episode (see `run/manager.py`).

No separate screen classifier. The model is the classifier.

## How Tools Use These Modules

Tools compose controller + screens + bridge + perception:

| Tool | What it does |
|------|-------------|
| `move("up")` | `controller.press("up")` → turn loop calls `wait_for_change` |
| `inventory()` | `screens.open_screen("inventory")` → wait → crop screenshot → return to model |
| `equip("c")` | `screens.open_screen("inventory")` → `controller.press("c")` → `controller.press("enter")` |
| `look()` | `controller.press(SCREEN_KEYS["look"])` → model reads viewport |

## File Layout

```
game/
  __init__.py
  controller.py    # press, chord, hold, release
  screens.py       # SCREEN_KEYS, open_screen, close_screen, Screen enum
```

## Dependencies

- `client/bridge_client.py` (via controller)
- Stdlib only otherwise

## Open Items

- All keybindings in `SCREEN_KEYS` are placeholders. Must be verified in-game.
- Some screens may require modifier chords (e.g., Shift+E instead of E). The
  `SCREEN_KEYS` values should support chord notation if needed (e.g., `"shift+e"`
  or a list `["shift", "e"]`).
