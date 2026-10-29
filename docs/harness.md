# The harness (`harness/`)

The harness lets a language model play Caves of Qud on its own. It drives the model through the same
MCP tools that Vibe or Claude Code would use, keeps the model's memory across a long run, and records
everything so a run can be replayed and reviewed afterwards.

```
uv run python -m harness play --new-game --max-steps 200 --label first-try
uv run python -m harness replay
uv run python -m harness export 20261028-215600_ml4-live-1     # MP4 of a run
```

`uv run coq-play ...` is the same as `uv run python -m harness ...`.

## Architecture

```
            ┌──────────────────────── harness (python -m harness play) ─────────────────────────┐
            │                                                                                    │
  LLM API ◄─┤ llm.py  ◄──  agent.py: step loop  ──►  game.py (MCP client)  ──stdio MCP──►  mcp_server.py ──TCP──► Qud + mod
            │                 │        │    │                                                       │
            │           memory.py   recorder.py ◄── capture.py (PrintWindow screenshots) ◄──────────┘ (window)
            │                          │
            └──────────────────────────┼─────────────────────────────────────────────────────────────┘
                                       ▼
                       runs/harness/<run>/  ──►  replay.py + viewer/index.html (browser)
```

| Module | Role |
|---|---|
| `__main__.py` | CLI: `play` and `replay` subcommands |
| `agent.py` | The play loop, context building, compaction, watchdog, run setup and teardown |
| `llm.py` | Chat-completions client for OpenAI-compatible APIs (standard library only), provider presets, API key lookup |
| `game.py` | Starts `mcp_server.py` as an MCP stdio server, lists its tools, calls them, reads the raw state |
| `memory.py` | The model's goal and notes, "the story so far", and the cross-run lessons journal |
| `recorder.py` | Writes `meta.json`, `events.jsonl`, state snapshots and screenshots |
| `capture.py` | Background screenshots of the Qud window via a long-lived `powershell.exe` |
| `replay.py`, `viewer/index.html` | Local HTTP server and single-page replay viewer |
| `video.py` | Renders a run to MP4 (Pillow frames piped to ffmpeg) |
| `prompts/` | `system.md` (system prompt), `summarize.md` (context compaction), `lessons.md` (end of run) |
| `deploy.py` | Copies `mod/` into Qud's Mods folder (`python -m harness.deploy`) |

### Why it goes through MCP

ML4's earlier loop (`mcp/run.py`, removed) talked to the mod over TCP with its own copy of every tool.
That copy drifted: it never got popups, trading, skills or `go_to`. The harness instead launches
`mcp_server.py` and uses its tool list as is, so:
- a fix to a tool helps every client at once;
- runs through the harness are comparable with runs through Vibe or Claude Code.

## A run, start to finish

1. **Connect:** start `mcp_server.py` over stdio, list its tools, and build the function schemas.
   Some tools are hidden from the model (`HIDDEN_TOOLS` in `game.py`):
   - saving, loading, character creation and quitting belong to the harness;
   - `choose_option` and `confirm_popup` duplicate `respond_popup`;
   - `press_key`, `focus_window` and `look` are legacy key injection or a modal look mode.

   The memory tools (`note`, `forget_note`, `set_goal`) are added on top.
2. **Set up the game** (`_ensure_in_game`):
   - **Already playing:** keep that game, unless `--new-game` is set. Then it dismisses any open
     popup and calls `quit_to_menu`, which saves and leaves through the system menu's "Save and
     Quit" (passing one turn first if the new-game world-generation view is still up).
   - **At the main menu:** `continue_game`, or a new game with `--new-game`. If continuing fails, it
     falls back to a new game.
   - **New game:** pick the character (below), then `start_new_game` and `chargen_auto`. Right after
     Qud launches, the menu can ignore `start_new_game`, and world generation can fail because the
     game's data is still loading ("The given key 'Snapjaw' was not present"), which drops back to
     the main menu. Both are retried, up to three times.
   - **In character creation:** `chargen_auto`.
3. **Character** (`--character`, default `choose`): the harness lists the game's nine preset
   characters (`chargen_presets`, read from Qud's `EmbarkModules.xml`) and asks the model to pick
   one, with `random` allowed. The prompt (`prompts/character.md`) steers it toward presets marked
   most or highly survivable and toward simple fighters, and includes the lessons journal. The
   choice and its reason are recorded as a `setup` event. `--character random` or
   `--character "Marsh Taur"` skip the question. In the mod, a preset goes through the game's own
   path (character type "Pregen", `QudPregenModule.SelectPregen`), so it builds exactly like picking
   it in the menu, starting in Joppa.
4. **Opening:** the first user message is the full `get_state` text. For a brand-new character
   (level 1, no XP) it adds "Follow the Opening plan", and the goal starts as the opening plan
   until the model sets its own.
5. **Steps** until a stop condition (below).
6. **Teardown:**
   - save, unless the character died;
   - ask the model for lessons and append them to `runs/journal.md`;
   - finish `meta.json` and close the screenshot helper.

### One step

1. Build the context: system prompt + memory, then the opening message, then the recent steps.
2. Call the model with all tools. The tool choice is `any` for Mistral and `required` for others, so a
   tool call is mandatory.
3. Record the response:
   - the text: the model is asked for one or two sentences of visible reasoning;
   - the hidden reasoning: Mistral `thinking` chunks, or `reasoning_content`;
   - the tool calls, token usage and latency.
4. Run the tool calls in order, at most 4 per step:
   - **Memory tools** are handled in the harness.
   - **Game tools** go to the MCP server. After each one the harness takes a snapshot: the full raw
     state plus a screenshot.
   - **Popup or screen opened:** once a call leaves a popup or a non-map screen open, the remaining
     game calls in that response are not run, unless they work on popups and screens
     (`respond_popup`, `close_menu`, trade and skill tools, `get_state`, `get_map`). The model gets
     "Not run: a popup is open; answer it first." Every tool call id still gets a tool message, which
     the APIs require.
   - **Death** ends the step and the run.
5. **Hints:** a zone change adds a hint to the last tool result ("You are now in a new zone…").
   Entering a gated zone below its level (`ZONE_GATES`: Red Rock before level 2) adds a
   `CAUTION` nudge to go back and level up near town.
6. **Watchdog**, then compaction if needed.

### Stop conditions

- **Death:** `isDead`, a "you died" popup, or HP ≤ 0 in game.
- **Limits:** `--max-steps` (default 300) or `--max-minutes`.
- **Ctrl-C:** stops cleanly after the current step; a second Ctrl-C aborts.
- **API errors:** three in a row. Transient HTTP errors (429/5xx) are already retried with backoff
  inside `llm.py`.

## Context and memory

The model's context is always `[system prompt + memory] [opening] [steps…]`.

- **System prompt** (`prompts/system.md`), assembled once per run:
  - the objective (`--objective` overrides the default);
  - how a turn works;
  - a priority list for every turn: popup → open screen → danger → heal → spend level-up points →
    progress;
  - an opening plan for a new character: learn the character, sweep Joppa (explore, talk to every
    named villager, take the quests), gear up at the merchants, level up on weak creatures near
    Joppa until level 2, and only then go to Red Rock;
  - exploration habits: `auto_explore` until done (it stops when a hostile comes into view, so it's
    also the safe way through dangerous zones), then NPCs, containers and stairs, then leave the
    zone; prefer `go_to` to many single moves;
  - the whole of `docs/qud_novice_notes.md`, so game knowledge lives in one file shared with other
    clients;
  - from `runs/journal.md`: every hand-kept section (a `##` heading that doesn't start with a
    date and run id) plus the lessons of the latest 3 runs, at most ~4000 characters. Older run
    lessons age out instead of piling up, since the model's own lessons are often wrong.
- **Memory block:** appended to the system prompt every step, so it is never lost.
  - **Goal:** set by `set_goal`.
  - **Notes:** numbered, written by `note` and removed by `forget_note`. At most 40 notes of 300
    characters each; the oldest is dropped first.
  - **The story so far:** written during compaction.
  - **Named people seen in this zone:** kept by the harness. The game state lists creatures only
    while they are in sight, so after each snapshot the harness records every named (capitalized),
    non-hostile creature's position per zone, e.g. "Mehmet (42,19); Tam, dromad merchant (70,19)".
    Without it the model spent many steps looking for villagers it had already seen.

  It sits at the end of the system message rather than in a separate message because Mistral is
  strict about message order (no user message straight after a tool message). The fixed part of the
  prompt stays first so providers can cache it.
- **Recent steps:** kept verbatim, except that old tool results are cut: state dumps (`get_state`,
  `get_map`, `world_map`, `trade_list`, `list_skills`) to 300 characters after 2 steps, everything
  else to 600 characters after 4 steps. In run 6 those dumps were most of the ~12.5k prompt tokens a
  step.
- **Compaction:**
  - Triggers when there are more than `--keep-steps` steps (default 24) or the context passes about
    160k characters.
  - The oldest steps are rendered as a plain transcript, keeping the newest `keep_steps/2`. The model
    rewrites "the story so far" from the previous summary plus that transcript (`prompts/summarize.md`,
    at most 250 words), and the old steps are dropped.
  - Text-only calls like this get an 8000-token budget and one retry, because a reasoning model can
    spend a smaller budget entirely on thinking and return no text. That happened with ML4 in testing.
- **Lessons:**
  - At the end of a run of 5+ steps, the model writes 3–6 one-line lessons from its last 25 steps
    (`prompts/lessons.md`).
  - They go into `runs/journal.md` under a header with the run id, model, outcome and level. The file
    is plain markdown, so you can edit or prune it; lessons worth keeping for good go under a
    heading of your own, which every run reads.
  - The prompt asks for lessons about the game and decisions, and to describe odd tool behaviour
    rather than turn it into a rule: earlier runs wrote "travel only works from zone edges" when
    the cause was hostiles in view.

## Guards

| Guard | Trigger | Effect |
|---|---|---|
| No tool call | response without tool calls | user message: "You must call at least one tool every turn…" |
| Stuck | same zone, position, HP, turn counter, screen and popup for 8 steps | `WATCHDOG:` hint appended to the last result |
| Repeat | the same call with the same arguments and the same outcome 5 times in a row | `WATCHDOG:` hint |
| Walking | 6 steps in a row of only `move`/`get_map` with no hostile in sight | `TIP:` to use `go_to` or `auto_explore` |
| Combat check | `attack`, or a `move` into an adjacent hostile, while the latest result had a `DANGER:` line (at most once per 3 steps) | not run; the model gets the danger and is told that repeating the call fights on, otherwise heal now (stepping away from an adjacent enemy gives it free hits) and `flee()` only with a head start |
| Zone gate | entering a `ZONE_GATES` place below its level (Red Rock before level 2) | a `CAUTION:` on each gated zone entered (once per zone) |
| Message popups | a call leaves a popup with no options, no text input and at most an Accept/OK button | accepted for the model (chains up to 8); the result lists their text under `[harness] Message popup(s) accepted for you`. If the call itself was refused because of the popup, it is run again. Recorded as `auto_popup` events |
| Call limit | more than 4 calls in one response | the extras are answered "Not run" |
| Popup or screen | calls queued behind a popup or screen | answered "Not run: …" |
| Autosave | every 50 steps and at the end | `save_game` (not shown to the model) |

## Recording

Each run is saved to `runs/harness/<YYYYmmdd-HHMMSS>_<label or model>/`; `runs/` is git-ignored.

| File | Contents |
|---|---|
| `meta.json` | model, base URL, provider options, objective, tool list, start/end, outcome, steps, token totals, final HP/level/zone |
| `system_prompt.md` | the exact system prompt of the run (without the memory block) |
| `events.jsonl` | one JSON object per line: `type`, `t` (seconds since start), `step`, and fields per type |
| `states/NNNNN.json` | the full `get_state_raw` after each game action (snapshot N) |
| `frames/NNNNN.jpg` | screenshot of the Qud window at snapshot N (JPEG, up to 1280 px wide) |

Event types:
- **`run_start`, `setup`:** the start of the run and each setup action (quit, new game, chargen,
  continue).
- **`snapshot`:**
  - `index` and `label` (the tool that caused it);
  - `frame`, which is null without a screenshot;
  - HP, level, XP, position, zone, screen, popup, turn counter and death flag.
- **`llm`:** `text`, `reasoning`, `tool_calls`, `usage`, `latency`, `finish`.
- **`tool`:** `name`, `args`, `result`, `is_error`, `latency`, and `snapshot` (the snapshot it
  produced).
- **`memory`:** goal, notes and summary after every change.
- **`summary`:** compaction, with the number of dropped steps and the new summary.
- **`nudge`:** `kind` is one of `no_tool`, `stuck`, `repeat`, `zone`, `gate` or `walking`.
- **`auto_popup`:** the text of message popups the harness accepted for the model.
- **`autosave`, `lessons`, `error`, `run_end`.**

**Screenshots** come from a single `powershell.exe` started from WSL. It loops on stdin, finds the
`CoQ` window and renders it with `PrintWindow(PW_RENDERFULLCONTENT)`. That works while the window is
behind other windows and never takes focus. The process is DPI-aware so the window isn't cropped.

- **Cost:** about 0.1 s per frame after a one-second start-up.
- **Limitation:** a minimized window can't be captured. The run continues, and an `error` event notes
  it once.

## Replay viewer

`uv run python -m harness replay` serves `runs/harness/` on `http://localhost:8765/` and opens the
browser. Press `?` in the viewer for the keyboard shortcuts.

- **Run list:** one card per run with:
  - the last screenshot (the first one on hover) and an outcome badge (`died`, `running`,
    `unfinished` for a run that stopped without an end);
  - steps, max level, zones visited, duration, tokens and harness nudges;
  - an HP sparkline, the zones in order, and the number of reviewer notes.
- **Compare:** tick two cards and press Compare (`?compare=<a>,<b>`). It shows both last frames, a
  table of the numbers above (the better value in green where better is clear), both HP curves on
  one chart, tool-call counts side by side and the zones each run visited. The server computes
  these numbers from `events.jsonl` and caches them until the file changes.
- **Run view:** one screen on a wide display, in three columns:
  - **Step list:** one line per step, with its tool calls (`move×3`), the start of the model's text,
    the HP change, and icons for death, error, nudge, popup, zone change, level-up, context summary
    and reviewer note. Fights and damage have a coloured edge. Click a line to jump there.
    - **Search** covers thoughts, reasoning, call arguments and results, nudges and notes, and
      highlights the match.
    - **Filters:** fights, nudges, errors, popups, zones and notes. With a search or filter
      active, `[` and `]` jump between matching steps, and the timeline marks them.
  - **Game:** the screenshot, the map, or both side by side (`V`).
    - The map shows the last 40 positions in the zone as a trail. Long moves from `auto_explore`
      or `go_to` are drawn dashed and faint.
    - The frame's call target is marked with a line and crosshair: `go_to`, `fire` and
      `use_ability` coordinates, and the cell an `attack`, `move` or `interact` direction points to.
  - Under the game: stats, an HP bar that turns red below 35 %, the latest messages with new ones
    highlighted, and **what changed** since the previous frame. Changes covered: HP, level, XP,
    zone or distance moved, items and effects gained or lost (by base name, so a waterskin
    losing a dram doesn't count), goal changed, notes added or removed, context summarized and
    popup opened.
  - **Model:** the step's tags, latency and tokens; thinking (collapsible); the text; and every
    call with its result. The call that produced the current frame is outlined; click another
    call to show its frame. Nudges, summaries and errors follow, then the reviewer note and the
    memory at that moment (newly added notes in green).
- **Timeline:** the HP curve plus one lane each for damage, fights, popups, zone changes, nudges,
  summaries, errors, level-ups and reviewer notes. A red line marks death. Hovering shows that
  frame's screenshot, step, HP, tags, call and text; click to seek. `[` and `]` jump to the
  previous or next event.
- **Reviewer notes:** write a note on any step (`A`, then Ctrl+Enter or click away). Notes are
  saved to `runs/harness/<run>/annotations.json` through `POST /api/annotate`, keyed by step;
  an empty note deletes it. They appear in the step list, the timeline and, if you choose, the
  MP4.
- **Playback:** Space plays at 0.5× to 10×. **Smart playback** (`S`) uses the MP4 export's pacing
  rule, below.
- **Keys:** ←/→ frame, Shift+←/→ or J/K step, `[`/`]` event, Home/End, `/` search, `V` view,
  `S` smart, `A` note, `L` step list, `E` export, `T` theme (auto, dark or light), `?` help.
- **Layout:** below 1400 px the step list becomes a drawer (`☰ Steps` or `L`). Below 900 px
  everything stacks into one column: game, stats, step, note, messages, memory, timeline.
- **Links:** the address bar follows the current frame, so `?run=<id>&frame=N` can be copied as a
  link to that moment.
- **Live runs:** a run still in progress is polled every 3 s, and "follow live" keeps the view on
  the newest frame.

## MP4 export

```
uv run python -m harness export <run> [--speed 2] [--smart] [--annotations] [--seconds-per-frame 1.0] [--out file.mp4]
```

The viewer's **Export MP4** menu (`E`) does the same on the server, shows progress, and lists
every export of the run for download. It also estimates the video length for the chosen settings.

- **Speed:** each snapshot is shown for `seconds-per-frame / speed` seconds (the default is 1 s).
  The viewer offers 0.25× to 8×.
- **Smart pacing** multiplies each frame's time by what happened in it:
  - death 3×;
  - damage, fights and frames with a reviewer note 2×;
  - level-ups 1.75×;
  - zone changes 1.4×;
  - popups, nudges and errors 1.25×;
  - idle frames 0.3×. A frame is idle when it is a look at state or map, a memory call or a
    `wait`, and nothing (position, HP, zone, popup) changed.

  The rule is `frame_kinds()` and `pace()` in `video.py`, and the viewer has a copy for smart
  playback. On the first live run it gives 4:09 at 1× instead of 3:48, with fights slower and
  idle stretches faster.
- **Annotations** (`--annotations`, or "Burn in reviewer notes") draws each step's note as a
  yellow banner over the screenshot.
- **File names** encode the settings so exports sit side by side:
  `replay_<speed>x[_smart][_notes].mp4` in the run directory.
- **Frames:** 1920×1080, drawn with Pillow:
  - the header (run, model, step, time);
  - the game screenshot;
  - an HP bar and stats;
  - the map with the movement trail;
  - the step panel: "what changed" badges, thinking, the model's text, the tool calls with the
    current call's result, and harness nudges;
  - memory (goal and notes);
  - the latest messages, with new ones highlighted;
  - the timeline: the HP curve, the same event lanes as the viewer, and a cursor.
- **Encoding:** frames are piped to `ffmpeg` (libx264, CRF 23, `-tune stillimage`), which must be
  on PATH. Each picture is written once per output frame it covers, at 10 fps (up to 30 fps when
  frames are shorter than 0.1 s).

  The first live run (228 frames) took about 30 s to render at 2× (1:54, 12 MB) and about 40 s
  with smart pacing at 1×.

## Models

Defaults:
- **provider:** `mistral`;
- **model:** `mistral-large-4`;
- **API key:** `MISTRAL_API_KEY` from the environment, then the repo's `.env`, then `~/.vibe/.env`.
- **Reasoning:** `reasoning_effort: "high"`. Left to choose, ML4 skipped reasoning on 164 of 208
  steps in the first live run. With `high` it reasoned on every step of a test run, at 1.5–9 s per
  step. `--reasoning medium|low|none` changes it, and `--reasoning default` sends nothing.

Other OpenAI-compatible APIs:
```
uv run python -m harness play --provider openai --model <id>                 # OPENAI_API_KEY
uv run python -m harness play --provider openrouter --model <vendor/model>   # OPENROUTER_API_KEY
uv run python -m harness play --provider local --base-url http://localhost:8000/v1 --model <id> --key-env LOCAL_KEY
```

- `--extra-body '{...}'` is merged into every request, for provider options such as reasoning effort.
- `--temperature` is passed through as given.
- A provider that isn't OpenAI-compatible needs a new client with the same `chat(messages, tools,
  max_tokens) -> Reply` interface.

## How it was tested

- **Scripted model, fake game:** the real `mcp_server.py` tool list with simulated results, run for
  40 steps. It covered:
  - notes, goal and forgetting notes;
  - the no-tool nudge, the watchdog and summaries;
  - autosave and the call limit;
  - death detection and lessons.

  Before every model call, the test checked that every tool call has exactly one following tool
  message and that no message is out of order.
- **ML4, fake game:** short runs, which confirmed that Mistral accepts the message format, including
  multiple calls per step, summaries and lessons. Two problems found there are fixed:
  - empty summaries when reasoning used up the token budget;
  - actions queued after `open_screen`.
- **Screenshots:** captured from the real window while it was in the background.
- **Viewer:** rendered in headless Chromium at desktop and phone widths.
- **Live game:** see the first live run below.

## First live run (`20261028-215600_ml4-live-1`)

Replay it with `uv run python -m harness replay 20261028-215600_ml4-live-1`.

**The run:**
- ML4 (`mistral-large-4`), new random character Shwumir (12 HP, Freezing Ray, Force Bubble, short
  bow).
- Died at step 208 after 21 minutes, still level 1 with 50 XP.
- 1.9M prompt tokens and 52k completion tokens. That's about 9k prompt tokens per step; the context
  was summarised 12 times.

**What it did:**
- **Steps 1–66, Joppa:**
  - auto-explored the village;
  - took Mehmet's watervine quest, Argyve's knickknack quest and Irudad's "O Glorious Shekhinah!";
  - noted where every NPC is;
  - bought gear from a merchant (leather armour, arrows) and equipped the bow.
- **Steps 67–105:** north through the outskirts and the salt marsh to Red Rock. A shrine on the way
  gave it the "Visit Kiwan!" quest, which it noted.
- **Steps 105–208, Red Rock surface:**
  - got into a fight with a "goat and qudzu symbiote" (15 HP, 2–3 damage per hit) and fell to 4/12 HP;
  - escaped and healed with witchwood bark;
  - noted that symbiotes are too tough and that it should level on baboons first;
  - later auto-explored back into the same goat, was ambushed while bleeding, and died zig-zagging
    across a zone edge (the "zone-edge trick" from the guide) with the goat next to it.

**What worked in the harness:**
- 228 snapshots, all with screenshots;
- no crashes and no API failures;
- popups and conversations handled throughout;
- notes and goals used sensibly;
- summaries kept the context at about 10k tokens;
- death detected, and lessons written to the journal.

**Problems found, and their status:**
- **`travel` at a zone edge did nothing.** ML4 spent 6 steps at y=0 calling `travel north`. Fixed:
  at the edge it now steps into the next zone.
- **The repeat watchdog fired on ordinary walking,** five `move north` calls that each moved. Fixed:
  it now needs the same call *and* the same outcome. (The live run used the old code, so its replay
  shows these nudges.)
- **Targeted abilities weren't supported.** `use_ability("Freezing Ray")` opened the targeting screen
  (`PickTarget`), which no tool could answer; ML4 lost 3 steps and got hit. Fixed:
  - `use_ability(name, x?, y?)` answers the targeting screen through the mod's new `pick_target`
    action, aiming at (x, y) or the nearest visible hostile.
  - `pick_target` pushes the mouse events the picker reads. It sends `PointerOver` twice, because
    the first only switches the picker to mouse mode, then `LeftClick`.
  - Out-of-range targets are cancelled rather than left open.
  - Tested live with Proselytize on Mehmet.
- **Zone-change hints were noisy** when crossing a zone edge back and forth (13 of the 19 nudges).
  Minor.
- **Visible reasoning was sparse.** ML4 wrote visible text in 32 of 208 steps and returned
  `thinking` in 44. Fixed: Mistral runs now default to `reasoning_effort: high` (see Models).
- **The end-of-run save could corrupt a save.** After a failed setup it saved on the
  world-generation screen. Now it only saves after at least one step and outside menus or loading
  screens.
- **Starting a new game needed three fixes:**
  - the MCP `quit_to_menu` couldn't save (the game ignores the "save first?" answer), so it now uses
    the system menu's Save and Quit;
  - after the embark popup, Qud keeps the world-generation screen until a turn passes. A
    `close_menu` there aborted to the main menu. Setup now passes one turn, and `close_menu` refuses
    on that screen.
  - at the main menu, the state still shows the last game's player, so setup checks for the menu
    first.

  `runs/harness/20261028-214426_aborted-worldgen-bug` is the aborted attempt that showed the second
  problem.

**On the model:** ML4 played sensibly in town and managed its quests and notes well. In combat it
didn't follow its own notes: it re-entered the zone it had marked dangerous and auto-explored there
at low HP. The lessons it wrote say exactly that, and later runs will see them in the journal.

## Supervised opening runs (2026-10-29)

Six new-game runs of ML4, each changing the harness based on what the previous ones showed. The goal
was a better start: sweep Joppa, take the quests, gear up, level on weak creatures, and only then
go to Red Rock, the way a careful human (or Claude, playing through the same tools) does it.

| Run | Character (model's pick) | Result | Levels reached (step) | Notes |
|---|---|---|---|---|
| `ml4-opening-1` | Praetorian Prime | step limit 250, alive | 2 (137) | Good Joppa sweep and quests; 85 single `move`s and 55 `respond_popup`s, mostly plain message popups |
| `ml4-opening-2` | Praetorian Prime | died at 118 | 4 (83) | Fast start; engulfed by a gelatinous frustum (70 HP) it had called "too dangerous" |
| `ml4-opening-3` | Praetorian Prime | step limit 300, alive | 2 (120), 3 (199) | Ground glowfish for 150 steps; got lost heading east when Joppa was west |
| `ml4-opening-4` | Gunwing | died at 127, level 1 | – | Kept going into Red Rock past the one-time CAUTION; moves that silently failed while it was surrounded; killed by a hulking baboon |
| `ml4-opening-5` | Praetorian Prime | died at 222 | 2 (108), 3 (119), 4 (205) | Obeyed the gate; level 4 around Red Rock; left via the world map, where `travel` failed and `go_to` walked it into a jungle |
| `ml4-opening-6` | Praetorian Prime | step limit 300, alive | 2 (123), 3 (156) | First run with every fix below. Hunted baboons at range (incl. [Tough] ones), escaped hulking baboons, found an artifact and finished Argyve's quest; spent its last ~50 steps trying to hand in a snapjaw corpse as the watervine vermin (the notes now say girshlings) |

**What changed, and why:**
- **Preset characters** (all runs): the model picks from the game's presets; it chose Praetorian Prime
  ("most survivable") five times out of six.
- **Opening plan** in the system prompt, a seeded goal for new characters, and the Red Rock gate
  (run 1). The gate's level went from 3 to 2 after run 3 spent 150 steps grinding, and became a
  warning on every gated zone after run 4 walked past the single one.
- **Message popups accepted by the harness** (after run 1): 30–50 popups per run no longer cost a
  step each. A call refused because such a popup appeared is run again (seen in run 2's first try).
- **Quest log in the state** (after run 1, where the model spent steps looking for it), and
  **people map memory** (after run 2's search for villagers).
- **Threat ratings** on every creature (after run 2's frustum).
- **`World:` line** with zone coordinates and the way to Joppa and Red Rock (after run 3), and a
  world-map version with parasang coordinates (after run 5). Since then it is built from the game's
  world map instead of two hardcoded landmarks: the terrain of the four neighbouring parasangs and
  the direction to every place the character knows (named terrain and revealed map notes). The
  `world_map` tool shows the surroundings as a letter grid with each terrain's look description.
- **`travel`** steps into the next zone itself, walks around terrain in the way, says when hostiles
  stop it, and steps one parasang on the world map (runs 3 and 5).
- **`move`** says when the move didn't happen, or that it was a bump attack (run 4).
- **`attack()`** without arguments hits the adjacent hostile, or `attack(x, y)` (run 3's direction
  mix-ups).
- **`use_item`** looks the item up on the game thread, which fixes an intermittent "Index was out of
  range" crash, and accepts `use` (run 3).
- **Setup:** retries a new game when world generation fails right after Qud launches, passes the
  world-generation screen before `quit_to_menu`, and gets past a previous character's death screens.
- **Walking tip** after 6 steps of single moves with nothing hostile in sight.
- **Notes:** the watervine vermin are girshlings in the caves under Red Rock; other corpses don't
  count (run 6).

**Still weak:** combat judgment at low level (two of the three deaths were fights the model itself had
called too dangerous), long-range navigation, and multi-step quest logic. The harness can give the
model the facts (ratings, directions, quest steps), but it still has to act on them. Each run costs
roughly 1.5–4M prompt tokens for 120–300 steps.

### Second round: acting on what the model knows (runs 7–9)

After the six runs, the harness added tools and checks aimed at the remaining weak spots: a combat
check, `flee()`, `go_to_place()`, world-map knowledge, shorter old results and an aging journal
(see the guards table and the [protocol tool list](protocol.md#available-tools)).

| Run | Character (model's pick) | Result | Levels reached (step) | Notes |
|---|---|---|---|---|
| `ml4-opening-7` | First Gardener | died at 178 | 2 (96), 3–4 (130), 5 (167) | Clean opening: swept Joppa, took both quests, traded for armor and a long sword. The combat check held back one blow at 8 HP against a croc at 2/13 HP; the model finished it, which was right. `go_to_place` took it between Joppa and Red Rock. Killed by two hulking baboons it shot at while they closed in; it crossed a zone edge at 8 HP and one followed it |
| `ml4-opening-8` | Gunwing | step limit 250, alive | 2 (100), 3 (116), 4 (141), 5 (165), 6 (188) | Fought at range throughout (127 `fire` calls); `go_to_place` six times between Joppa and Red Rock. Sold its bandages for ammo; with akimbo revolvers each shot costs two slugs |

| `ml4-opening-9` | Praetorian Prime | step limit 250, alive | 2 (77), 3 (111), 4 (120), 5 (143) | First run with creature knowledge (mod 0.13.23): `KNOW` lines in 14 results, one shot held back by the `fire` guard. Used `go_to_place` 8 times, `flee()` and `world_map` once each; ended on Red Rock's stratum 2, short of the girshlings on stratum 4 |

All three reached level 4 by step 120–141; of the first six runs, only two got there, at steps 83
and 205. Runs 7 and 8 never used `flee()` or `world_map` (the model walked off zone edges by hand);
run 9 used each once. Average prompt per step: 13.4k tokens in runs 7 and 8, 12.3k in run 9.

**What run 7 changed:**
- **Hit memory** treated "bloody hulking baboon" as a different creature from "hulking baboon", so the
  `DANGER:` line came late. Names are now matched without state words. The other session's
  bestiary (below) replaced this matching with the game's base name.
- **`DANGER:` threshold** raised from two of a creature's hardest hits to three, and then to two of
  its worst rounds: a hulking baboon took 8 HP in one round when the line still said there was room.
- **Advice depends on distance.** Turning your back on an adjacent enemy gives it free hits, so the
  line now says to heal (listing the healing items carried) or finish it when it's nearly dead, and to
  `flee()` only with a head start. Run 7 died with a salve injector and three witchwood barks unused.
  The system prompt also says never to sell healing items.
- **The `World:` line** appears in a result only on entering a zone and on every 10th result, since
  it repeated in every result.
- **Invalid tool arguments** (a reply that hit the token limit produced a 158k-character argument)
  are cut to a 300-character preview, and size-triggered compaction drops enough steps to get under
  70% of the limit; run 7 had re-summarized on every step from 82 to 97.
- **Place names** that differ only by an article ("the Sumur Neighborhood") are listed once, and
  `fire(x, y)` no longer accepts the player's own cell.

**Creature knowledge** (mod 0.13.23, done by a second Claude session in parallel):
- **Base names.** Creature cells carry `baseName`, the name without state words like "bloody" or
  "wounded".
- **Bestiary.** `mcp_server.py` keeps a bestiary per kind of creature in `runs/bestiary.json`
  (`COQ_BESTIARY` overrides the path), learned from the message log. It records:
  - every hit on the player, and damage per round;
  - HP;
  - kills, with the player's level;
  - deaths, with the level;
  - total damage taken.

  It was seeded from the saved states of all earlier runs.
- **Tactics.** Hand-written tactics for common early creatures are in `data/creatures.json`.
- **`KNOW` line.** The first time a kind of creature appears in a zone, the result gets a `KNOW <kind>:`
  line with its tactic and the record, e.g. "hits you for 1-9; you killed 1 (at level 5); it killed
  you 1x (at level 5)".
- **`fire(x, y)` on an empty cell** aims at the nearest hostile within 2 tiles, or doesn't fire. Run 7
  spent 12 of 36 arrows on empty cells.
- **New-message tracking** uses the game's message count instead of comparing message windows. A stale
  snapshot had made 40 old messages look new.

**After run 9:**
- **`fire` reports what the shot did**, from the shot's own messages: whom it hit and for how much,
  whether it died, a miss, a hit that didn't get through armor, or terrain in the line of fire.
  Before, kills and shots into rock both read "[nothing there]" (13 of run 9's 44 shots), and the
  model wrote the false lesson that `fire()` shoots at empty terrain.
- **`fire` no longer says "Out of ammo" after a successful reload** (6 times in run 9 while carrying
  about 50 slugs).
- **`travel` is more robust:**
  - when the cell across the edge is blocked, it tries edge cells 1, 2, 4 and 8 away;
  - when the game's run stops early with nothing hostile in view, it runs again (up to 3 times);
  - when the only hostiles are more than 6 tiles away, it walks to the edge instead of refusing;
  - when it stops, it gives the reason, e.g. "stopped at (55,3) before the edge: hostiles in view".

  The retry at a blocked crossing hasn't been tested live yet.

**Tokens:** runs 7–9 still kept 30 steps before summarizing, because the `--keep-steps` command-line
default (30) overrode the new `Config` default of 24; the command-line default is 24 now. The
trimming didn't lower the per-step prompt (13.4k tokens on average in both runs, 12.6k
in run 6); the context still fills to the compaction limit. Mistral's prompt cache covers most of it:
from about step 30 on, 85–95% of each prompt was reported as cached.


## Known limitations and ideas

- **One model call per step.** There's no separate planner or critic; the model plans through its
  goal and notes. A slower "reflect every N steps" pass would be easy to add next to compaction.
- **Rough size estimate.** The context size is counted in characters, not tokens.
- **No resume.** Runs aren't resumable: a new run starts with empty notes (the journal carries
  over).
- **Game knowledge is static.** The model doesn't search a wiki; everything comes from the guide
  notes and the journal.
- **Screenshots need WSL.** They need `powershell.exe` and a Windows Qud; elsewhere the harness runs
  without them.
- **The old screenshot harness** (`main.py`, `agent/`, `bridge/` …) is still in the repo. It is
  superseded, and its own recorder and viewer under `recording/` aren't used by this harness.
