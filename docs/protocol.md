# In-game bridge: setup and protocol

The C# mod (`mod/`) runs a TCP server inside Caves of Qud. `mcp_server.py` turns it into MCP tools,
and the harness (`harness/`) plays through those tools. Inspired by
[heroes-3-mcp](https://github.com/andreinwald/heroes-3-mcp).

## Architecture

```
harness/ (python -m harness play)      any MCP client (Vibe, Claude Code, ...)
        └──────────── stdio MCP ──────────────┘
                          │
                   mcp_server.py   tools, compact results, turn waiting, pathing
                          │  TCP 47321: [4-byte big-endian length][JSON]
             Caves of Qud + mod/   McpServer, Bridge, GameStateSnapshot, GameActions,
                                   PopupBridge, SkillActions, TradeBridge
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
.venv/bin/python -m harness.deploy
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
6. Restart Qud (mods compile at startup). `Player.log` shows `[mcp] MCP server listening` once the
   TCP server on port 47321 is up; it starts at the main menu.

### 3. Play

Point an MCP client at `mcp_server.py`, or run the harness (`python -m harness play`, see the root
README).

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
{"type": "command", "action": "use_item", "item": "vinewafer", "item_action": "eat", "cmdId": "item_103"}
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
      "faction": "Villagers",
      "difficulty": "Average"
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
  "quests": [
    {"name": "What's Eating the Watervine?", "giver": "Mehmet", "giverLocation": "Joppa",
     "steps": [{"name": "Travel to Red Rock", "text": "Journey two parasangs north of Joppa to Red Rock.",
                "finished": false, "failed": false, "optional": false}]}
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
| `use_item(item, item_action)` | Yes | Use inventory item (eat/drink/equip/apply or use/unequip/drop); the item is looked up on the game thread |
| `press_key(key)` | No | Press a single key |
| `press_command(command)` | Varies | Send raw Qud command (e.g. CmdFire) |
| `open_screen(screen)` | No | Open inventory/equipment/skills/etc. |
| `close_menu()` | No | Close the open popup or screen through its own Exit/Cancel (does nothing on the plain map; Escape there would open the system menu) |
| `choose_option(option)` | No | Select numbered dialogue option (1-9) |
| `auto_explore()` | Yes | Trigger auto-explore |
| `travel(direction)` | Yes | Run to the zone edge (cardinal only) and step into the next zone; walks around terrain that blocks the straight line, and says so when hostiles in view stop it |
| `go_stairs(direction)` | Yes | Take stairs up/down |
| `save()` | No | Save the game |
| `quit()` | No | Quit to main menu |
| `abandon()` | No | Abandon current run |
| `look()` | No | Enter look mode |
| `show_labels()` | No | Show item/entity labels |

Tools added to `mcp_server.py` on top of the raw protocol actions:

| Tool | Advances Turn | Description |
|------|---------------|-------------|
| `respond_popup(option/button/dismiss/text)` | No | Answer any popup, conversation, or item picker (containers: `button="take_all"`) |
| `go_to(x, y)` | Yes | Walk a shortest path; stops next to an occupied target, on damage, popups, new hostiles |
| `get_map()` | No | ASCII map of the zone with x/y rulers |
| `attack(direction?, x?, y?)` | Yes | Melee-attack an adjacent cell by coordinates or direction, or the adjacent hostile by default; also force-attacks walk-over creatures such as dreadroots |
| `fire(x?, y?)` | Yes | Shoot the missile weapon at a cell or the nearest hostile; reloads automatically |
| `rest()` | Yes | Wait until healed (stops if something happens) |
| `use_ability(name, x?, y?)` | Yes | Activated abilities (Sprint, Freezing Ray, ...); targeted ones are aimed at (x, y) or the nearest visible hostile (mod action `pick_target`) |
| `list_skills(all?)` / `learn_skill(name)` | No | Spend skill points |
| `raise_attribute(attribute)` | No | Spend attribute points |
| `trade_list()` / `trade_select(side, index, count)` / `trade_offer()` | No | Buy and sell on the open trade screen (side 0 = trader, 1 = you) |
| `world_map(radius?)` | No | The parasangs around you as a letter grid, a legend with each terrain's look description, and the known places with directions (mod action `world_info`: terrain per parasang plus revealed map notes) |
| `chargen_presets()` / `chargen_auto(preset?)` | No | List the game's preset characters; create a Classic character from a preset (mod action `chargen_auto` with `pregen`, through the game's Pregen path) or at random |

Action results return a compact status (HP, hostiles with the game's threat rating such as
`[Tough]`, a `World:` line with the zone's world coordinates, the terrain of the neighbouring
parasangs and how many zones away the known places are, new messages); `get_state` returns everything, including the quest log.
The state only contains what the player knows: creatures in line of sight and objects in explored
cells (`zone.explored` holds one `0`/`1` row string per y). Item names spell out the stat glyphs
(`boar-skin gloves AV1 DV0`, `short bow PV4`, `slender pestle PV3/5 dmg 1d2-1`).
The "Your health has dropped below N%!" popup is dismissed automatically while waiting for a turn and
reported as a `WARNING:` line in the result.
Trading: talk to a merchant and pick "Let's trade", then `trade_list`, `trade_select`, `trade_offer`
(the game asks to confirm the dram difference in a popup), and `close_menu` to leave.

## Project Structure

See the [root README](../README.md#repository-layout).

## Troubleshooting

### "Connection refused" from mcp_server.py or the harness

The mod isn't running. Make sure:
1. Qud is running with the mod enabled
2. Qud was restarted after deploying (the server starts at the main menu)
3. Check Qud's log for `[mcp]` messages: `%USERPROFILE%\AppData\LocalLow\Freehold Games\CavesOfQud\Player.log`

### Mod doesn't appear in Mod Configuration

1. Check the mods folder path is correct: `python -m harness.deploy --check`
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
