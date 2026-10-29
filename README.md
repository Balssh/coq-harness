# coq-harness

A harness that lets an LLM play [Caves of Qud](https://www.cavesofqud.com/). It started as a test of
whether Mistral Large 4 (ML4) can play the game. The MCP server works with any MCP client and has been
played with Mistral Vibe and Claude Code. The harness in `harness/` drives a model through the same
MCP tools on its own, with system prompts, memory, and a recorder plus replay viewer for each run.

Qud runs on Windows; the agent side runs in WSL (or on the same machine).

## How it works

```
harness/ (python -m harness play)  or  any MCP client (Vibe, Claude Code, ...)
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

## Quick start

1. **Deploy the mod**: `uv run python -m harness.deploy` copies `mod/` to Qud's `Mods/CoQMcpBridge`.
2. **Enable it in Qud**: Options → Modding → allow scripting mods, enable "CoQ MCP Bridge" in Mod
   Configuration, and restart Qud. `Player.log` shows `[mcp] MCP server listening` once the mod has
   compiled. The server starts at the main menu, so character creation and loading work too.
3. **Either run the harness** (see [below](#the-harness)): `uv run python -m harness play`
4. **Or register the MCP server** with your client:
   - **Claude Code:**
     `claude mcp add -s local qud -- /path/to/coq-harness/.venv/bin/python /path/to/coq-harness/mcp_server.py`
   - **Mistral Vibe:**
     `vibe mcp add caves-of-qud --transport stdio --command /path/to/uv --arg=run --arg=--project --arg=/path/to/coq-harness --arg=python --arg=/path/to/coq-harness/mcp_server.py`

   The server finds the game through `COQ_HOST`, then localhost, then the WSL gateway.
   Then play: `continue_game` (or `start_new_game` + `chargen_auto`, optionally with a preset name
   from `chargen_presets`), then `get_state`.

## Tools

| Area | Tools |
|---|---|
| State | `get_state` (full), `get_state_raw` (JSON), `get_map` (ASCII map with x/y rulers), `world_map` (terrain and known places around you) |
| Movement | `move`, `go_to(x, y)`, `travel`, `go_to_place(place)`, `flee()`, `go_stairs`, `auto_explore`, `wait`, `rest` |
| Combat | `move` into a hostile, `attack(x?, y?)` or `attack(direction)` (default: the adjacent hostile), `fire(x?, y?)`, `use_ability(name, x?, y?)` (targeted abilities aim at the cell or the nearest hostile) |
| Items | `get`, `use_item(item, item_action)` (eat, drink, apply, equip, unequip, drop) |
| Popups | `respond_popup(option / button / dismiss / text)`, which covers conversations, Yes/No prompts and container pickers |
| Character | `list_skills`, `learn_skill`, `raise_attribute` |
| Trade | `trade_list`, `trade_select(side, index, count)`, `trade_offer` |
| Game | `continue_game`, `start_new_game`, `chargen_presets`, `chargen_auto(preset?)`, `list_saves`, `save_game`, `quit_to_menu`, `open_screen`, `close_menu` |

- **Compact results:** each action returns a short status with HP, visible hostiles and new messages.
- **No hidden information:** the state only contains what the character could know, meaning creatures
  in line of sight and objects in explored cells.
- **Further reading:** [`docs/protocol.md`](docs/protocol.md) has the wire protocol, and
  [`docs/qud_novice_notes.md`](docs/qud_novice_notes.md) has early-game strategy and tool tips to use as
  prompt material.

## The harness

```
uv run python -m harness play                       # ML4 plays the loaded game (or continues the last save)
uv run python -m harness play --new-game --max-steps 500 --label first-try   # the model picks a preset character
uv run python -m harness play --new-game --character "Marsh Taur"             # or name one, or --character random
uv run python -m harness replay                     # pick a run in the browser
uv run python -m harness export <run> --speed 2     # render a run to MP4 (--smart pacing, --annotations; also in the viewer)
```

`uv run coq-play ...` works too. [`docs/harness.md`](docs/harness.md) documents the implementation.

- **Model:** Mistral (`mistral-large-4`) by default, with `reasoning_effort: high` (`--reasoning` to change). The key comes from `MISTRAL_API_KEY`, the repo's
  `.env`, or `~/.vibe/.env`. Any OpenAI-compatible API works too: `--provider openai --model ...`,
  `--provider openrouter --model ...`, or `--base-url http://localhost:8000/v1 --model ...` for a
  local server. `--extra-body` passes provider options such as reasoning settings.
- **Tools:** the harness starts `mcp_server.py` as an MCP client, so the model plays with exactly the
  tools other clients get. Saving, loading and character creation are handled by the harness and
  hidden from the model. Once a popup or screen opens, other queued actions in that response are
  skipped.
- **Prompts** (`harness/prompts/`): turn priorities (popups, screens, danger, healing, level-ups,
  exploring with `auto_explore` then NPCs then the next zone), plus the guide notes in
  `docs/qud_novice_notes.md` and the lessons from previous runs.
- **Memory:**
  - The model keeps a goal and numbered notes (`set_goal`, `note`, `forget_note`), shown every turn.
  - When the context grows past `--keep-steps` steps (default 30), the oldest are summarised into
    "the story so far" and dropped. Older tool results are shortened.
  - At the end of a run the model writes lessons into `runs/journal.md`; the next runs read its hand-kept sections and the latest 3 runs' lessons.
- **Watchdog:** if nothing changes for 8 turns, or the same call repeats 5 times, the harness tells the
  model to try something else. It also points out zone changes.
- **Stops** at death, `--max-steps` (default 300), `--max-minutes`, or Ctrl-C. It saves every 50
  steps and at the end unless the character died.
- **Recording** (`runs/harness/<run>/`):
  - every model response, with its reasoning, text, tool calls and token usage;
  - every tool result;
  - the full game state after each action;
  - a screenshot of the Qud window (taken in the background with PrintWindow; the window must not be
    minimized; `--no-screenshots` to skip);
  - memory changes, summaries and nudges.
- **Replay viewer:**
  - shows the screenshot next to a map drawn from the recorded state;
  - shows the model's thinking, calls and results for each step, and its memory at that point;
  - an HP timeline marks level-ups, nudges and errors;
  - runs in progress can be followed live;
  - `?run=<id>&frame=N` links to a moment.

## Repository layout

| Path | What |
|---|---|
| `mod/` | C# Qud mod (the bridge inside the game) |
| `mcp_server.py` | stdio MCP server, the maintained entry point |
| `harness/` | The LLM harness: play loop, LLM client, memory, recorder, replay viewer, prompts, and the mod deploy script |
| `data/creatures.json` | Hand-written tactics for common early creatures, shown in `KNOW` lines |
| `runs/` | Git-ignored. `runs/harness/<run>/` holds recordings, `runs/journal.md` the lessons carried between runs (hand-kept sections plus the latest 3 runs are read), `runs/bestiary.json` what each kind of creature has done to the player |
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
