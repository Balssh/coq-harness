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
   - **Already playing:** keep that game, unless `--new-game` is set. Then it calls `quit_to_menu`,
     which saves and leaves through the system menu's "Save and Quit", followed by `start_new_game`
     and `chargen_auto` (a random Classic character).
   - **At the main menu:** `continue_game`, or the new-game pair with `--new-game`. If continuing
     fails, it falls back to a new game. Right after Qud launches the menu can ignore
     `start_new_game`, so the pair is retried up to three times.
   - **In character creation:** `chargen_auto`.
3. **Opening:** the first user message is the full `get_state` text.
4. **Steps** until a stop condition (below).
5. **Teardown:**
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
  - exploration habits: `auto_explore` until done, then NPCs, containers and stairs, then leave the
    zone; prefer `go_to` to many single moves;
  - the whole of `docs/qud_novice_notes.md`, so game knowledge lives in one file shared with other
    clients;
  - the last ~4000 characters of `runs/journal.md`.
- **Memory block:** appended to the system prompt every step, so it is never lost.
  - **Goal:** set by `set_goal`.
  - **Notes:** numbered, written by `note` and removed by `forget_note`. At most 40 notes of 300
    characters each; the oldest is dropped first.
  - **The story so far:** written during compaction.

  It sits at the end of the system message rather than in a separate message because Mistral is
  strict about message order (no user message straight after a tool message). The fixed part of the
  prompt stays first so providers can cache it.
- **Recent steps:** kept verbatim. Tool results older than 6 steps are cut to 1200 characters, since
  old `get_state` dumps are the biggest cost.
- **Compaction:**
  - Triggers when there are more than `--keep-steps` steps (default 30) or the context passes about
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
    is plain markdown, so you can edit or prune it.
  - Every later run reads it.

## Guards

| Guard | Trigger | Effect |
|---|---|---|
| No tool call | response without tool calls | user message: "You must call at least one tool every turn…" |
| Stuck | same zone, position, HP, turn counter, screen and popup for 8 steps | `WATCHDOG:` hint appended to the last result |
| Repeat | the same call with the same arguments and the same outcome 5 times in a row | `WATCHDOG:` hint |
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
- **`nudge`:** `kind` is one of `no_tool`, `stuck`, `repeat` or `zone`.
- **`autosave`, `lessons`, `error`, `run_end`.**

**Screenshots** come from a single `powershell.exe` started from WSL. It loops on stdin, finds the
`CoQ` window and renders it with `PrintWindow(PW_RENDERFULLCONTENT)`. That works while the window is
behind other windows and never takes focus. The process is DPI-aware so the window isn't cropped.

- **Cost:** about 0.1 s per frame after a one-second start-up.
- **Limitation:** a minimized window can't be captured. The run continues, and an `error` event notes
  it once.

## Replay viewer

`uv run python -m harness replay` serves `runs/harness/` on `http://localhost:8765/` and opens the
browser.

- **Run list:** start time, model, label, outcome, steps, final level and duration.
- **Run view:**
  - the screenshot;
  - a map drawn from the recorded state:
    - creatures by their first letter, coloured hostile, friendly or neutral;
    - walls, items, containers, doors and stairs;
    - unexplored cells in black;
    - hover shows names;
  - an HP bar and stats;
  - messages, with new ones highlighted;
  - the step panel: hidden reasoning (collapsible), the model's text, and each tool call with its
    result. The call that produced the current frame is outlined.
  - the memory as it was at that moment;
  - nudges, summaries and errors for the step.
- **HP timeline:** dashed lines mark level-ups, ticks mark nudges, summaries, errors and death.
  Click it to seek.
- **Controls:** play/pause with Space, step with ←/→, Home/End, speed from 0.5× to 10×.
- **Links:** `?run=<id>&frame=N` opens a specific moment.
- **Live runs:** a run that's still in progress is polled every 3 s, and "follow live" keeps the
  view on the newest frame.

## MP4 export

`uv run python -m harness export <run> [--seconds-per-frame 1.0] [--out file.mp4]`, or the
**Export MP4** button in the viewer. The button renders on the server, shows progress, and then
offers `replay.mp4` for download.

- **Frames:** one 1920×1080 frame per snapshot, drawn with Pillow:
  - the header (run, model, step, time);
  - the game screenshot;
  - an HP bar and stats;
  - the map drawn from the recorded state;
  - the step panel: thinking, the model's text, the tool calls with the current call's result, and
    harness nudges;
  - memory (goal and notes);
  - the latest messages, with new ones highlighted;
  - the HP timeline with a cursor.
- **Encoding:** frames are piped to `ffmpeg` (libx264, CRF 23, 30 fps), which must be on PATH. The
  first live run (228 frames at 1 s each) took 36 s to render and came out at 3:48 and 14 MB.

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
