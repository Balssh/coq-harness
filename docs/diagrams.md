# Harness Flow Diagrams

## 1. Startup — Terminal to Running Harness

```
Terminal: python main.py --episode 16 --skip-chargen
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  main.py                                                          │
│  ├── Parse --force-bridge flag                                    │
│  └── ensure_all()  ←── auto-deploy infrastructure                 │
│        │                                                          │
│        ├──► 1. ensure_relay()                                     │
│        │       └── Start WSL relay if not running                 │
│        │           └── client.relay listens on:                   │
│        │               ├── 0.0.0.0:9091  (bridge connects here)    │
│        │               └── 127.0.0.1:9090 (harness connects here)  │
│        │                                                          │
│        ├──► 2. ensure_qud_running()                               │
│        │       └── Check CoQ process exists                       │
│        │           └── If minimized → ShowWindow(SW_RESTORE)       │
│        │               (WGC can't capture minimized windows!)      │
│        │                                                          │
│        ├──► 3. deploy_bridge()                                    │
│        │       ├── Copy bridge/*.py → C:\Windows\Temp\coq-bridge\│
│        │       ├── Kill old bridge processes (powershell)         │
│        │       ├── Start bridge (powershell, hidden window)       │
│        │       │   └── python -m bridge.server --connect ...      │
│        │       │       └── Connects to relay at localhost:9091    │
│        │       │       └── WGC capture starts (background thread)  │
│        │       │       └── InputInjector ready                    │
        │       │       └── FrameDiffer ready                          │
│        │       └── Wait for bridge ping (retry x2)                │
│        │                                                          │
│        └──► 4. wait_qud_capture()                                 │
│                └── Verify bridge.grab() returns frame data         │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  run.manager.main() — Episode loop                                │
│  └── run_episode(16, skip_chargen=True)                           │
└──────────────────────────────────────────────────────────────────┘
```

## 2. Episode Lifecycle

```
run_episode(N)
    │
    ├──► init_client() → connect to relay at 127.0.0.1:9090
    │       └── Relay pipes bytes between harness ↔ bridge
    │
    ├──► wait_for_game() — poll ping + grab until Qud window ready
    │
    ├──► reset_state() / clear transcript / clear conversation / reset watchdog
    │
    ├──► Load journal from runs/journal.json
    │
    ├──► start_recorder() → create runs/2026-10-23_episode-N/
    │       └── frames/  log.jsonl  meta.json
    │
    ├──► IF --skip-chargen:
    │       └── Press Escape ×2 (clear menus) → Phase.PLAY
    │   ELSE:
    │       └── Phase.CHARGEN → run_chargen() → Phase.PLAY
    │
    └──► _play_loop()
            │
            │   ┌─────────────────────────────────────────────┐
            └──►│  LOOP:                                       │
                │  1. run_turn(phase="play")                   │
                │  2. Check: death screen? → end episode       │
                │  3. Check: watchdog (20 same-screen turns)?  │
                │     → end episode                            │
                │  4. Check: restart requested by model?       │
                │     → end episode                            │
                │  5. Go to step 1                             │
                └─────────────────────────────────────────────┘
                    │
                    ▼ (episode ends)
            Save journal → save meta → stop recorder
                    │
                    ▼
            "Press Enter to start episode N+1..."
                    │
                    └──► run_episode(N+1)  (or Ctrl+C to quit)
```

## 3. Turn Loop — The Core (run_turn)

```
run_turn(phase="play")
    │
    ├──► 1. CAPTURE
    │       └── perception.capture()
    │           ├── BridgeClient.grab() → relay → bridge → WGC cached frame → PNG
    │           ├── Crop viewport (main game area)
    │           ├── Crop message log (right panel, full-res)
    │           └── Crop stats bar (bottom strip)
    │           └── Downscale viewport for LLM
    │
    ├──► 2. recorder.start_turn(turn_count)
    │
    ├──► 3. DECIDE — call ML4 (Mistral Large 4)
    │       │
    │       ├──► Build prompt:
    │       │   ├── system_base.md (manual, tools, output format)
    │       │   ├── system_play.md / system_dialogue.md / system_menu.md (phase-specific)
    │       │   ├── Tool descriptions (39 tools, JSON schema)
    │       │   ├── Transcript (last 30 turns)
    │       │   ├── Conversation history (last 20 turn-pairs)
    │       │   ├── Journal notes (cross-episode)
    │       │   └── Current state (HP, hunger, location, goal)
    │       │
    │       ├──► Attach images:
    │       │   ├── Viewport (downscaled)
    │       │   ├── Message log (full-res)
    │       │   └── Stats bar
    │       │
    │       ├──► ML4 returns JSON:
    │       │   {
    │       │     "reasoning": "...",
    │       │     "tool": "move",          // or ""
    │       │     "key": null,              // or "space", "escape", "1", etc.
    │       │     "args": {"direction": "up"},
    │       │     "screen": "play",
    │       │     "goal": "...",
    │       │     "hp": 18, "max_hp": 18,
    │       │     "hunger": "Satiated",
    │       │     "location": "Joppa",
    │       │     "journal_note": null
    │       │   }
    │       │
    │       └──► Retry: 5 attempts, exponential backoff on 429/5xx/timeout
    │           └── Fallback: {"tool": "wait"} on total failure
    │
    ├──► 4. recorder.record_decision(decision)
    │
    ├──► 5. update() — harness state (turn_count++, screen, hp, goal, etc.)
    │
    ├──► 6. journal.add(journal_note) if present
    │
    ├──► 7. EXECUTE ACTION
    │       │
    │       ├──► IF decision.key (direct key press):
    │       │   └── press(key) → BridgeClient.keys([key])
    │       │       └── No turn advance
    │       │
    │       └──► ELSE execute_tool(tool, args):
    │           │
    │           ├──► Movement tools (advance turn):
    │           │   ├── move(dir)         → press(dir)
    │           │   ├── rest(turns)       → press(".")
    │           │   ├── auto_explore      → loop move until stuck/hostile
    │           │   └── go_stairs         → press direction + interact
    │           │
    │           ├──► Interaction tools (advance turn):
    │           │   ├── talk(dir)         → press_seq(["space", dir])  ← keys_seq!
    │           │   ├── interact(dir)     → press_seq(["space", dir])
    │           │   ├── trade(dir)        → press_seq(["space", dir])
    │           │   ├── get / drop / equip / quaff / eat
    │           │
    │           ├──► Info tools (no turn advance):
    │           │   ├── look              → chord(["shift", "l"])
    │           │   ├── alt_overlay       → hold("alt") + capture + release
    │           │   ├── character_sheet   → open screen + capture + close
    │           │   ├── inventory / skills / quests / read_log / read_stats
    │           │
    │           ├──► Dialogue tools (no turn advance):
    │           │   ├── choose_option(n)  → press(str(n))
    │           │   └── close_menu        → press("escape")
    │           │
    │           └──► Meta tools:
    │               ├── save / quit / restart_run / abandon
    │
    ├──► 8. recorder.capture("after-action") — save frame to disk
    │
    ├──► 9. TURN CLOCK — IF tool.advances_turn:
    │       └── client.wait_for_change(timeout=3.0)
    │           └── Bridge FrameDiffer.wait_for_change()
    │               ├── Poll log region every 50ms
    │               ├── Diff against baseline (>50 pixels = change)
    │               └── Return True on change, False on timeout
    │
    ├──► 10. recorder.end_turn(turn_changed, wait_time)
    │
    ├──► 11. CONVERSATION CONTEXT
    │       ├── Append assistant (decision JSON) + user (result + state)
    │       ├── Trim to last 20 turn-pairs (40 messages)
    │       └── ANTI-REPEAT: if same action 3+ times consecutively,
    │           inject warning: "STOP repeating this action"
    │
    └──► Return decision → back to _play_loop()
```

## 4. Bridge Internals (Windows Side)

```
BridgeServer (long-lived Windows process)
    │
    ├──► WindowCapture (WGC — continuous background thread)
    │   │
    │   │   start_free_threaded()
    │   │       └── WGC captures window content on every change (event-driven)
    │   │       └── _on_frame(frame) → cache latest frame (HxWx4 BGRA numpy)
    │   │       └── _on_closed() → mark session dead
    │   │
    │   │   grab_png()          → return cached frame as PNG bytes
    │   │   grab_region_png()   → return cropped region as PNG
    │   │   grab_region_array() → return cropped region as numpy (for diffing)
    │   │   get_frame()         → auto-restart WGC if session died
    │   │
    │   └── Note: captures EVEN WHEN window is occluded/off-screen
    │       But NOT when minimized (Windows stops rendering)
    │
    ├──► InputInjector (SendInput + focus management)
    │   │
    │   │   send_chord(keys)     → force-fg → press all → release → restore-fg
    │   │                           (e.g., ["shift", "l"] for look)
    │   │
    │   │   send_sequence(keys)  → force-fg → press each sequentially → restore-fg
    │   │                           (e.g., ["space", "up"] for talk — ONE focus session)
    │   │
    │   │   key_down(key) / key_up(key)
    │   │
    │   └── PostMessage tried first → Unity ignores it (Raw Input)
    │       → Fallback: AttachThreadInput + AllowSetForegroundWindow + SendInput
    │
    ├──► FrameDiffer (log region turn detection)
    │   │
    │   │   reset_baseline()       → sample current log region
    │   │   wait_for_change(t)     → poll every 50ms, diff, return on >50px change
    │   │
    │   └── Region: 1440, 54, 480, 918 (right-side message log)
    │
    └──► Socket client → connects to WSL relay at localhost:9091
        │
        └── Actions (lock-serialized):
            ├── ping              → {status, uptime, capture_alive, frame_age}
            ├── grab              → PNG bytes (full frame)
            ├── grab_region       → PNG bytes (cropped)
            ├── keys              → send_chord
            ├── keys_seq          → send_sequence (Space+dir in one focus session)
            ├── key_down / key_up → hold/release
            └── wait_for_change   → FrameDiffer result
```

## 5. Data Flow — One `grab` Request

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────────────────┐
│  Harness     │     │  Relay       │     │  Bridge (Windows)            │
│  (WSL)       │     │  (WSL)       │     │                              │
│              │     │              │     │  WGC thread:                 │
│  client.grab()    │              │     │    └── continuously caches   │
│      │       │     │              │     │        latest frame          │
│      │       │     │              │     │                              │
│      ├──TCP──┼────►│──TCP───────┼────►│  capture.grab_png()          │
│      │  {   │     │  forward    │     │    └── return cached frame   │
│      │  "action":"grab"       │     │                              │
│      │  }   │     │              │     │  ←─TCP──┐                    │
│      │      │     │              │     │  PNG bytes                  │
│      │◄─────┼─────┼──────────────┼─────┤         │                    │
│      │      │     │              │     │         └────────────────────┘
│  return PNG│     │              │     │
│  bytes     │     │              │     │
└──────────────┘     └──────────────┘     └──────────────────────────────┘
     127.0.0.1:9090      pipes both ways       connects to 0.0.0.0:9091
```

## 6. Data Flow — One `talk("up")` Action

```
Harness                          Bridge (Windows)
────────                        ─────────────────
  talk("up")
    │
    ├── execute_tool("talk", {"direction": "up"})
    │
    ├── TalkTool.execute("up")
    │   └── press_seq(["space", "up"])
    │       └── BridgeClient.keys_seq(["space", "up"])
    │           │
    │           ├── TCP: {"action": "keys_seq", "keys": ["space", "up"]}
    │           │                                           │
    │           │                    ┌──────────────────────┘
    │           │                    ▼
    │           │         InputInjector.send_sequence(["space", "up"])
    │           │           │
    │           │           ├── _force_foreground(hwnd)     ← ONE focus session
    │           │           │   └── AttachThreadInput + SetForegroundWindow
    │           │           │
    │           │           ├── SendInput(SPACE down) ──┐
    │           │           ├── SendInput(SPACE up)    │ sequential
    │           │           ├── sleep(80ms)             │ within same
    │           │           ├── SendInput(UP down)     │ focus
    │           │           └── SendInput(UP up) ──────┘
    │           │           │
    │           │           └── _restore_foreground(prev)
    │           │
    │           ◄── TCP: {"status": "ok"}
    │
    ├── _wait_for_render(0.3s)
    │
    └── Return ToolResult("Opened interaction menu toward up.")
            │
            └── Turn clock: wait_for_change(3.0s)
                    └── FrameDiffer polls log region for changes
```

## 7. Turn Clock — wait_for_change

```
Harness                          Bridge FrameDiffer
────────                        ──────────────────
  move("up") executed
    │
    ├── tool.advances_turn = True
    │
    └── client.wait_for_change(timeout=3.0)
            │
            ├── TCP: {"action": "wait_for_change", "timeout": 3.0}
            │                                    │
            │                    ┌───────────────┘
            │                    ▼
            │         differ.reset_baseline()  ← sample log region now
            │         loop (every 50ms):
            │           ├── sample = capture.grab_region_array(log_region)
            │           ├── diff = count_pixels_changed(baseline, sample)
            │           ├── if diff >= 50: return (True, elapsed)
            │           └── if elapsed >= 3.0s: return (False, elapsed)
            │
            ◄── TCP: {"changed": true/false, "elapsed": 0.XXX}
            │
            └── turn_changed = result["changed"]
```

## 8. Anti-Repeat & Watchdog

```
Per-turn (in run_turn, step 11):
    │
    ├── Track action string: "tool:args" or "key:X"
    ├── Count consecutive repeats of same action
    └── IF repeat_count >= 3:
            └── Inject into conversation:
                "*** WARNING: You have called 'X' 3 times in a row
                    with no progress. STOP repeating this action. ***"

Per-episode (in _play_loop, after each turn):
    │
    └── Watchdog.check_play(screen, turn_count):
            ├── Track turns on same screen type
            ├── IF same_screen_turns >= 20:
            │   └── WatchdogAction.END_EPISODE
            │       └── Episode ends, recording saved
            └── ELSE: continue
```

## 9. Tool Categories (39 tools)

```
┌─────────────────────────────────────────────────────────────┐
│  MOVEMENT (advance turn)                                     │
│  ├── move(direction)         — walk one tile                 │
│  ├── rest(turns?)            — wait/heal                     │
│  ├── go_stairs               — use < or >                    │
│  ├── auto_explore            — systematic wandering          │
│  ├── wait_until_healed       — rest until HP full            │
│  └── move_to_zone_edge(dir)  — travel to adjacent zone       │
├─────────────────────────────────────────────────────────────┤
│  INTERACTION (advance turn)                                  │
│  ├── get / drop / equip / unequip / quaff / eat             │
│  ├── talk(direction)         — Space+dir (keys_seq!)        │
│  ├── interact(direction)     — Space+dir (keys_seq!)        │
│  └── trade(direction)         — Space+dir (keys_seq!)        │
├─────────────────────────────────────────────────────────────┤
│  INFO (no turn advance)                                      │
│  ├── look                    — Shift+L, inspect tiles        │
│  ├── alt_overlay             — hold Alt, show labels         │
│  ├── character_sheet         — X key                         │
│  ├── inventory               — I key                         │
│  ├── skills                  — P key                         │
│  ├── quests                  — Q key                         │
│  ├── read_log                — full-res log screenshot       │
│  └── read_stats              — HP/hunger/level               │
├─────────────────────────────────────────────────────────────┤
│  DIALOGUE / MENU (no turn advance)                           │
│  ├── choose_option(n)        — press number 1-9             │
│  ├── close_menu              — Escape                        │
│  └── send_keys(keys)         — raw key list                  │
├─────────────────────────────────────────────────────────────┤
│  META                                                         │
│  ├── save / quit / restart_run / abandon                    │
│  └── confirm / next (chargen navigation)                    │
└─────────────────────────────────────────────────────────────┘
```
