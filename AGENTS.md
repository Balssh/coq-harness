## Goal
A **harness that lets Mistral Large 4 (ML4) play Caves of Qud**. ML4 is the policy: it reads the game
state as text, decides what to do, and calls semantic tools. The harness is reliable infrastructure
around it. Qud runs on Windows; the harness runs in WSL.

This is **not RL training**. It's an exploratory agent-capability demo: can the model play Qud?
Logging and replay are for observability (understanding what the model did and why), not for
training data.

The original screenshot-based design (window capture, frame diffs, key injection) is retired to the
`legacy/screenshot-harness` branch, together with its specs and this file's old version.

## Architecture
See `docs/how-it-works.md` for the walkthrough.

- `mod/`: C# Qud mod. TCP server on 127.0.0.1:47321 (`[4-byte big-endian length][JSON]`); reads the
  game state and runs actions from inside the game.
- `mcp_server.py`: stdio MCP server that turns the mod's commands into semantic tools with compact
  text results. Any MCP client (Claude Code, Vibe, the harness) can play through it.
- `harness/`: the agent loop (`python -m harness play`): LLM client, memory and journal, guards,
  recorder, replay viewer, MP4 export, mod deploy script.

## Key rules
- **Window must never be minimized.** Minimizing stops rendering; alt-tab is fine.
- **Tools are semantic, harness owns mechanics, model owns cognition.** The model never emits raw
  keys, only validated tool calls.
- **Threads in the mod:** game logic and display names on Qud's game thread
  (`GameManager.Instance.gameQueue`); UI screens on the Unity main thread
  (`BridgeMainThread.EnqueueAndWait`).
- **Mod changes:** bump `mod/Protocol.cs` and `mod/manifest.json`, run
  `uv run python -m harness.deploy`, restart Qud, and check `Player.log` for
  `[mcp] MCP server listening` or `MODERROR`.
- **Dependencies:** third-party libs are fine if they make life easier. Prefer stdlib when it's
  sufficient, but don't hand-roll what a well-maintained package already does well.

## Docs
- `docs/how-it-works.md`: how the layers fit together, and the API the model is called through.
- `docs/harness.md`: the agent loop, context, guards, recording, replay, run results.
- `docs/protocol.md`: mod commands and MCP tools.
- `docs/development-history.md`, `docs/ml4-assessment.md`, `docs/future-improvements.md`.
