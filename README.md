# coq-harness

A harness that lets an LLM play [Caves of Qud](https://www.cavesofqud.com/) on its own. It was built
to answer one question: can Mistral Large 4 (ML4) play the game? A C# mod inside Qud exposes the
game as semantic MCP tools, and an agent loop drives the model through them, recording every step
for replay. The MCP server also works with any MCP client, such as Mistral Vibe or Claude Code.

Qud runs on Windows; the agent side runs in WSL (or on the same machine).

## Results

Nine supervised new-game runs of 118–300 steps (details in [`docs/ml4-assessment.md`](docs/ml4-assessment.md)):

- **The opening goes well.** ML4 explores Joppa, talks to the villagers and takes both quests, then
  trades for armor and a weapon. In the later runs (7–9) it reached level 5–6 within 250 steps.
- **Tool use is reliable.** It sent one invalid argument in about 2,900 calls.
- **Judgment over time is the weak spot.** Four runs died, each in a fight the model had itself
  called too dangerous. It spends resources badly, and no run finished the first main quest.

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

The original screenshot-based harness (window capture, key injection, an ML4 loop that read the
screen) is retired to the [`legacy/screenshot-harness`](../../tree/legacy/screenshot-harness)
branch. [`docs/how-it-works.md`](docs/how-it-works.md) walks through the current design.

## Requirements

- **Caves of Qud** on Windows, with scripting mods allowed. The mod is compiled by the
  game at startup, so no .NET SDK is needed.
- **WSL2** (or Python on the same Windows machine) with [uv](https://docs.astral.sh/uv/) and
  Python 3.10+. `uv sync` installs the dependencies (the MCP SDK and Pillow).
- **A Mistral API key** for the harness (`MISTRAL_API_KEY`, or a `.env` file), or a key for any
  OpenAI-compatible provider.
- **Optional:** `ffmpeg` for MP4 export of runs; Node.js 20+ to render the presentation video.

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
uv run python -m harness export <run> --speed 2     # render a run to MP4
```

- **Model:** `mistral-large-4` with `reasoning_effort: high` by default. The key comes from
  `MISTRAL_API_KEY`, the repo's `.env`, or `~/.vibe/.env`. Any OpenAI-compatible API works too:
  `--provider openai|openrouter --model ...`, or `--base-url` for a local server.
- **Tools:** the harness is an MCP client of `mcp_server.py`, so the model plays with exactly the
  tools other clients get. Saving, loading and character creation are handled by the harness.
- **Context:** each step has three parts:
  - the system prompt: turn priorities (`harness/prompts/`), the guide notes and lessons from
    earlier runs;
  - the goal and notes the model keeps for itself;
  - the recent steps. Older steps are folded into a running summary.
- **Guards:**
  - routine popups are accepted for the model;
  - one risky melee blow is held back when a fight could kill;
  - watchdogs catch loops and getting stuck.
- **Recording and replay:**
  - every run writes `runs/harness/<run>/`: each model response, tool result, game state, and a
    screenshot of the Qud window;
  - the replay viewer shows these side by side with a map and an HP timeline, live or afterwards,
    and exports MP4.
- **Stops** at death, `--max-steps` (default 300), `--max-minutes` or Ctrl-C, and saves every 50 steps.

[`docs/harness.md`](docs/harness.md) documents all of it.

## Repository layout

| Path | What |
|---|---|
| `mod/` | C# Qud mod (the bridge inside the game) |
| `mcp_server.py` | stdio MCP server, the maintained entry point |
| `harness/` | The LLM harness: play loop, LLM client, memory, recorder, replay viewer, prompts, and the mod deploy script |
| `video/` | The presentation video: Remotion scenes, narration script, Voxtral voicing and clip extraction |
| `data/creatures.json` | Hand-written tactics for common early creatures, shown in `KNOW` lines |
| `runs/` | Git-ignored. `runs/harness/<run>/` holds recordings, `runs/journal.md` the lessons carried between runs (hand-kept sections plus the latest 3 runs are read), `runs/bestiary.json` what each kind of creature has done to the player |
| `docs/` | [How it works](docs/how-it-works.md), [harness](docs/harness.md), [protocol](docs/protocol.md), research brief, guide notes, [development history](docs/development-history.md), [ML4 assessment](docs/ml4-assessment.md), [possible improvements](docs/future-improvements.md) |

## How it was developed

- **People:** one developer, working with AI coding agents from 2026-10-18 to 2026-10-29. They set
  the direction, found the hard root causes, and supervised every run.
- **Mistral Large 4 in [Mistral Vibe](https://mistral.ai/products/vibe)** (local sessions and Vibe's
  cloud agent) wrote the first version:
  - the screenshot harness;
  - the in-game mod;
  - the first MCP server.
- **Claude Code** (Claude Opus) then:
  - rebuilt the bridge's popup, conversation, trade and skill handling;
  - wrote most of the current tools, the agent loop and the replay viewer;
  - ran and analysed the nine runs;
  - made the video.
- **Mistral models used:**
  - `mistral-large-4` is the player.
  - The video is narrated by Voxtral TTS (`voxtral-mini-tts-3`).
  - Each take is checked with `voxtral-small-transcribe-3`, which also times the subtitles.
- **Inspired by:**
  - [heroes-3-mcp](https://github.com/andreinwald/heroes-3-mcp): a Mistral model plays Heroes of Might
    and Magic III through an MCP server built into the game engine. coq-harness follows the same
    idea: a server inside the game, exposed as MCP tools.
  - [llm-of-qud](https://github.com/ToaruPen/llm-of-qud): another LLM player for Qud, with an in-game
    mod and a Python harness that serves MCP.
  - [raves-of-qud](https://github.com/TheMutantFactory/raves-of-qud) (Raves of Mud): an in-game mod
    streams what the player sees over a local socket to a Godot client that renders Qud in 2.5D.
- **Open source it builds on:**
  - the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk);
  - [Pillow](https://python-pillow.org/);
  - [FFmpeg](https://ffmpeg.org/);
  - [uv](https://github.com/astral-sh/uv);
  - [Remotion](https://www.remotion.dev/) and React for the video.
- **The game:** the mod uses Caves of Qud's own C# scripting API. Caves of Qud is by Freehold Games
  and isn't open source.

[`docs/development-history.md`](docs/development-history.md) tells the story commit by commit,
including what each agent got right and wrong.

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
