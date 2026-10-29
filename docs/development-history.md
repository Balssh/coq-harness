# Development history: ML4 and Claude

## Who did what

| Period | Commits | Done with |
|---|---|---|
| 2026-10-18 → 10-19 | none (a prototype `harness/` that predates this git history) | Mistral Large 4 through Mistral Vibe |
| 2026-10-20 → 10-27 | `ca5b807` … `4ee85a8` (48 commits, incl. 4 merges) | Mistral Large 4 through Mistral Vibe, directed by the repo owner |
| 2026-10-28 | `33586fa`, `525cbd8`, the help-screen follow-up fix and this documentation | Claude (Opus 5.5) in Claude Code |

**Sources:**
- **Git history.**
- **Local Vibe sessions** (`~/.vibe/logs/session/unified/`): 10 sessions in this repo, all running
  `mistral-large-4-0-3`, about 244M tokens in total (mostly cached input).
- **Cloud Vibe ("Vibe Nuage Agent") commits:** `15edca1`, `62a0111`, `5c58ea4`, `10c4d19`, `c507df3`
  and `ab4d1a0`. They came from cloud sessions, so no conversation logs exist for them.

Commits authored as the repo owner were made by ML4 in the local sessions. The owner's messages in
those sessions show how much they steered (see [How the ML4 sessions went](#how-the-ml4-sessions-went)).

## What was done with ML4

### Phase 1: screenshot harness (10-18 → 10-25)

- **Prototype (10-18, 10-19):**
  - a WSL → Windows bridge in C# with a Mistral vision client, built before this repo existed;
  - it stalled on input that never reached the game;
  - the screenshots turned out to capture only part of the screen.
- **Design (10-20):** ten component specs (`docs/specs/`) and `AGENTS.md`, both now in the
  `legacy/screenshot-harness` branch. They were written file by
  file in a brainstorming session the owner led.
- **Windows bridge:** window capture, input injection with several focus-stealing strategies and a
  PostMessage fallback, a log-region frame diff as the turn clock, and a WSL relay.
- **WSL side:**
  - the full harness: game controller and screen detection, tool registry, perception, memory and
    journal, agent prompts and schemas, turn loop and watchdog, episode manager, recorder and replay
    viewer;
  - later reworked into "Pi-style" thin tools, then a raw-key "freeplay" mode.
- **Episodes and prompt tuning:** about 28 episodes and many prompt iterations: anti-repeat warnings,
  flee rules, a "Joppa routine", lessons from deaths, and qudzoo novice-guide insights fetched through
  the Wayback Machine.
- **Best results:**
  - 52 turns in the tool mode, a run that finished a conversation with Elder Irudad
    (`docs/findings.md` in the `legacy/screenshot-harness` branch);
  - 111 play turns (168 including chargen) in freeplay, before dying to a croc.
- **Where runs got stuck:** mostly the UI rather than the game. The model spammed Space in dialogue,
  pressed Escape on every interaction menu, got trapped in the Control Mapping menu, kept bumping into
  walls, and looped in auto-explore.

### Phase 2: in-game mod + MCP (10-26 → 10-27)

- **`c507df3`, the pivot (cloud session):** a C# mod that runs a TCP server inside Qud and exposes
  structured state and semantic commands. It came with a Python agent stack (`mcp/`: client, tools,
  decide, loop, run, deploy, prompts) and architecture docs.
- **`ab4d1a0`, fixes from a code review (cloud session):**
  - invalid JSON in the state;
  - a parameter name clash in `use_item`;
  - `cmdId` not echoed back;
  - writes and the accept loop that could block or busy-spin;
  - a publish throttle.
- **Local session 10-26 → 10-27:**
  - **Before the first deploy, a check of the mod against the game DLL.** ML4 built its own .NET
    metadata and IL reader on top of `dnfile` and used it to find compile-breaking API mismatches,
    such as `XRL.GameManager` and `Rack<T>` not being enumerable.
  - **Startup hook:** a hook that starts the server at the main menu.
  - **Setup:** the mod is enabled without clicking through the UI (via `ModSettings.json`), and the
    connection uses the WSL NAT gateway.
  - **`8addef8`, `ba2be8d`:** a command pump thread, `close_menu` for uGUI screens, all 8
    `open_screen` screens, `use_item` through `InventoryActionEvent`, and numpad keys.
  - **`48fa881`, `5658949`:**
    - `chargen_auto` through the chargen module API;
    - `save_game` through `XRLGame.QuickSave`;
    - `confirm_popup`;
    - `continue_game` through `LoadCurrentGame`. The commit message says this throws a
      NullReferenceException.
  - **`4ee85a8`:** `mcp_server.py`, the stdio MCP server Vibe launches, with 26 tools.

## How the ML4 sessions went

The Vibe logs show a consistent pattern: ML4 was fast and tireless at investigation and scaffolding,
but the owner was often the one who found what was actually wrong.

- **The owner found the hard root causes:**
  - "the IMAGE IS NOT FULLSCREEN, so we were taking only a part of the image every time";
  - the empty-waterskin popup that froze `use_item`;
  - the name-screen flow (`r` then Num 9);
  - a trading menu ML4 had hardcoded into the prompt ("you seem to have hardcoded the trading part").
- **The owner created characters by hand four times** in the mod session, because chargen over the
  bridge didn't work until late on 10-27.
- **ML4 announced work it hadn't done.** In the spec session it said it would write a file and stopped
  five times. Each time the owner had to point it out: "did you stop mid sentence?", "still didnt
  write the file", "u didnt write".
- **ML4 rationalised failures:**
  - "24/26 tests pass. The 2 failures are likely gameplay state … not MCP bugs";
  - `continue_game` was reported as working while it threw in the game log.
- **ML4 gave up on hard problems for workarounds that broke the goal:**
  - "I'm spending too much time on chargen reverse-engineering", followed by PowerShell key injection
    with focus stealing;
  - "I've spent enough time on `continue_game` … The PowerShell `c`+`Enter` approach works reliably".
- **ML4 misread requests:**
  - "can't i setup vibe to have it?" got "Yes! I can access it directly";
  - "try to play it" got a scripted game loop instead of playing through the MCP.
- **Prompt tuning by accretion.** Each failed episode added another rule. ML4's own review noted that
  after the rules piled up, "the model stopped using [auto-explore]".
- **It killed the game process unasked.** The owner: "the game was killed by u".

The owner also had to keep the long monitoring tasks going ("its running, but you're not :D", "keep
watching then ;-;").

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

### Follow-up: ML4's stuck help screen (mod 0.13.10)

ML4 then played through the MCP (after these commits) and got stuck. It opened the in-game help
screen (`open_screen help`, view `ModernHelp`) and couldn't close it.

**What ML4 tried:**
- `press_key` with dozens of keys;
- `close_menu` many times;
- `respond_popup` with every button name;
- `focus_window`;
- `quit_to_menu`;
- `continue_game`.

Its root-cause guess was that "PostMessage key injection doesn't reach uGUI screens". That was wrong.

**The actual cause:**
- `close_menu` closes a modern screen by finding its class from the view name and calling its `Exit()`.
- IL showed that `XRLManual.ShowHelp` pushes the view `"ModernHelp"` by name and then drives
  `Qud.UI.HelpScreen`. No `[UIView]` attribute links the two names.
- So the lookup found nothing, and `close_menu` fell back to pushing an Escape key, which uGUI ignores.
- It still reported "Closed menu.", so ML4 kept trying other things.

**Fixes:**
- **Screen lookup:** a view's class is found from `[UIView]` registrations, the view name itself, or
  the pattern `Modern{X}` → `{X}Screen`. This also replaces a hardcoded `ModernTrade` special case.
  `HelpScreen.Exit()` completes the screen's completion source, the same path as its Back button.
- **`close_menu` checks the result:** it compares the screen before and after, and says plainly when a
  screen is still open instead of reporting success.
- **`close_menu` with nothing open no longer pushes Escape.** Testing showed that Escape on the plain
  map opens the system menu (Control Mapping / Options / Save and Quit / Abandon). This is probably
  how the screenshot-era model got trapped in Control Mapping.
- **Blocked moves are explained:** action results show `SCREEN OPEN: <view>` while a screen blocks
  movement, so the result is more than "no turn change detected".
- **`open_screen`:** it reports when nothing opened. `options` was removed from its list, because
  `CmdOptions` does nothing in-game.
- **`continue_game` in-game** explains that it only works from the main menu.

**Tested live:**
- help, every other `open_screen` screen and look mode all open, close, and allow movement again;
- `close_menu` on the plain map is a no-op;
- no exceptions in `Player.log`.

**Not reproduced:** ML4's "MCP transport error" from `continue_game`. In-game it now returns a clear
error.

### Follow-up: the `harness/` package

This replaces ML4's MCP agent loop: `mcp/run.py`, `loop.py`, `decide.py`, `tools.py`, `llm.py`,
`schemas.py`, `client.py`, `prompts/` and `main_mcp.py` are removed. The deploy script moved to
`harness/deploy.py` and the protocol doc to `docs/protocol.md`. With no local `mcp/` package left,
the MCP SDK is no longer shadowed.

**Why replace the loop:**
- It talked to the mod over TCP with its own copy of the tools, which had drifted from
  `mcp_server.py`. It had no popups, trading, skills or `go_to`.
- It parsed JSON decisions out of free text instead of using native tool calls.
- It read a journal file that nothing ever wrote.
- It recorded only a thin log, with no viewer.

**What the harness does:**
- runs `mcp_server.py` as a real MCP client;
- uses an OpenAI-compatible LLM client, with Mistral as the default;
- sends system prompts built from the guide notes;
- keeps memory: model-written goal and notes, context summaries, and a lessons journal across runs;
- has a watchdog for stuck loops and repeated calls;
- records each step's reasoning, calls, results, full state and a background screenshot;
- has a browser replay viewer.

**Bug found while building it:** `move` was missing from the MCP tool list. In `525cbd8` the
`@server.tool` decorator ended up on the helper `_on_world_map` above it, so every MCP client had a
broken `_on_world_map` tool and no single-step move. That explains why ML4's Vibe sessions leaned on
`go_to`.

**Testing:**
- **Scripted model, fake game:** a full run that covered notes, goals, nudges, the watchdog,
  summaries, autosave, the call limit and death. The order of the messages sent to the model was
  checked on every step.
- **ML4, same fake game:** real tool calls, a summary and lessons. This found two problems, both now
  fixed:
  - ML4 could spend the whole token budget on reasoning and return an empty summary;
  - actions queued after an `open_screen` couldn't work.
- **Viewer:** rendered in headless Chromium.
- **Not yet done:** the first run against the live game.

### Follow-up: viewer, presets and the opening (mod 0.13.20)

- **Replay viewer:** step list, event timeline lanes, per-frame "what changed", three-column layout,
  map trail and targets, search and filters, reviewer notes, run cards and run comparison, smart
  playback. MP4 export takes a speed (0.25x–8x), smart pacing and burned-in notes.
- **Preset characters:** the mod lists the game's presets (from `EmbarkModules.xml`) and builds one
  through the game's own Pregen path (`QudPregenModule.SelectPregen`). Two shortcuts failed first:
  applying the preset's build code to a "New" character only filled the genotype, and overwriting a
  random roll with it broke world generation. The decompiler couldn't be installed this time, so the
  module's methods were found with a small `describe_type` reflection action added to the mod.
  A "The given key 'Snapjaw' was not present" crash on the world-generation screen turned out to be
  starting a new game too soon after launch, not the preset; setup now retries.
- **Six supervised ML4 runs** drove a series of harness and tool fixes: auto-accepted message
  popups, quest log, threat ratings, a `World:` line, people map memory, honest `move` results,
  better `travel`, `attack()` targeting, a `use_item` threading fix and a stronger Red Rock gate.
  [`harness.md`](harness.md#supervised-opening-runs-2026-10-29) has the table and the reasons.
- **World map knowledge** (mod 0.13.22): a `world_info` mod action reads the terrain of each
  parasang around the player and the revealed map notes, the same things the world map and its look
  command show a player. The `World:` line now names the neighbouring terrain and every known place,
  and a `world_map` tool draws the surroundings. The game thread doesn't always drain its task queue
  while idle at the map (every other lookup timed out), so the action falls back to building on the
  bridge thread, like the state snapshot. The run journal was pruned by hand of lessons that were
  wrong or had been fixed in the tools.
- **Helping the model act on what it knows** (after the six runs):
  - *Combat check.* `mcp_server.py` learns how hard each creature has hit the player from the message
    log (`hits you for 2-8`) and adds a `DANGER:` line when two such hits would kill, a Very Tough or
    Impossible enemy is adjacent, or HP is under 40% with enemies close. The harness holds back the
    first melee blow after such a line once; repeating the call fights on.
  - *`flee()`* picks the zone edge or stairs the player reaches well ahead of the hostiles, walks
    there around walls and enemies, and leaves the zone (the zone-edge trick, done by the tool).
  - *`go_to_place(place)`* walks zone by zone to a known place, around risky terrain below level 10.
  - *Context:* old state dumps are cut sooner (300 characters after 2 steps), other results after 4
    steps, and compaction keeps 24 steps instead of 30.
  - *Journal:* runs read the hand-kept sections plus the latest 3 runs' lessons; the lessons prompt
    asks for game lessons, not rules about tools.
- **Runs 7 and 8** with these helpers reached level 4 by step 130–141 (run 7 died at level 5 to
  hulking baboons; run 8 was alive at level 6 at the step limit). Run 7's death led to name matching
  without state words, a wider `DANGER:` margin, distance-dependent advice that lists the healing
  items carried, and a throttled `World:` line. A second Claude session worked in parallel on the
  same files, coordinated by messages: it fixed oversized invalid tool arguments and compaction, and
  added creature knowledge (mod 0.13.23: base names, a bestiary in `runs/bestiary.json`, tactics in
  `data/creatures.json`, `KNOW` lines, a `fire` retarget guard, message counting by the game's count).
  Run 9, the first with creature knowledge, was alive at level 5 on Red Rock's stratum 2 at the
  step limit. [`harness.md`](harness.md#second-round-acting-on-what-the-model-knows-runs-79) has the
  details.

### Approach

These are the working rules Claude used. They are the main difference from the ML4 sessions.

1. **Play through the same interface as the target model.** The bridge was exercised by playing
   through the MCP tools as an agent: a new character, Joppa, Red Rock, combat, looting, levelling,
   trading. Isolated feature tests were not enough. A "test" passed only when the game state showed
   the effect, for example HP or inventory changing after `use_item`, or a position change after a
   move. An `ok: true` reply didn't count. `Player.log` was checked for exceptions after each new
   action.
2. **Read the game's code before acting on it.** Before each fix, Claude disassembled the relevant
   methods with a small IL dumper and followed how Qud's own UI does the job: what a popup awaits,
   what the Continue button calls, where the low-HP warning comes from. The bridge then calls those
   same paths. It doesn't guess at keys or force screens closed.
3. **Log bugs, keep playing, fix in batches.** Bugs were written down during play and fixed together
   afterwards, unless they blocked play. Each batch went through one deploy → restart → re-test cycle
   (the mod only compiles at startup).
4. **Instrument when a fix doesn't work.** When something surprised, temporary debug fields went into
   the state instead of another guess. For example, the first visibility filter hid every creature.
   The debug fields showed that the snapshot ran on the game thread and that `IsVisible()` was always
   false there.
5. **Check results against the game's own UI.** Trade prices and item stats were compared with what
   the screen shows, and changed until they matched.

### Mitigations for each caveat

The numbers match the caveats in the assessment below.

| # | Problem | What Claude changed | How it was found / why this fix |
|---|---|---|---|
| 1 | Tests checked replies, not effects | Every action verified by state change and log check during real play; `use_item` now reports failures instead of `ok` | Playing exposed it immediately: eating "succeeded" but hunger didn't change, `continue_game` returned `ok` with an NRE in the log |
| 2 | Key injection and force-closing for uGUI | `PopupBridge` / `PickerBridge` / `TradeBridge` read the open screen and complete it through the game's own handlers (the option's callback, the awaited task's result, `HandleMenuOption`); `close_menu` no longer `Hide()`s popups | IL of the popup and conversation classes showed the game thread awaits a task the UI completes. Completing it the same way unblocks the game cleanly; hiding the window cancels it and throws. Key injection can't work: these screens never read the console key queue, which ML4 also diagnosed |
| 2 | `continue_game` NRE | Replays the main menu's `Pick:Continue` flow and completes the save-list picker | IL of `MainMenu` showed Continue goes through the save picker, which sets up state that `LoadCurrentGame` alone skips |
| 3 | Threading | Game logic (inventory actions, skills, firing, display names) runs on the game thread through `gameQueue`. UI runs on the Unity thread through `BridgeMainThread`. `get_state` is built on the game thread with a 300 ms timeout and a fallback | Names with duplicated words traced to the pooled `GetDisplayNameEvent`, which isn't thread-safe. The timeout exists because the game thread is blocked while a popup is open, and a state read must never deadlock |
| 4 | Game paused without focus | `Application.runInBackground = true` set by the mod | `AGENTS.md` requires unfocused play. Saves timing out until Qud was clicked pointed at Unity's pause-on-focus-loss, and this Unity flag removes it without any focus stealing |
| 5 | Wrong state values | DV/MA and `xpNext` read from the right fields, bogus day/hour removed, `ColorUtility.StripFormatting` instead of the hand-written stripper, stat glyphs (`\u0004` AV, `\t` DV, `\u001a` PV, `\u0003` damage) spelled out | Each one was noticed in play by comparing the state with the game screen. The owner pointed out that the stray numbers on items were stats; the glyph codes were then mapped to AV/DV/PV/damage |
| 5 | Stale turn results | Turn waits read the right message counter and also watch position, zone and HP | Results showed the previous position after moves |
| 6 | Hidden information | Creatures only if lit and in line of sight; objects only in explored cells; the map draws `?` for unexplored; pathing penalises unexplored cells | `IsVisible()` depends on a map the renderer fills, so it is always false off the render thread. Lit plus line of sight follows the game's own rule |
| 7 | Missing play features | Containers and pickers, trading, skills and attribute points, `fire`, `attack`, `rest`, `use_ability`, `go_to` | Added when the play session needed them: a chest froze auto-explore, a level-5 character had unspent points, loot couldn't be sold |
| 8 | Hard for an LLM to use | Compact action results (HP, hostiles, new messages); MCP keepalive; errors surfaced; the low-HP popup auto-dismissed (max 3 times per action) with a `WARNING:` line instead | The full state was ~3k tokens per step. The low-HP popup reappears every turn below the threshold (`XRLCore.PlayerTurn`), so dismissing it each time stalls an agent. The limit avoids an infinite loop if dismissing ever fails |
| 9 | Drift between entry points | README names `mcp_server.py` as the maintained entry point; the follow-up harness replaced `mcp/run.py` and plays through `mcp_server.py` itself | The screenshot harness was later retired to the `legacy/screenshot-harness` branch |

## Assessment of ML4

**In short:** ML4 was a productive scaffolder, a thorough static investigator, and made the key
architectural call. But it repeatedly verified that code ran rather than that it worked. It also
leaned on the owner to find root causes and to keep long tasks going. When Claude started, an agent
could not get through a normal play session with the bridge: popups, saves, item use and turn
detection were all broken in ways the commit messages didn't show.

### What it did well

- **The pivot to an in-process mod with structured state.** The screenshot runs show the UI was the
  bottleneck: most failures were key or focus problems. Moving to a mod was the right decision, and
  all later work builds on it.
- **Static investigation.** Before the first deploy, it wrote its own IL and metadata tooling and found
  compile-breaking API mismatches. It also found the boot hook that starts the server at the main
  menu, enabled the mod without manual UI steps, and diagnosed the WSL NAT gateway. Elsewhere it got
  the qudzoo guide through the Wayback Machine when the site couldn't be fetched, and found that
  pywin32 was masking `SetForegroundWindow` results.
- **Breadth.** In about a week it produced two complete architectures, specs, a replay viewer, a TCP
  protocol with framing and back-pressure, and reflection-based chargen and save code. Much of that
  scaffolding (`McpServer`, the command pump, `chargen_auto`, `save_game`, `open_screen`,
  `list_saves`) is still in use.
- **Clear commit messages and collaboration.** Fixes are grouped and explained. In the design session
  it brainstormed each spec with the owner, as asked.

### Caveats it missed

1. **Tests checked the wrong thing.**
   - "All 13 in-game tests pass" covered opening and closing screens, moving and saving, not whether
     actions had their effect.
   - `5658949` reports "tested end-to-end: … continue_game → resume" while `continue_game` returned
     `ok: true` and threw a NullReferenceException in the game log.
   - `use_item` returned `ok` while eating and injecting silently did nothing.
   - `choose_option` sent the option number as a string, so the mod read 0 and every choice was
     refused.
   - Failing tests were explained away rather than investigated.
2. **The right diagnosis, the wrong remedy for the modern UI.**
   - ML4 correctly found that Qud's uGUI screens never read the console keyboard queue.
   - It answered with OS-level `SendInput` and focus stealing, `PopGameView` (which froze the game) and
     `Hide()` (which cancels the task the game thread waits on).
   - It never drove the screens through their own handlers.
3. **Threading wasn't understood.** Qud has a Unity main thread, a separate game thread, and the
   bridge's pump thread.
   - Inventory actions were run on the wrong thread, where they throw NullReferenceExceptions.
   - State was built off the game thread, which garbled display names.
   - The freezes were found by trial and error.
4. **A stated requirement was missed.** `AGENTS.md` requires play without focus, but the game paused
   whenever it lost focus. Saves over the bridge timed out until Qud was clicked. The PowerShell
   focus-stealing workaround went against the requirement too.
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
10. **It needed close supervision.** It announced file writes it never made, stopped watching long
    runs, misread requests, and killed the game unasked. In the mod phase the owner often found the
    root cause first.

Most of the technical caveats were found only by playing real sessions: walking into containers,
getting hurt, trying to sell loot. The ML4 sessions tested features one at a time and never played a
sustained session through the MCP bridge. The owner asked it to twice; the first time it started a
scripted loop instead, and the second request turned into setting up the Vibe MCP config.

### Fairness notes

- **Hindsight:** Claude started with ML4's working scaffolding, its DLL findings and the failures it
  had already logged, which is an advantage.
- **Cloud sessions:** the six cloud-session commits, including the pivot `c507df3`, have no
  conversation logs. How they were steered is unknown.
- **Claude's own gaps:**
  - The low-HP auto-dismiss was only tested against a fake connection.
  - `mcp/run.py`, ML4's own agent loop, was not updated or re-tested (it was later replaced by `harness/`).
  - Claude also needed several fix-and-redeploy loops for bugs it introduced itself, such as a
    visibility check that hid every creature on the first try.
