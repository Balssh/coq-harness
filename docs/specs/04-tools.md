# Spec: Tools

## Purpose

Tools are the **semantic API** the model calls. The model never emits raw keys —
it calls tools by name with parameters. Tools compose the controller, screens,
bridge client, and perception modules to perform game actions.

## Philosophy: Pi-Style Thin Primitives

The model is smart. Tools are **thin primitives** that encode game mechanics
so the model doesn't have to. The model uses dedicated tools when they fit,
and falls back to the generic `press()` tool with the keymap when they don't.

Design principles:
- **Minimal surface area**: ~24 tools total, but screen-based filtering means
  the model only sees 2-20 tools per turn depending on context.
- **Semantic where it matters**: movement, item use, and screen navigation have
  dedicated tools with validated parameters.
- **Generic escape hatch**: `press(keys)` lets the model send any key sequence
  using the keymap reference in the system prompt.
- **Screen-aware**: tools declare which screens they're relevant on. The agent
  only receives schemas for tools available on the current screen.

## Tool Base Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ToolResult:
    text: str = ""
    image: bytes | None = None       # PNG bytes of a cropped screenshot
    images: dict[str, bytes] = {}    # named PNG bytes
    error: bool = False

class Tool(ABC):
    name: str                        # unique identifier, e.g. "move"
    description: str                 # shown to the model in the system prompt
    parameters: dict                 # JSON schema for the model's arguments
    advances_turn: bool = False      # if True, turn loop calls wait_for_change
    screens: set[str] | None = None  # None = available on all screens

    @abstractmethod
    def execute(self, **params) -> ToolResult: ...
```

## Screen-Based Filtering

Tools declare which screens they're relevant on via the `screens` attribute:

```python
def tools_for_screen(screen: str) -> list[Tool]:
    """Return tools relevant to the given screen.

    Tools with `screens=None` are always available (e.g., `press`).
    Tools with `screens` set are only available when the current screen
    is in that set.
    """
    return [
        t for t in _REGISTRY.values()
        if t.screens is None or screen in t.screens
    ]
```

The agent calls `tools_for_screen(state.screen)` to get the filtered list,
and `_format_tools(screen)` renders it for the system prompt.

### Screen → Tool Mapping

| Screen | Tools Available |
|--------|-----------------|
| `play` | move, go_stairs, rest, auto_explore, travel, wait_until_healed, get, use_item, interact, choose_option, open_screen, read_log, read_stats, look, show_labels, save, quit, abandon, restart_run, press |
| `menu` | choose_option, open_screen, read_log, read_stats, save, quit, press |
| `dialogue` | choose_option, press |
| `trade` | choose_option, press |
| `title` | select, confirm, back, press |
| `mode_select` | select, confirm, back, press |
| `chargen` | select, confirm, next, back, press |
| `death` | press |
| `world_map` | press |

## Execution Flow

1. Model outputs a tool call: `{"tool": "move", "args": {"direction": "up"}, "wait_for_turn": true}`
2. Agent validates the tool is available on the current screen
3. Agent validates `args` against the tool's parameter schema
4. Agent looks up the tool in the registry
5. Tool `execute()` runs: sends keys via controller, may capture screenshots
6. Tool returns `ToolResult`
7. If `tool.advances_turn` is True OR `decision.wait_for_turn` is True:
   turn loop calls `bridge.wait_for_change(timeout=3.0)`
8. Turn loop captures a fresh frame
9. `ToolResult` (text + image) + fresh frame are appended to the conversation
10. Model decides the next action

The **turn loop owns the turn clock**. Tools just send keys and return results.

The `wait_for_turn` field in the Decision schema lets the model control the
turn clock when using `press()` — set it to `true` for turn-advancing keys,
`false` for info-only actions.

## Error Handling

Tool execution errors are **caught and returned as `ToolResult(error=True, text=...)`**.
The model sees the error message and decides what to do. Tools never raise exceptions
to the agent loop — a failed tool call is information, not a crash.

## Tool Catalog (24 tools)

### Movement (play only, advances turn)

| Tool | Params | Description |
|------|--------|-------------|
| `move` | `direction`: 8 compass | Move one tile. Bump enemies to attack, doors to open. |
| `go_stairs` | `direction`: up/down | Take stairs. Must be on a staircase tile. |
| `rest` | `turns`: int (optional) | Rest to heal/wait. Omit turns to rest indefinitely. |
| `auto_explore` | — | Trigger Qud's auto-explore. Advances many turns. |
| `travel` | `direction`: N/S/E/W | Auto-pathfind to zone edge, load adjacent zone. |
| `wait_until_healed` | — | Rest until healed or interrupted. Advances many turns. |

### Interaction (play only, advances turn)

| Tool | Params | Description |
|------|--------|-------------|
| `get` | — | Pick up items on current tile. Menu may appear for multiples. |
| `use_item` | `slot`: a-z, `action`: equip/drop/quaff/eat/unequip | Use inventory item. Opens inventory, selects slot, performs action. |
| `interact` | `direction`: 8 compass | Space+direction context menu (talk, open, take, etc.). |

### Menu/Dialogue (menu/dialogue/trade screens)

| Tool | Params | Description |
|------|--------|-------------|
| `choose_option` | `option`: 1-9 | Select numbered option in dialogue or menu. |

### Info (play/menu screens, no turn advance)

| Tool | Params | Description |
|------|--------|-------------|
| `open_screen` | `screen`: inventory/equipment/skills/character/quests/journal/abilities/mutations | Open a game screen, return screenshot. Close with `press(['escape'])`. |
| `read_log` | — | Full-resolution message log crop. |
| `read_stats` | — | Stats bar + abilities bar crops. |
| `look` | — | Enter look mode. Use `move()` to inspect tiles. |
| `show_labels` | — | Hold Alt for item/entity labels, capture, release. |

### Meta

| Tool | Screens | Description |
|------|---------|-------------|
| `save` | play, menu | Save the game. |
| `quit` | play, menu | Quit to main menu (no-op in chargen). |
| `abandon` | play | Abandon run cleanly (Esc → Abandon). |
| `restart_run` | play | End current run, start new one. |

### Chargen (title/mode_select/chargen screens)

| Tool | Screens | Description |
|------|---------|-------------|
| `select` | title, mode_select, chargen | Navigate menu with arrow keys. |
| `confirm` | title, mode_select, chargen | Press Enter to select. |
| `next` | chargen | Press Num 9 to advance to next screen. |
| `back` | title, mode_select, chargen | Press Escape to go back. |

### Generic (all screens)

| Tool | Params | Description |
|------|--------|-------------|
| `press` | `keys`: array of strings or string arrays (max 10) | Send any key sequence. Escape hatch for actions not covered by dedicated tools. Consult the keymap in the system prompt. |

## Keymap Reference (in system prompt)

The system prompt includes a keymap reference table for use with `press()`:

- **Movement**: arrows/numpad, `.` (wait), `~` (wait until healed), `e` (auto-explore), `-`/`+` (stairs)
- **Interaction**: `g` (get), `space`+direction (interact), `1-9` (numbered options)
- **Screens**: `I`/`E`/`X`/`P`/`Q`/`J`/`A`/`M`/`L` (various screens), `escape` (close)
- **Inventory actions**: `d` (drop), `w` (wear), `q` (quaff), `e` (eat), `t` (take off)
- **Meta**: `escape`→`s`→`enter` (save), `escape`→`q`→`enter` (quit)

## Registry

```python
_REGISTRY: dict[str, Tool] = {}

def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool

def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)

def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())

def tools_for_screen(screen: str) -> list[Tool]:
    return [t for t in _REGISTRY.values()
            if t.screens is None or screen in t.screens]

def tool_schemas(screen: str | None = None) -> list[dict]:
    tools = tools_for_screen(screen) if screen else all_tools()
    return [{"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools]
```

## File Layout

```
tools/
  __init__.py          # registry, Tool base class, ToolResult, screen filtering
  movement.py          # move, go_stairs, rest, auto_explore, travel, wait_until_healed
  interaction.py       # get, use_item, interact, choose_option
  info.py              # open_screen, read_log, read_stats, look, show_labels
  meta.py              # save, quit, abandon, restart_run
  chargen.py           # select, confirm, next, back
  press.py             # press (generic key sender)
```

## Dependencies

- `client/bridge_client.py` (via game/controller)
- `game/controller.py`, `game/screens.py`
- `perception/` (for cropping screenshots)
- `jsonschema` for parameter validation
- `PIL` for image encoding

## Open Items

- Exact keybindings for all actions must be verified in-game (Esc → k).
- `auto_explore` key binding needs verification (currently 'e').
- Menu navigation (sub-menus after selecting an item) — model drives via
  `press()` or `choose_option()` turn-by-turn.
- `look` mode interaction: after entering look mode, movement keys move the cursor.
  The model needs to know it's in look mode (via screen report or tool result text).
