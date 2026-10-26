# CoQ MCP Harness

Full MCP-style architecture for letting Mistral Large 4 play Caves of Qud.
Inspired by [heroes-3-mcp](https://github.com/andreinwald/heroes-3-mcp).

## Architecture

```
┌─────────────────┐    TCP 47321      ┌─────────────────────────────┐
│  Python Agent   │◄─────────────────►│  Caves of Qud (C# mod)      │
│  (mcp/)         │  JSON state +     │  ├─ McpServer.cs (TCP)      │
│  ├─ client.py   │  commands         │  ├─ Bridge.cs (per-turn)    │
│  ├─ tools.py    │                   │  ├─ BridgePart.cs (hooks)   │
│  ├─ decide.py   │                   │  ├─ GameStateSnapshot.cs    │
│  ├─ loop.py     │                   │  ├─ GameActions.cs          │
│  └─ run.py      │                   │  └─ Protocol.cs / MiniJson  │
└─────────────────┘                   └─────────────────────────────┘
```

### Key Differences from Screenshot-Based Harness

| Aspect | Old (screenshots) | New (MCP) |
|--------|-------------------|-----------|
| **Perception** | Screenshots + vision model | Structured JSON state |
| **State fidelity** | Model reads pixels | Exact HP, positions, inventory |
| **Turn sync** | Frame-diff heuristic | `EndTurnEvent` fires exactly |
| **Action space** | Key presses | Semantic commands |
| **Setup** | WSL + Windows bridge + relay | Just Qud + Python on same machine |
| **Input** | SendInput/PostMessage | `Keyboard.PushCommand()` |
| **Reliability** | Fragile (OCR, timing) | Deterministic |

## Setup

### 1. Deploy the Mod

```bash
python -m mcp.deploy
```

This copies the C# mod files to Qud's mods folder:
- Windows: `%USERPROFILE%\AppData\LocalLow\Freehold Games\CavesOfQud\Mods\CoQMcpBridge\`
- macOS: `~/Library/Application Support/com.FreeholdGames.CavesOfQud/Mods/CoQMcpBridge/`
- Linux: `~/.config/unity3d/Freehold Games/CavesOfQud/Mods/CoQMcpBridge/`

### 2. Enable the Mod in Qud

1. Launch Caves of Qud
2. Go to **Options → Modding**
3. Enable **"Allow scripting mods"** (you'll be prompted)
4. Go to **Mod Configuration** (bottom-right of title screen)
5. Enable **"CoQ MCP Bridge"**
6. Restart Qud (mods compile at startup)
7. Start or load a game
8. Take one step in-game (activates the mod, opens TCP server on port 47321)

### 3. Set Up Python Environment

```bash
# Install dependencies
pip install mistralai pydantic

# Set your API key
export MISTRAL_API_KEY="your-key-here"
```

### 4. Run the Agent

```bash
python -m mcp.run
```

Or with options:
```bash
python -m mcp.run --host 127.0.0.1 --port 47321 --episode 1
```

## MCP Protocol

The mod exposes a simple TCP protocol on `127.0.0.1:47321`:

### Framing

```
[4 bytes: big-endian uint32 length][UTF-8 JSON payload]
```

### Client → Server (Commands)

```json
{"type": "get_state"}
{"type": "command", "action": "move", "direction": "up", "cmdId": "move_123"}
{"type": "command", "action": "wait", "turns": 5, "cmdId": "wait_456"}
{"type": "command", "action": "interact", "direction": "right", "cmdId": "interact_789"}
{"type": "command", "action": "press_key", "key": " ", "cmdId": "key_101"}
{"type": "command", "action": "press_command", "command": "CmdFire", "cmdId": "cmd_102"}
{"type": "command", "action": "use_item", "item": "vinewafer", "action": "eat", "cmdId": "item_103"}
{"type": "command", "action": "auto_explore", "cmdId": "explore_104"}
{"type": "command", "action": "travel", "direction": "right", "cmdId": "travel_105"}
{"type": "command", "action": "go_stairs", "direction": "down", "cmdId": "stairs_106"}
{"type": "command", "action": "open_screen", "screen": "inventory", "cmdId": "screen_107"}
{"type": "command", "action": "close_menu", "cmdId": "close_108"}
{"type": "command", "action": "choose_option", "option": 2, "cmdId": "option_109"}
{"type": "command", "action": "save", "cmdId": "save_110"}
{"type": "command", "action": "quit", "cmdId": "quit_111"}
{"type": "command", "action": "abandon", "cmdId": "abandon_112"}
{"type": "command", "action": "look", "cmdId": "look_113"}
{"type": "command", "action": "show_labels", "cmdId": "labels_114"}
{"type": "command", "action": "get", "cmdId": "get_115"}
```

### Server → Client (Responses)

**State snapshot** (broadcast after every turn, or in response to `get_state`):

```json
{
  "type": "state",
  "protocol": "1",
  "version": "1.0.0",
  "player": {
    "name": "Amos",
    "hp": 25, "hpMax": 25,
    "level": 3, "xp": 350, "xpNext": 400,
    "strength": 18, "agility": 16, "toughness": 20,
    "willpower": 14, "ego": 12, "intelligence": 15,
    "av": 4, "dv": 10, "ma": 2, "qn": 100, "ms": 100,
    "hunger": 0, "thirst": 0, "temperature": 70, "weight": 35,
    "x": 40, "y": 12,
    "location": "Joppa",
    "inCombat": false
  },
  "zone": {
    "id": "JoppaWorld.53.3.1.0.10",
    "width": 80, "height": 25,
    "name": "Joppa",
    "isWorldMap": false
  },
  "cells": [
    {
      "x": 41, "y": 12,
      "name": "Elder Irudad",
      "blueprint": " NPC_Villager_ElderIrudad",
      "isCreature": true,
      "isHostile": false,
      "isFriendly": true,
      "isNeutral": false,
      "isItem": false,
      "isDoor": false,
      "isContainer": false,
      "blocksMovement": false,
      "distance": 1,
      "hp": 30, "hpMax": 30,
      "level": 3,
      "faction": "Villagers"
    }
  ],
  "messages": ["You enter Joppa.", "The village spreads before you.", {"msgCount": 42}],
  "effects": [],
  "inventory": [
    {"name": "Iron Sword", "slot": "Hand", "equipped": true},
    {"name": "Vinewafer", "blueprint": "Food_Vinewafer", "equipped": false}
  ],
  "abilities": [
    {"name": "Long Sword", "command": "CmdLongSword", "hotkey": "1"}
  ],
  "time": {
    "segment": 4200, "segmentsPerDay": 12000,
    "isDay": true, "day": 1, "hour": 10
  }
}
```

**Command result**:

```json
{"type": "command_result", "result": {"ok": true, "action": "move", "direction": "up", "cmdId": "move_123"}}
```

## Available Tools

| Tool | Advances Turn | Description |
|------|---------------|-------------|
| `move(direction)` | Yes | Move one tile (8 directions) |
| `wait(turns?)` | Yes | Wait/rest to heal |
| `interact(direction)` | Yes | Interact with adjacent tile |
| `get()` | Yes | Pick up items on current tile |
| `use_item(item, action)` | Yes | Use inventory item (equip/drop/quaff/eat/unequip) |
| `press_key(key)` | No | Press a single key |
| `press_command(command)` | Varies | Send raw Qud command (e.g. CmdFire) |
| `open_screen(screen)` | No | Open inventory/equipment/skills/etc. |
| `close_menu()` | No | Close menu/dialog (Escape) |
| `choose_option(option)` | No | Select numbered dialogue option (1-9) |
| `auto_explore()` | Yes | Trigger auto-explore |
| `travel(direction)` | Yes | Travel to zone edge (cardinal only) |
| `go_stairs(direction)` | Yes | Take stairs up/down |
| `save()` | No | Save the game |
| `quit()` | No | Quit to main menu |
| `abandon()` | No | Abandon current run |
| `look()` | No | Enter look mode |
| `show_labels()` | No | Show item/entity labels |

## Project Structure

```
coq-harness/
├── mod/                    # C# mod for Caves of Qud
│   ├── manifest.json       # Mod metadata
│   ├── McpServer.cs        # TCP server
│   ├── Bridge.cs           # Per-turn hooks, state broadcast
│   ├── BridgePart.cs       # Player part (event hooks)
│   ├── GameStateSnapshot.cs # Serialize game state to JSON
│   ├── GameActions.cs      # Execute commands
│   ├── Protocol.cs         # Wire protocol
│   └── MiniJson.cs         # Minimal JSON parser
│
├── mcp/                    # Python MCP client + agent
│   ├── client.py           # TCP client, state management
│   ├── tools.py            # MCP-style tools
│   ├── schemas.py          # Decision schema (pydantic)
│   ├── llm.py              # Mistral API (text-only)
│   ├── decide.py           # Decision flow
│   ├── loop.py             # Turn loop
│   ├── run.py              # Episode manager
│   ├── deploy.py           # Mod deployment
│   └── prompts/            # System prompts
│       ├── system_base.md
│       ├── system_play.md
│       └── fewshot.md
│
└── ... (legacy screenshot-based harness)
```

## Troubleshooting

### "Connection refused" when running the agent

The mod isn't running. Make sure:
1. Qud is running with the mod enabled
2. You've taken at least one step in-game (the mod activates on first turn)
3. Check Qud's log for `[mcp]` messages: `%USERPROFILE%\AppData\LocalLow\Freehold Games\CavesOfQud\Player.log`

### Mod doesn't appear in Mod Configuration

1. Check the mods folder path is correct: `python -m mcp.deploy --check`
2. Make sure `manifest.json` is valid JSON
3. Restart Qud after deploying

### "Allow scripting mods" prompt

Qud shows a security warning when it detects C# scripting mods. You must:
1. Go to Options → Modding
2. Enable "Allow scripting mods"
3. Restart Qud

### State updates are slow

The mod publishes state after every turn. If the game is running slowly:
1. Check that `runInBackground` is working (the mod sets this)
2. Make sure Qud's window isn't minimized
3. Check for errors in Qud's Player.log

## License

MIT
