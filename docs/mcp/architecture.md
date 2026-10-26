# CoQ MCP Architecture

Full MCP-style architecture for Caves of Qud, inspired by
[heroes-3-mcp](https://github.com/andreinwald/heroes-3-mcp).

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Python Agent (mcp/)                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐ │
│  │ client  │  │  tools  │  │ decide  │  │  loop   │  │  run   │ │
│  │  .py    │  │  .py    │  │  .py    │  │  .py    │  │  .py   │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └───┬────┘ │
│       └─────────────┴─────────────┴─────────────┘         │       │
│                    TCP: 127.0.0.1:47321                    │       │
│              [4-byte length][JSON payload]                │       │
└──────────────────────────────────────────────────────────────┼───────┘
                                                               │
┌──────────────────────────────────────────────────────────────┼───────┐
│                    Caves of Qud (C# Mod)                      │       │
│  ┌──────────────────────────────────────────────────────────┐│       │
│  │                    mod/ (C# files)                        ││       │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ ││       │
│  │  │ McpServer│ │ Bridge   │ │ BridgePart│ │ GameState    │ ││       │
│  │  │  .cs     │ │  .cs     │ │   .cs    │ │ Snapshot.cs  │ ││       │
│  │  │ (TCP)    │ │ (hooks)  │ │ (events) │ │ (JSON state) │ ││       │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘ ││       │
│  │       │            │            │              │         ││       │
│  │  ┌────┴────────────┴────────────┴──────────────┴─────┐   ││       │
│  │  │              GameActions.cs (commands)              │   ││       │
│  │  │  move / wait / interact / get / use_item / ...     │   ││       │
│  │  └────────────────────────────────────────────────────┘   ││       │
│  │                          │                                ││       │
│  │                    Keyboard.PushCommand()                 ││       │
│  │                    CommandEvent.Send()                    ││       │
│  │                          │                                ││       │
│  │                    Qud Game Engine (XRL.*)                ││       │
│  └──────────────────────────────────────────────────────────┘│       │
└──────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. State Broadcast (per turn)

```
Qud turn ends
    → BridgePart.HandleEvent(EndTurnEvent)
    → Bridge.Tick(player)
    → GameStateSnapshot.BuildFullState(player)
    → McpServer.Broadcast(json)
    → Python client receives state
    → Agent sees updated game state
```

### 2. Command Execution

```
Agent decides: {"tool": "move", "args": {"direction": "up"}}
    → Python client.send_command("move", direction="up")
    → TCP frame: {"type": "command", "action": "move", ...}
    → Bridge.Tick/TickRender drains Incoming queue
    → GameActions.ExecuteCommand(player, json)
    → Keyboard.PushCommand("CmdMoveN")
    → Qud processes the command (movement, combat, etc.)
    → Turn resolves
    → Bridge.Tick fires again with new state
    → Agent receives updated state
```

## Threading Model

The C# mod uses multiple threads carefully:

| Thread | Role | What it does |
|--------|------|-------------|
| **Game Main Thread** | Unity main thread | Runs `Bridge.TickRender` (every frame), applies commands from `Incoming` queue |
| **Turn Thread** | Qud's simulation thread | Runs `Bridge.Tick` (on `EndTurnEvent`), publishes state snapshots |
| **TCP Accept Thread** | Background | Accepts new client connections |
| **TCP Read Threads** (per client) | Background | Reads incoming commands, enqueues to `Incoming` |
| **TCP Write Threads** (per client) | Background | Sends state snapshots (non-blocking, coalescing) |
| **Focus Keeper Thread** | Background | Keeps `GameManager.focused = true` so the game runs while unfocused |

**Critical rule**: Game state is only read/written on the main thread or turn thread.
TCP threads only touch the `Incoming` queue and the per-client outbox.

## State Snapshot Structure

```json
{
  "type": "state",
  "protocol": "1",
  "version": "1.0.0",
  "player": {
    "name": "string",
    "hp": "int", "hpMax": "int",
    "level": "int", "xp": "int", "xpNext": "int",
    "strength": "int", "agility": "int", "toughness": "int",
    "willpower": "int", "ego": "int", "intelligence": "int",
    "av": "int", "dv": "int", "ma": "int",
    "qn": "int", "ms": "int",
    "hunger": "int", "thirst": "int",
    "temperature": "int", "weight": "int",
    "x": "int", "y": "int",
    "location": "string",
    "inCombat": "bool"
  },
  "zone": {
    "id": "string",
    "width": "int", "height": "int",
    "wx": "int", "wy": "int",
    "zx": "int", "zy": "int", "z": "int",
    "name": "string",
    "isWorldMap": "bool"
  },
  "cells": [
    {
      "x": "int", "y": "int",
      "name": "string",
      "blueprint": "string",
      "isCreature": "bool",
      "isHostile": "bool",
      "isFriendly": "bool",
      "isNeutral": "bool",
      "isItem": "bool",
      "isDoor": "bool",
      "isContainer": "bool",
      "blocksMovement": "bool",
      "distance": "int",
      "hp": "int", "hpMax": "int",
      "level": "int",
      "faction": "string"
    }
  ],
  "messages": ["string", ..., {"msgCount": "int"}],
  "effects": [{"name": "string", "duration": "int"}],
  "inventory": [
    {"name": "string", "slot": "string", "equipped": "bool"}
  ],
  "abilities": [
    {"name": "string", "command": "string", "hotkey": "string"}
  ],
  "time": {
    "segment": "int", "segmentsPerDay": "int",
    "isDay": "bool", "day": "int", "hour": "int"
  }
}
```

## Command Reference

| Action | Parameters | Effect |
|--------|-----------|--------|
| `move` | `direction` (8-dir) | `Keyboard.PushCommand("CmdMove"+dir)` |
| `wait` | `turns` (int, default 1) | `Keyboard.PushCommand("CmdWait")` × N |
| `interact` | `direction` (8-dir) | `CmdInteract` + move command |
| `get` | — | `Keyboard.PushCommand("CmdGet")` |
| `use_item` | `item` (name), `action` (equip/drop/quaff/eat/unequip) | Finds item, sends command |
| `press_key` | `key` (single char) | `Keyboard.PushKey()` |
| `press_command` | `command` (Qud cmd ID) | `Keyboard.PushCommand()` |
| `open_screen` | `screen` (name) | Opens inventory/equipment/etc. |
| `close_menu` | — | `CmdEscape` |
| `choose_option` | `option` (1-9) | Presses number key |
| `auto_explore` | — | `CmdAutoExplore` |
| `travel` | `direction` (cardinal) | `CmdTravel` + move command |
| `go_stairs` | `direction` (up/down) | `CmdGoUp`/`CmdGoDown` |
| `save` | — | `CmdSave` |
| `quit` | — | `CmdQuit` |
| `abandon` | — | `CmdAbandon` |
| `look` | — | `CmdLook` |
| `show_labels` | — | `CmdShowLabels` |

## Comparison with Screenshot-Based Harness

| Feature | Screenshot (old) | MCP (new) |
|---------|-----------------|-----------|
| **State source** | Pixel analysis | Direct game API |
| **HP/Stats** | Model reads from image | Exact integer |
| **Position** | Model estimates from grid | Exact (x, y) |
| **Inventory** | Open screen, read image | Structured list |
| **Hostility** | Model guesses from color | Brain.IsHostileToPlayer() |
| **Turn detection** | Frame-diff on log region | EndTurnEvent |
| **Movement** | SendInput keystrokes | Keyboard.PushCommand() |
| **Reliability** | Fragile (OCR, timing, focus) | Deterministic |
| **Setup complexity** | WSL + Windows + relay | Same machine, one mod |
| **Game modification** | None (external) | C# mod (in-process) |
| **Works with any game** | Yes (screenshots) | No (game-specific mod) |
| **Visual reasoning** | Yes (model sees screen) | No (structured text only) |
