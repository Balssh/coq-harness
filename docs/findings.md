# Findings — 2026-10-23 Harness Session

## What we ran

- **15 episodes** total (episodes 1–15), iteratively debugging the ML4 agent playing Caves of Qud
- Started from main menu (episode 12: full chargen → Marsh Taur "9999" in Joppa), then continued with `--skip-chargen` for episodes 13–15

## Best result: Episode 15 (52 turns)

The model **successfully talked to Elder Irudad (Village Chief)**, navigated a multi-turn dialogue with numbered options, exited cleanly, and continued exploring Joppa. This is the furthest any episode has gotten.

### Episode 15 tool usage

| Tool | Count |
|------|-------|
| move | 24 |
| choose_option | 7 |
| key:space | 6 |
| key:escape | 5 |
| close_menu | 4 |
| send_keys | 2 |
| talk | 2 |
| alt_overlay | 1 |
| look | 1 |

### Episode 15 screen distribution

| Screen | Turns |
|--------|-------|
| play | 29 |
| dialogue | 15 |
| menu | 8 |

## Fixes applied

| # | Fix | Files | Impact |
|---|-----|-------|--------|
| 1 | **`keys_seq` bridge action** — sends sequential key presses within one focus session | `bridge/input.py`, `bridge/server.py`, `client/bridge_client.py`, `game/controller.py`, `tools/interaction.py` | Fixed `talk`/`interact`/`trade` sending Space+direction as two separate calls, losing focus between them |
| 2 | **Dialogue Space fix** — prompts now say Space doesn't work in dialogue, use number keys | `agent/prompts/system_base.md`, `system_play.md`, `system_dialogue.md` | Model stopped looping on `key=space` in dialogue |
| 3 | **Look-mode protocol** — explicit step-by-step (look → move cursor once → read → close_menu → talk) | `agent/prompts/system_play.md`, `tools/movement.py` | Model follows look-before-talk correctly |
| 4 | **Anti-repeat warning** — harness injects a warning after 3+ identical consecutive actions | `loop/turn.py` | Breaks stuck loops (wall-bumping, space-spamming) |
| 5 | **Blocked-movement rule** — "the way is blocked" → pick a different direction immediately | `agent/prompts/system_base.md`, `system_play.md` | Prevents wall-bumping loops |
| 6 | **Escape opens menu bug** — model kept pressing Escape which opened Control Mapping | (prompt awareness) | Model learned to use `close_menu` tool instead |

## Key learnings

1. **Space+direction focus loss was the root cause of `talk` failures** — `press("space")` + `press(direction)` as two bridge calls lost window focus between them. Fixed with `keys_seq` (single focus session). Episode 15's successful `talk(down)` to the Village Chief validates this.

2. **Space does NOT work in Qud dialogue** — only number keys (1-9) select dialogue options. The ">press [Space]" prompt is misleading. Verified manually: Enter didn't work, pressing `1` changed the screen.

3. **The message log is scrolling history, not popups** — the model repeatedly tried to "dismiss" old log messages. Prompts now emphasize this.

4. **Look mode toggles** — calling `look` twice exits it. The model must call `look` once, move cursor with `move`, read the description, then `close_menu`.

5. **Escape opens the Control Mapping menu** in Qud — the model kept pressing Escape to "close" things, which opened a menu instead. The `close_menu` tool and proper prompts help avoid this.

6. **Anti-repeat warnings work** — injecting a harness-side warning after 3 identical actions helps break loops, but the model still sometimes repeats (e.g., 6x `key=space` in dialogue before the warning kicked in).

7. **Watchdog at 20 same-screen turns** catches hard-stuck cases but is too late — the anti-repeat warning at 3 turns is more effective.

## Remaining issues

- **Dialogue `key=space` spam** — the model still presses Space 4-6 times in dialogue before switching to `choose_option`. The prompt fix helps but doesn't fully eliminate it.
- **Menu loops** — the model occasionally gets stuck in the Control Mapping / Options menu (8 menu turns in ep 15).
- **Exploration is aimless** — after the dialogue, the model wanders around buildings without a clear goal (no quest accepted yet).
- **No quest obtained yet** — the Village Chief dialogue didn't result in a quest pickup (model may have missed the quest option or the dialogue didn't offer one).

## Episode history

| Episode | Turns | Outcome |
|---------|-------|---------|
| 1 | 28 | Full run (chargen OK). Watchdog stuck — model looped on failed interactions. |
| 2-3 | — | `--skip-chargen` added. Ep 3 crashed on Mistral 503 (no retry). |
| 4 | — | Model looped on `close_menu` — thought log messages were popups. |
| 5 | — | Model looped on `key=space` — game needed Enter, not Space. |
| 6 | — | Best until ep 15. Entered dialogue with Village Chief, got stuck advancing text. |
| 7 | — | `talk(up)` repeatedly failed despite model claiming adjacency. |
| 8 | — | Model used `choose_option(1)` but still looped talk→fail→space. |
| 9 | — | Model entered look mode, called `look` twice (toggles OFF), moved cursor wrong. |
| 10 | — | Character sat on a floor cushion and got stuck. |
| 11 | 21 | Got trapped in Control Mapping menu loop. |
| 12 | 34 | Full chargen (Marsh Taur "9999", Joppa). Stuck on Space during world creation and Village Chief dialogue. |
| 13 | 22 | Watchdog: stuck in look mode, 10x `move(up)` moving cursor without reading. |
| 14 | 21 | Watchdog: 16x `move(up_right)` into a wall despite "the way is blocked" in log. |
| 15 | 52 | **Best result.** Full dialogue with Elder Irudad, clean exit, continued exploring. |

## Infrastructure notes

- **Window title**: `CavesOfQud` (no space — default `"Caves of Qud"` won't match)
- **Window must not be minimized** — stops rendering
- **Capture size drift**: 1922x1119 vs expected 1920x1080 — fixed with proportional scaling in perception
- **Relay is single-session**: only one harness connection at a time
- **Bridge log is empty**: Python buffers stdout when redirected to file
- **Sitting on cushions**: character can get stuck; `"key": "s"` toggles sit/stand

## Commands

**Start relay** (WSL):
```bash
cd /home/balssh/Projects/coq-harness && PYTHONUNBUFFERED=1 nohup .venv/bin/python -u -m client.relay > /tmp/relay.log 2>&1 &
```

**Start bridge** (Windows, via WSL interop):
```bash
powershell.exe -Command "Start-Process -FilePath 'C:\Users\georg\AppData\Local\Python\pythoncore-3.15-64\python.exe' -ArgumentList '-m bridge.server --connect localhost:9091 --window-title CavesOfQud --log-region 1440 54 480 918' -WorkingDirectory 'C:\Windows\Temp\coq-bridge' -WindowStyle Hidden"
```

**Deploy bridge files to Windows**:
```bash
cp bridge/*.py /mnt/c/Windows/Temp/coq-bridge/bridge/
```

**Start harness** (continue existing game):
```bash
cd /home/balssh/Projects/coq-harness && PYTHONUNBUFFERED=1 nohup .venv/bin/python -u main.py --episode N --skip-chargen > /tmp/harnessN.log 2>&1 &
```

**Start harness** (from main menu, full chargen):
```bash
cd /home/balssh/Projects/coq-harness && PYTHONUNBUFFERED=1 nohup .venv/bin/python -u main.py --episode N > /tmp/harnessN.log 2>&1 &
```

**Restore minimized Qud window**:
```bash
powershell.exe -Command "\$w = Get-Process -Name 'CoQ'; \$h = \$w.MainWindowHandle; Add-Type -MemberDefinition '[System.Runtime.InteropServices.DllImport(\"user32.dll\")] public static extern bool ShowWindow(System.IntPtr h, int nCmdShow);' -Name W -Namespace W; [W.W]::ShowWindow(\$h, 9) | Out-Null"
```

**Monitor decisions**:
```bash
cd /home/balssh/Projects/coq-harness && .venv/bin/python -c "
import json
decisions = []
with open('runs/2026-10-23_episode-N/log.jsonl') as f:
    for line in f:
        e = json.loads(line)
        if e.get('type') == 'decision': decisions.append(e)
for e in decisions[-15:]:
    key = e.get('key'); tool = e.get('tool',''); args = e.get('args',{})
    action = f'key={key}' if key else f'[{tool} {args}]' if args else f'[{tool}]'
    print(f\"T{e['turn']:3d} {action:32s} {e.get('screen',''):10s} | {e.get('reasoning','')[:150]}\")
"
```
