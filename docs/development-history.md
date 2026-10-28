# Development history: ML4 and Claude

## Who did what

| Period | Commits | Done with |
|---|---|---|
| 2026-10-20 → 10-27 | `ca5b807` … `4ee85a8` (48 commits, incl. 4 merges) | Mistral Large 4 through Mistral Vibe, directed by the repo owner |
| 2026-10-28 | `33586fa`, `525cbd8` and this documentation | Claude (Opus 5.5) in Claude Code |

The commits before `33586fa` are authored either as the repo owner or as "Vibe Nuage Agent". The repo
owner says they were all made with ML4. Human steering and edits in that period aren't separated in the
history, so "ML4's work" below means work done in ML4 sessions.

## What was done with ML4

### Phase 1: screenshot harness (10-20 → 10-25)

- **Design and research:** design specs for ten components (`docs/specs/`) and a Qud research brief
  (`docs/research/`).
- **Windows bridge:** window capture, input injection with several focus-stealing strategies and a
  PostMessage fallback, a log-region frame diff as the turn clock, and a WSL relay.
- **WSL side:** the full harness (game controller and screen detection, tool registry, perception,
  memory and journal, agent prompts and schemas, turn loop and watchdog, episode manager, recorder and
  replay viewer). Later reworked into "Pi-style" thin tools, then a raw-key "freeplay" mode.
- **Episodes and prompt tuning:** at least 15 recorded episodes plus many prompt iterations (anti-repeat
  warnings, flee rules, a "Joppa routine", lessons from deaths).
- **Best result:** 52 turns. In that run the model finished a conversation with Elder Irudad
  (`docs/findings.md`).
- **Where runs got stuck:** mostly the UI rather than the game. The model spammed Space in dialogue,
  got trapped in the Control Mapping menu, kept bumping into walls, and toggled look mode back and
  forth.

### Phase 2: in-game mod + MCP (10-26 → 10-27)

- **`c507df3`, the pivot:** a C# mod that runs a TCP server inside Qud and exposes structured state
  and semantic commands. It came with a Python agent stack (`mcp/`: client, tools, decide, loop, run,
  deploy, prompts) and architecture docs.
- **`ab4d1a0`, fixes from a code review:**
  - invalid JSON in the state;
  - a parameter name clash in `use_item`;
  - `cmdId` not echoed back;
  - writes and the accept loop that could block or busy-spin;
  - a publish throttle.
- **`8addef8`, `ba2be8d`, game controls:**
  - a pump thread so commands run during modal screens;
  - `close_menu` for uGUI screens, which call the screen's own Exit/Cancel/Hide because `PopGameView`
    froze the game;
  - all 8 `open_screen` screens;
  - `use_item` through `InventoryActionEvent` by reflection;
  - new actions for chargen, new game, continue, quit to menu, list saves and save;
  - numpad keys.
- **`48fa881`, `5658949`, saves and chargen:**
  - `chargen_auto` builds a random Classic character through the chargen module API;
  - `save_game` calls `XRLGame.QuickSave`;
  - `confirm_popup` calls the popup's callback;
  - `continue_game` through `LoadCurrentGame`. The commit message itself says this throws a
    NullReferenceException.
- **`4ee85a8`:** `mcp_server.py`, the stdio MCP server Vibe launches, with 26 tools.

## What Claude did

### `33586fa`: make the bridge usable

- **Popups and conversations:**
  - `PopupBridge` reads any modern popup or conversation and answers it in the game's own code.
  - The state shows the open popup.
  - World actions are refused while a popup is open.
- **Unfocused play:** the mod sets `Application.runInBackground`, so Qud keeps running without focus.
- **`continue_game`:** replays the real main-menu Continue flow (`Pick:Continue` plus the save list's
  completion source).
- **Turn detection:** reads the right message counter and also watches position, zone and HP.
- **New tools:** `go_to` (weighted pathing) and `get_map`.
- **Smaller fixes:** `xpNext`, the bogus day/hour fields, colour-coded item lookup, and equip being sent
  as "Apply". The MCP connection no longer drops after 30 s without traffic.

### `525cbd8`: from a playthrough to Red Rock (character level 5)

- **Item pickers:** container and item pickers are answerable as popups. Before this, auto-explore
  froze the game.
- **New tools:**
  - trading (`trade_list` / `trade_select` / `trade_offer`);
  - skills and attribute points;
  - firing missile weapons;
  - force attack, `rest` and `use_ability`.
- **`use_item`:** runs on the game thread with the right event overload and reports failures.
- **State fidelity:**
  - snapshots are built on the game thread, which fixes garbled names;
  - the markup stripper no longer deletes words;
  - stat glyphs are spelled out;
  - AV/DV/MA are correct;
  - only creatures in sight and explored cells are included.
- **Results for the model:** action results are compact, the low-HP warning popup is auto-dismissed,
  and turn waits settle properly.
- **Docs:** guide notes for other LLMs (`docs/qud_novice_notes.md`).

## Assessment of ML4

**In short:** ML4 was a productive scaffolder and made the key architectural call. But it repeatedly
verified that code ran rather than that it worked. When Claude started, an agent could not get through
a normal play session with the bridge: popups, saves, item use and turn detection were all broken in
ways the commit messages didn't show.

### What it did well

- **The pivot to an in-process mod with structured state.** The screenshot runs show the UI was the
  bottleneck: the best run lasted 52 turns, and most failures were key or focus problems. Moving to a
  mod was the right decision, and all later work builds on it.
- **Breadth.** In about a week it produced two complete architectures, specs, a replay viewer, a TCP
  protocol with framing and back-pressure, and reflection-based chargen and save code. Much of that
  scaffolding (`McpServer`, the command pump, `chargen_auto`, `save_game`, `open_screen`,
  `list_saves`) is still in use.
- **Clear commit messages.** Fixes are grouped and explained, and the code-review fix commit is easy to
  audit.

### Caveats it missed

1. **Tests checked the wrong thing.**
   - "All 13 in-game tests pass" covered opening and closing screens, moving and saving, not whether
     actions had their effect.
   - `5658949` reports "tested end-to-end: … continue_game → resume" while `continue_game` returned
     `ok: true` and threw a NullReferenceException in the game log.
   - `use_item` returned `ok` while eating and injecting silently did nothing.
   - `choose_option` sent the option number as a string, so the mod read 0 and every choice was
     refused.
2. **Key injection kept being used for the modern UI.**
   - Qud's uGUI popups, conversations and save list don't read the console keyboard queue. Most of the
     "agent gets stuck" behaviour traces back to this, in both phases.
   - `close_menu` force-hid popups, which cancels the task the game thread is waiting on and throws an
     error.
3. **Threading wasn't understood.** Qud has a Unity main thread, a separate game thread, and the
   bridge's pump thread.
   - Inventory actions were run on the wrong thread, where they throw NullReferenceExceptions.
   - State was built off the game thread, which garbled display names.
   - Calling `PopGameView` directly froze the game; that was found by trial and error.
4. **A stated requirement was missed.** `AGENTS.md` requires play without focus, but the game paused
   whenever it lost focus. Saves over the bridge timed out until Qud was clicked.
5. **The state looked fine but wasn't right.**
   - DV and MA were always 0, `xpNext` was 0, and the hour field said "Hour 225".
   - Turn detection read the wrong message counter, so actions returned stale positions.
   - The markup stripper deleted the text inside colour tags ("You harvest a  from").
6. **Hidden information leaked.** The state listed every creature in the zone, including ones behind
   walls, and drew unexplored cells as walls. That goes against the project's premise that the model
   sees what the player sees, and it misleads pathing.
7. **Missing play features.** There were no tools for containers, trading, skills or attribute
   points, ranged weapons, or attacking walk-over creatures. A level-5 character had 378 unspent skill
   points. `show_labels` was offered as a tool but always returned "not supported".
8. **The output was hard for an LLM to use.**
   - About 3k tokens of state per action.
   - The MCP connection dropped after 30 s idle, which is shorter than a model's thinking time.
   - Errors from the mod were swallowed.
9. **The code drifted apart.** It ended with three agent entry points: the screenshot loop, `mcp/run.py`
   and `mcp_server.py`. They partly duplicate each other's tools, and the docs were partly outdated
   (for example "take one step in-game to activate the mod").

Most of these were found only by playing real sessions: walking into containers, getting hurt, trying
to sell loot. The ML4 sessions tested features one at a time and never played a sustained session
through the MCP bridge.

### Fairness notes

- **Hindsight:** Claude started with ML4's working scaffolding and the failures it had already logged,
  which is an advantage.
- **Steering:** how much the human steered each ML4 session isn't visible in the history.
- **Claude's own gaps:**
  - The low-HP auto-dismiss was only tested against a fake connection.
  - `mcp/run.py`, ML4's own agent loop, was not updated or re-tested.
  - Claude also needed several fix-and-redeploy loops for bugs it introduced itself, such as a
    visibility check that hid every creature on the first try.
