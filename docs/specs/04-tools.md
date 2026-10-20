# Spec: Tools

## Purpose

Tools are the **semantic API** the model calls. The model never emits raw keys —
it calls tools by name with parameters. Tools compose the controller, screens,
bridge client, and perception modules to perform game actions.

## Tool Base Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ToolResult:
    text: str = ""              # text for the model to read
    image: bytes | None = None  # PNG bytes of a cropped screenshot
    error: bool = False         # True if this is an error result

class Tool(ABC):
    name: str                   # unique identifier, e.g. "move"
    description: str            # shown to the model in the system prompt
    parameters: dict            # JSON schema for the model's arguments
    advances_turn: bool = False # if True, turn loop calls wait_for_change after execute

    @abstractmethod
    def execute(self, **params) -> ToolResult: ...
```

## Registry

Simple dict, populated at startup. Tools register themselves.

```python
_REGISTRY: dict[str, Tool] = {}

def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool

def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)

def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())

def tool_schemas() -> list[dict]:
    """Returns [{name, description, parameters}] for the system prompt."""
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in _REGISTRY.values()
    ]
```

## Execution Flow

1. Model outputs a tool call: `{"tool": "move", "args": {"direction": "up"}}`
2. Agent validates `args` against the tool's parameter schema
3. Agent looks up the tool in the registry
4. Tool `execute()` runs: sends keys via controller, may capture screenshots
5. Tool returns `ToolResult`
6. If `tool.advances_turn` is True: turn loop calls `bridge.wait_for_change(timeout=3.0)`
7. Turn loop captures a fresh frame
8. `ToolResult` (text + image) + fresh frame are appended to the conversation
9. Model decides the next action

The **turn loop owns the turn clock**. Tools just send keys and return results.

## Error Handling

Tool execution errors are **caught and returned as `ToolResult(error=True, text=...)`**.
The model sees the error message and decides what to do. Tools never raise exceptions
to the agent loop — a failed tool call is information, not a crash.

Example: `equip("z")` when slot z is empty → `ToolResult(error=True, text="No item in slot z.")`

## Tool Categories

### Movement

| Tool | Params | advances_turn | Description |
|------|--------|---------------|-------------|
| `move` | `direction`: "up" \| "down" \| "left" \| "right" \| "up_left" \| "up_right" \| "down_left" \| "down_right" | Yes | Move one tile in a direction |
| `rest` | `turns`: int (optional, default 1) | Yes | Rest (pass turns). If turns omitted, rest until interrupted |
| `go_stairs` | `direction`: "up" \| "down" | Yes | Take stairs. Must be standing on stairs |
| `auto_explore` | — | Yes | Harness-side loop: explore unexplored adjacent tiles until none remain or interrupted |
| `wait` | — | Yes | Do nothing, pass one turn. For waiting for NPCs, enemies, etc. |

### Interaction

| Tool | Params | advances_turn | Description |
|------|--------|---------------|-------------|
| `get` | — | Yes | Pick up item(s) on current tile. If multiple items, a menu appears — model picks via follow-up |
| `drop` | `slot`: str (letter a-z) | Yes | Open inventory, drop item in slot |
| `equip` | `slot`: str (letter a-z) | Yes | Open inventory, equip item in slot. Handles equip sub-menu (choose slot) |
| `unequip` | `slot`: str (letter a-z) | Yes | Open equipment screen, unequip item in slot |
| `quaff` | `slot`: str (letter a-z) | Yes | Open inventory, quaff item in slot |
| `eat` | `slot`: str (letter a-z) | Yes | Open inventory, eat item in slot |
| `talk` | — | Yes | Initiate conversation with adjacent NPC. Model handles dialogue choices via follow-up |
| `trade` | — | Yes | Initiate trade with adjacent NPC (talk → trade option) |

**Menu navigation pattern** (for `equip`, `drop`, `quaff`, `eat`, `unequip`):
1. Open the relevant screen via `screens.open_screen(...)`
2. Wait for the menu to render
3. Press the slot letter via `controller.press(slot)`
4. If a sub-menu appears (e.g., "Equip on which hand?"), capture it and return to model
5. Model calls the tool again with the sub-menu choice, or a follow-up tool handles it

### Info (no turn advance)

| Tool | Params | advances_turn | Description |
|------|--------|---------------|-------------|
| `character_sheet` | — | No | Open character sheet, crop, return screenshot |
| `inventory` | — | No | Open inventory, crop, return screenshot |
| `skills` | — | No | Open skills/abilities screen, crop, return |
| `quests` | — | No | Open journal/quests, crop, return |
| `read_log` | — | No | Crop the message log region at full resolution, return |
| `read_stats` | — | No | Return stats bar + abilities bar crops. For when the model wants fresh HP/hunger/abilities without waiting for the periodic refresh |
| `look` | — | No | Enter look mode (press look key), capture viewport, return. Model uses move keys to inspect tiles |
| `alt_overlay` | — | No | Hold Alt (item labels), capture, release, return screenshot |

Info tools return cropped screenshots (`ToolResult.image`) plus optional text.
The model reads the image to understand the screen contents.

### Meta

| Tool | Params | advances_turn | Description |
|------|--------|---------------|-------------|
| `save` | — | No | Save the game (Esc → Save) |
| `quit` | — | No | Quit to main menu |
| `restart_run` | — | No | End current run, start a new one. Signals the run manager |

## Parameter Schemas

Schemas are JSON Schema dicts. Example for `move`:

```python
{
    "type": "object",
    "properties": {
        "direction": {
            "type": "string",
            "enum": ["up", "down", "left", "right",
                     "up_left", "up_right", "down_left", "down_right"]
        }
    },
    "required": ["direction"]
}
```

## File Layout

```
tools/
  __init__.py          # registry, Tool base class, ToolResult
  movement.py          # move, rest, go_stairs, auto_explore, wait
  interaction.py       # get, drop, equip, unequip, quaff, eat, talk, trade
  info.py              # character_sheet, inventory, skills, quests, read_log, look, alt_overlay
  meta.py              # save, quit, restart_run
```

Tools register themselves on import. `tools/__init__.py` imports all category
modules to trigger registration.

## Dependencies

- `client/bridge_client.py` (via game/controller)
- `game/controller.py`, `game/screens.py`
- `perception/` (for cropping screenshots)
- `jsonschema` (or similar) for parameter validation — or hand-rolled if simple enough

## Open Items

- Exact keybindings for all actions must be verified in-game (Esc → k).
- `auto_explore` is the most complex tool — it runs a harness-side loop. Needs its
  own sub-spec or at least a detailed design before implementation.
- Menu navigation (sub-menus after selecting an item) needs a state machine or
  the model drives it turn-by-turn. TBD which approach.
- `look` mode interaction: after entering look mode, movement keys move the cursor.
  The model needs to know it's in look mode (via `Screen` enum or tool result text).
