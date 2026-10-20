## Goal
Build a **harness that lets Mistral Large 4 (ML4) play Caves of Qud from screenshots**. ML4 is the policy — it sees the screen, decides what to do, and calls semantic tools. The harness is just reliable infrastructure around it. Qud runs on Windows; the harness/agent runs in WSL (Vibe).

This is **not RL training**. It's an exploratory agent-capability demo: can the model play Qud? Logging and replay are for observability — understanding what the model did and why — not for training data.

## Key decisions

**Architecture: two sides, persistent bridge**
- **Windows side**: one long-lived Python process ("bridge") — screen capture + input injection + socket API.
- **WSL side**: everything intelligent — perception, memory, tools, ML4 agent, turn loop, logging. Frames cross via loopback socket as bytes (never via `/mnt/c`).
- Networking: Windows 11 22H2+ mirrored networking → `localhost` works from WSL. Older WSL2 → use gateway IP from `/etc/resolv.conf` + one firewall rule.

**Windows deps: minimal**
- Python 3.10+, uv, `pip install pywin32 windows-capture` (plus `mss`/`numpy`/`pillow` only if you keep a screen-capture fallback).

**Window must never be minimized**
- You can alt-tab freely, but minimizing stops rendering → stale frames.
- Capture with **Windows Graphics Capture by window title** (`windows_capture` package) — captures the window even fully occluded/off-screen.
- Input: try `PostMessage(WM_KEYDOWN/UP)` to the HWND first (zero focus steal); fallback is `AttachThreadInput` + `AllowSetForegroundWindow` + `SendInput` + restore previous foreground. Send arrows+Shift (or VK_NUMPAD*), not physical-key-dependent keys.
- **Open question (spike needed)**: does Qud (Unity) process PostMessage input and keep rendering when unfocused? Test before committing to PostMessage-first.

**Turn clock: diff the message log region**
- Qud's message log (right side of screen) gets new text when a turn resolves.
- Frame-diff (no ML) on the **log region** is the turn signal: send action → wait for log change (timeout 3 s) → re-capture.
- Full-frame diff is unreliable (ambient animations cause false positives).

**Movement: model picks a direction**
- `move(direction)` — the model looks at the screenshot and picks one of 8 compass directions. Harness sends the key. No BFS, no pathfinding for basic movement.
- `auto_explore` (harness-side) for systematic wandering when the model wants to discover new tiles.

**UI layout**
- Right side: message log (turn clock signal + narrative).
- Bottom: stats bar (HP, hunger, level, etc.) — model reads from screenshot each turn.
- No separate stat parser; the model sees everything.

**Character creation: model-led, random name**
- Model drives chargen (picks build archetype, stats, mutations).
- Character name is randomly generated — no `type_text` tool needed.

**Harness components (each a separate small module)**
1. `bridge/` (Windows): `server.py` (socket API: grab / keys / wait_for_change), `capture.py` (WGC), `input.py` (SendInput wrappers + keymap), `framediff.py` (numpy log-region diff)
2. `client/bridge_client.py` (WSL)
3. `game/`: `controller.py` (symbolic action → key sequence), `screens.py` (which screen: creation tab / inventory / map / death)
4. `tools/`: base class + registry; movement (`move`, `rest`, stairs, `auto_explore`), interaction (`get`, `drop`, `equip`, `quaff`, `eat`, `talk`, `trade`), info (`character_sheet`, `inventory`, `skills`, `quests`, `read_log`, `look`, `alt_overlay`), meta (`save`, `quit`, `restart_run`)
5. `perception/`: crop viewport/log/stats-bar; downscale viewport, full-res log (ML4 reads Qud's font fine)
6. `memory/`: `state.py` (hp, hunger, goal, turn count), `transcript.py` (ML4 transcribes log each step), `journal.py` (cross-episode notes), `map_memory.py`
7. `agent/`: prompts (`system_base.md` with distilled Qud manual — verify keys in-game via Esc→k, wiki is outdated; `system_creation.md`; `system_play.md`; few-shot), `schemas.py` (pydantic JSON output), `llm.py` (retry-on-invalid, fallback `wait`), `decide.py`
8. `loop/`: `turn.py`, `phases.py` (creation → play), `watchdog.py` (stuck detection, budgets)
9. `run/`: `manager.py` (episode lifecycle, death → new run), `creation.py` (model-led chargen, budget + same-screen watchdog)
10. `logging/`: `recorder.py` + replay viewer (non-negotiable for debugging)

**Core principle**: tools are semantic, harness owns mechanics, model owns cognition. ML4 never emits raw keys — only validated symbolic tool calls.

**Dependencies**: third-party libs are fine if they make life easier. Prefer stdlib when it's sufficient, but don't hand-roll what a well-maintained package already does well.

## Docs

Detailed design specs for each component live in `docs/specs/`:
- `01-bridge.md` — Windows bridge (server, capture, input, framediff)
- `02-client.md` — WSL bridge client (socket protocol)
- `03-game.md` — game controller + screen detection
- `04-tools.md` — tool framework + all tool categories
- `05-perception.md` — screenshot cropping and downscaling
- `06-memory.md` — state, transcript, journal, map memory
- `07-agent.md` — prompts, schemas, LLM integration, decision loop
- `08-loop.md` — turn loop, phases, watchdog
- `09-run.md` — episode manager, character creation
- `10-logging.md` — recorder + replay viewer
