# How the project works

A walkthrough of how the pieces fit together, from the game up to the model. For the details of each
part see [`harness.md`](harness.md) (the agent loop, recording, replay) and
[`protocol.md`](protocol.md) (the mod's commands and the MCP tools).

## The big picture

Four layers, each talking only to the one next to it:

```
┌──────────────────────────────────────────────────────────────────┐
│ Mistral API  (api.mistral.ai, model mistral-large-4)              │  the brain
└──────────────▲───────────────────────────────────────────────────┘
               │ HTTPS: POST /v1/chat/completions (+ tool list)
┌──────────────┴───────────────────────────────────────────────────┐
│ harness/  (python -m harness play)                                │  the agent loop
│  agent.py  llm.py  game.py  memory.py  recorder.py  prompts/      │
└──────────────▲───────────────────────────────────────────────────┘
               │ MCP over stdio (JSON-RPC through a pipe)
┌──────────────┴───────────────────────────────────────────────────┐
│ mcp_server.py                                                     │  the tools
└──────────────▲───────────────────────────────────────────────────┘
               │ TCP 127.0.0.1:47321  [4-byte big-endian length][JSON]
┌──────────────┴───────────────────────────────────────────────────┐
│ Caves of Qud (Windows) + mod/  (C#, compiled by Qud at startup)   │  the game
└──────────────────────────────────────────────────────────────────┘
```

The model never sees the screen or presses keys. It reads text (the game state, written out by the
mod and formatted by `mcp_server.py`) and calls named tools such as `go_to(42, 19)` or `fire()`.
This replaced the original screenshot design (window capture, frame diffs, key injection), which
lives on in the `legacy/screenshot-harness` branch: reading the game's own data is exact, reading
pixels isn't.

## Layer 1: the mod (`mod/`, C# inside Qud)

Qud compiles mods when it starts, so the mod runs inside the game with full access to its objects.

| File | What it does |
|---|---|
| `McpServer.cs` | TCP server on port 47321; reads length-prefixed JSON commands |
| `Bridge.cs` | Dispatches each command: `get_state` returns a snapshot, `{"type":"command","action":"move",...}` runs an action |
| `GameStateSnapshot.cs` | Turns the live game into one JSON object: player stats and position; visible creatures (with the game's threat rating and base name), items and doors; explored cells; messages; inventory; abilities; quests; any open popup |
| `GameActions.cs` | Movement (through Qud's own input commands), items, screens, saves, character creation, firing, `world_info` (terrain and known places on the world map) |
| `PopupBridge.cs`, `TradeBridge.cs`, `SkillActions.cs` | Answer popups and conversations, trade, buy skills and raise attributes by calling the game's UI and code directly |

**Threads.** Qud has a game thread and Unity's main thread. Building item and creature names off the
game thread can corrupt them, so the mod queues that work onto the game thread
(`GameManager.Instance.gameQueue`), and UI work onto the main thread
(`BridgeMainThread.EnqueueAndWait`). When the game thread is idle and doesn't drain its queue, some
reads fall back to the server thread.

**Changing the mod:** edit the C#, bump `mod/Protocol.cs` and `mod/manifest.json`, run
`uv run python -m harness.deploy` (copies `mod/` into Qud's Mods folder), restart Qud, and look for
`[mcp] MCP server listening` (or `MODERROR`) in `Player.log`.

## Layer 2: `mcp_server.py` (the tools)

A standard [MCP](https://modelcontextprotocol.io) server, the protocol Claude Code, Vibe and other
clients use for tools. It turns the raw socket into about 40 tools a model can use, and most of the
game sense lives here:

- **Compact results.** After each action it returns a short status instead of the raw JSON:
  - HP, level and position, and the `World:` line (zone, terrain, neighbouring parasangs, known
    places);
  - visible enemies with their threat rating and "hits you for 2-8";
  - `KNOW` lines with tactics for creatures it has notes on;
  - a `DANGER:` line when the fight can kill you;
  - only the messages that are new since the last call.
- **Composite tools written in Python**, not single game commands:
  - `go_to` plans a path and walks it step by step, stopping when something happens;
  - `travel` runs to a zone edge and crosses it;
  - `flee` picks the best escape route (an edge or stairs) away from enemies;
  - `go_to_place` crosses several zones to a named place, avoiding dangerous terrain at low level;
  - `fire` aims, reloads, and reports what each shot did.
- **Memory across runs:** `runs/bestiary.json` records what each kind of creature has done to the
  player; `data/creatures.json` holds hand-written tactics.

Because it's plain MCP, any MCP client can play: Vibe and Claude Code launch it as a tool server
(see the README), and the harness does the same.

## Layer 3: `harness/` (the agent loop)

The program that plays on its own: `uv run python -m harness play --new-game --max-steps 250`.

- **`game.py`** starts `mcp_server.py` as a child process and talks MCP to it over stdin/stdout. It
  hides tools the harness handles itself (saving, loading, character creation, quitting) and
  duplicate tools.
- **`agent.py`** runs the loop. Each step:
  1. builds the messages:
     - the system prompt: `prompts/system.md`, `docs/qud_novice_notes.md` and the journal's lessons;
     - a memory block: goal, notes, "the story so far", named people seen;
     - the recent steps;
  2. calls the model once;
  3. runs the tool calls in its reply (up to 4 per step);
  4. applies the guards:
     - message popups are accepted automatically;
     - the combat check holds back one risky melee blow when `DANGER:` is up;
     - watchdogs catch "stuck in place", "same call five times" and "walking tile by tile";
     - the zone gate warns before Red Rock at too low a level;
  5. every so often compresses old steps into a summary (`prompts/summarize.md`) so the context
     stays bounded.
- **`memory.py`** handles the model's memory tools (`set_goal`, `note`, `forget_note`) and the
  cross-run journal `runs/journal.md`. At the end of a run the model writes lessons
  (`prompts/lessons.md`), which are appended there and pruned by hand.
- **Setup:** the harness quits any game to the menu, asks the model to pick a preset character
  (`prompts/character.md`), creates it through the game's preset path, and waits for world
  generation.

## Layer 4: the API the model is called through

Every step is one HTTPS request:

```
POST https://api.mistral.ai/v1/chat/completions
```

That's Mistral's OpenAI-compatible Chat Completions endpoint, called from `harness/llm.py` with the
Python standard library (`urllib`, no SDK). The body:

```json
{
  "model": "mistral-large-4",
  "messages": [ {"role": "system", ...}, {"role": "user", ...},
                {"role": "assistant", "tool_calls": [...]}, {"role": "tool", ...}, ... ],
  "tools": [ {"type": "function",
              "function": {"name": "go_to", "description": "...", "parameters": {...}}}, ... ],
  "tool_choice": "any",
  "reasoning_effort": "high",
  "max_tokens": 4096
}
```

- **`tools`** are the MCP tools' JSON schemas converted to function-calling format, plus the three
  memory tools.
- **`tool_choice: "any"`** forces at least one tool call every step (Mistral's spelling of OpenAI's
  `"required"`).
- **`reasoning_effort: "high"`.** Without it ML4 skipped thinking on most steps (164 of 208 in the
  first live run).
- **The reply** has a short visible thought, hidden reasoning (Mistral's `thinking` chunks: recorded,
  not sent back) and tool calls. Each tool result goes back as a `role: "tool"` message.
- **Usage** includes `cached_tokens`: after about 30 steps, Mistral reports 85–95% of each prompt as
  cached.
- **Retries** on 408, 409, 429 and 5xx.
- **The API key** comes from `MISTRAL_API_KEY`, then the repo's `.env`, then `~/.vibe/.env`.
- **Other providers:** `--provider openai|openrouter` or `--base-url` point the same code at any
  OpenAI-compatible endpoint.

## One step, end to end

ML4 decides to shoot a croc:

1. The harness sends the conversation to Mistral. The reply says "The croc is 4 tiles away, I'll
   shoot it" and calls `fire()`.
2. The harness calls `fire` over MCP. `mcp_server.py` picks the nearest hostile and sends
   `{"action":"fire_at","x":45,"y":13}` over TCP.
3. The mod aims and fires inside Qud. The game resolves the turn and logs
   "You hit the croc (x1) for 6 damage!".
4. `mcp_server.py` waits for the turn to end, fetches a new snapshot and builds the result:
   ```
   Fired at (45,13): hit the croc for 6 damage.
   HP 19/19 … Hostiles: croc (44,13) d=3 HP=7/13 [Average] hits you for 3-4
   ```
5. The harness records everything, runs its guards, and appends the result for the next step.

## Recording and replay

- **Recording.** Every run writes `runs/harness/<run>/`:
  - `events.jsonl`: every model call, tool call, nudge and popup;
  - `states/`: the raw game snapshots;
  - `frames/`: screenshots of the Qud window, taken in the background through `powershell.exe`;
  - `system_prompt.md` and `meta.json`.
- **Replay.** `uv run python -m harness replay` serves the viewer at http://localhost:8765: a
  timeline, a map drawn from the state, filters, notes, and side-by-side comparison of two runs.
- **Video.** `uv run python -m harness export <run> --speed 2 --smart` renders an MP4.

## Where to look for what

| Question | File |
|---|---|
| What the model is told | `harness/prompts/system.md`, `docs/qud_novice_notes.md`, `runs/journal.md` |
| What a tool does | `mcp_server.py` (search for `def <tool>`) |
| How the game is read or changed | `mod/GameStateSnapshot.cs`, `mod/GameActions.cs` |
| The loop, guards and memory | `harness/agent.py`, `harness/memory.py` |
| The LLM call | `harness/llm.py` |
| Design and history | [`harness.md`](harness.md), [`protocol.md`](protocol.md), [`development-history.md`](development-history.md), [`ml4-assessment.md`](ml4-assessment.md), [`future-improvements.md`](future-improvements.md) |
