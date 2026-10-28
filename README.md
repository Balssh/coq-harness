# coq-harness

A harness that lets an LLM play [Caves of Qud](https://www.cavesofqud.com/). It started as a test of
whether Mistral Large 4 (ML4) can play the game. The MCP server works with any MCP client and has been
played with Mistral Vibe and Claude Code.

Qud runs on Windows; the agent side runs in WSL (or on the same machine).

## How it works

```
LLM client (Vibe, Claude Code, ...)
   │  stdio MCP
mcp_server.py ── semantic tools, compact state text, turn waiting, pathing
   │  TCP :47321, [4-byte big-endian length][JSON]
mod/ (C# mod compiled by Qud at startup)
   ├─ McpServer / Bridge      TCP server, command pump, state broadcast
   ├─ GameStateSnapshot       player, zone, visible creatures, explored map, inventory, messages
   ├─ GameActions             movement, items, screens, saves, chargen, firing
   ├─ PopupBridge             popups, conversations and item pickers, answered in-process
   ├─ SkillActions            skills, powers, attribute points
   └─ TradeBridge             the modern trade screen
```

The mod reads state and drives the game from inside Qud, so nothing depends on screenshots, key
injection or window focus. The window still must not be minimized.

## Quick start (MCP)

1. **Deploy the mod**: `.venv/bin/python -m mcp.deploy` copies `mod/` to Qud's `Mods/CoQMcpBridge`.
2. **Enable it in Qud**: Options → Modding → allow scripting mods, enable "CoQ MCP Bridge" in Mod
   Configuration, and restart Qud. `Player.log` shows `[mcp] MCP server listening` once the mod has
   compiled. The server starts at the main menu, so character creation and loading work too.
3. **Register the MCP server** with your client:
   - **Claude Code:**
     `claude mcp add -s local qud -- /path/to/coq-harness/.venv/bin/python /path/to/coq-harness/mcp_server.py`
   - **Mistral Vibe:**
     `vibe mcp add caves-of-qud --transport stdio --command /path/to/uv --arg=run --arg=--project --arg=/path/to/coq-harness --arg=python --arg=/path/to/coq-harness/mcp_server.py`

   The server finds the game through `COQ_HOST`, then localhost, then the WSL gateway.
4. **Play**: `continue_game` (or `start_new_game` + `chargen_auto`), then `get_state`.

## Tools

| Area | Tools |
|---|---|
| State | `get_state` (full), `get_state_raw` (JSON), `get_map` (ASCII map with x/y rulers) |
| Movement | `move`, `go_to(x, y)`, `travel`, `go_stairs`, `auto_explore`, `wait`, `rest` |
| Combat | `move` into a hostile, `attack(direction)`, `fire(x?, y?)`, `use_ability(name)` |
| Items | `get`, `use_item(item, item_action)` (eat, drink, apply, equip, unequip, drop) |
| Popups | `respond_popup(option / button / dismiss / text)`, which covers conversations, Yes/No prompts and container pickers |
| Character | `list_skills`, `learn_skill`, `raise_attribute` |
| Trade | `trade_list`, `trade_select(side, index, count)`, `trade_offer` |
| Game | `continue_game`, `start_new_game`, `chargen_auto`, `list_saves`, `save_game`, `quit_to_menu`, `open_screen`, `close_menu` |

- **Compact results:** each action returns a short status with HP, visible hostiles and new messages.
- **No hidden information:** the state only contains what the character could know, meaning creatures
  in line of sight and objects in explored cells.
- **Further reading:** [`mcp/README.md`](mcp/README.md) has the wire protocol, and
  [`docs/qud_novice_notes.md`](docs/qud_novice_notes.md) has early-game strategy and tool tips to use as
  prompt material.

## Repository layout

| Path | What |
|---|---|
| `mod/` | C# Qud mod (the bridge inside the game) |
| `mcp_server.py` | stdio MCP server, the maintained entry point |
| `mcp/` | Mod deploy script, protocol README, and ML4's own agent loop (`python -m mcp.run`). The agent loop was not updated or tested alongside the recent mod changes. |
| `bridge/`, `client/`, `game/`, `tools/`, `perception/`, `memory/`, `agent/`, `loop/`, `run/`, `recording/`, `main.py` | The original screenshot-based harness: Windows capture and input bridge plus an ML4 agent loop. It is superseded by the mod, and `AGENTS.md` and `docs/specs/` describe it. |
| `docs/` | Design specs, research brief, findings from screenshot runs, guide notes, [development history](docs/development-history.md) |

## Development notes

- **Mod changes** need a Qud restart. Compile errors show up in
  `%USERPROFILE%\AppData\LocalLow\Freehold Games\CavesOfQud\Player.log`. Bump `mod/Protocol.cs` and
  `mod/manifest.json` when you change the mod.
- **Threads:**
  - Game logic (inventory actions, skill purchases, firing, display names) must run on Qud's game
    thread through `GameManager.Instance.gameQueue`.
  - UI screens (popups, pickers, trade) must run on the Unity main thread through
    `BridgeMainThread.EnqueueAndWait`.
- **Reloading the MCP server:** an MCP client keeps the server process it started, so reconnect it
  (`/mcp` in Claude Code) after editing `mcp_server.py`.
