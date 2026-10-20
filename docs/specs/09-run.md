# Spec: Run (Episode Manager + Character Creation)

## Purpose

Two modules that manage the episode lifecycle and the character creation phase:

- `run/manager.py`: episode start/end, pause between episodes
- `run/creation.py`: model-led chargen with budget and retries

## Episode Manager (`run/manager.py`)

### Lifecycle

```
Episode start:
  1. Reset state (turn_count=0, phase=chargen)
  2. Clear transcript
  3. Load journal from disk
  4. Start recorder (new recording file)
  5. Wait for Qud window to be available (user launches Qud manually)
  6. Enter chargen phase (run/creation.py)

Play phase:
  - Turn loop runs (loop/turn.py)
  - Model plays until death

Episode end (death):
  1. Model writes final journal notes (via Decision.journal_note)
  2. Stop recorder, save recording
  3. Archive run data (screenshots, decisions, transcript)
  4. Save journal to disk
  5. PAUSE — print summary, wait for user to start next episode
```

### Pause Between Episodes

After death, the harness **pauses**. No auto-restart. The user reviews the
replay, then manually starts the next episode (e.g., by pressing Enter or
running a command).

```
--- Episode 3 ended: died on turn 847 (Red Rock cave level 3) ---
Recording saved to: runs/2026-10-20_episode-3/
Press Enter to start a new episode, or Ctrl+C to quit.
```

### Qud Launch

The harness does **not** launch Qud. The user starts Qud manually (via Steam or
executable). The harness waits for the Qud window to appear (polls the bridge's
`ping` + `grab` until a valid frame is returned).

```python
def wait_for_game(timeout: float = 60.0) -> None:
    """Poll bridge until Qud window is available. Raises on timeout."""
    ...

def run_episode() -> None:
    """Run one full episode: chargen → play → death → pause."""
    ...

def main() -> None:
    """Entry point. Loops: run episode → pause → wait for user → next episode."""
    while True:
        run_episode()
        input("Press Enter to start a new episode...")
```

## Character Creation (`run/creation.py`)

Model-led chargen. The model navigates Qud's character creation screens and
makes all choices (archetype, stats, mutations, cybernetics, faction, etc.).

### Chargen Tools

A small set of tools for navigating creation menus:

| Tool | Params | Description |
|------|--------|-------------|
| `select` | `direction`: "up" \| "down" \| "left" \| "right" | Navigate menu options |
| `confirm` | — | Confirm selection (Enter) |
| `back` | — | Go back (Escape) |
| `name_random` | — | Accept randomly generated name (no typing needed) |

These tools use `controller.press()` under the hood. No `advances_turn` — chargen
doesn't use the turn clock.

### Chargen Flow

```
1. Wait for Qud main menu
2. Model navigates to "New Game" → character creation
3. Model makes choices turn by turn:
   - Pick archetype (or random)
   - Allocate stat points
   - Choose mutations (if mutant)
   - Choose cybernetics (if true kin)
   - Pick faction/caste
   - Name: call name_random
4. Confirm character → game starts
5. Model writes chargen notes to journal
6. Transition to play phase
```

### Chargen Notes

After chargen completes, the model writes a note to the journal describing the
build. This note is available in future runs (the journal persists across episodes).

Example journal note:

```
[chargen] Created a Level 1 True Kin Praetorian with a steel long sword and
carbine. High AV build. Died on turn 847 in Red Rock cave level 3 — should
avoid caves at low level, stick to Joppa quests first.
```

The model writes this via `Decision.journal_note` on the turn it transitions
from chargen to play.

### Budget and Retries

| Limit | Value | Action on exceed |
|-------|-------|------------------|
| Max chargen steps | 100 | Restart chargen |
| Max chargen time | 10 minutes | Restart chargen |
| Max retries | 3 | End episode, pause for user |

If chargen exceeds the step or time budget, it's a failure:

1. Log the failure (with recording)
2. Quit to main menu (Esc → Quit → New Game)
3. Retry chargen (up to 3 times)
4. After 3 failures: end episode, pause for user intervention

### Chargen Watchdog

Same-screen detection: if the screen doesn't change for 30 consecutive steps
during chargen, the model is stuck. Trigger a retry.

## File Layout

```
run/
  __init__.py
  manager.py     # run_episode(), main(), wait_for_game()
  creation.py    # chargen loop, chargen tools, budget/retry logic
```

## Dependencies

- `loop/` (turn loop, phases, watchdog)
- `agent/` (decide, prompts)
- `tools/` (chargen tools: select, confirm, back, name_random)
- `memory/` (state, transcript, journal)
- `logging/recorder.py`
- `client/bridge_client.py` (wait_for_game)

## Open Items

- Chargen tools are separate from game tools. They need their own registry or
  a way to swap tool sets between chargen and play phases.
- The chargen prompt (`system_creation.md`) needs to explain the creation flow
  and what choices matter. This is prompt-engineering territory.
- After 3 chargen retries, the harness pauses. The user can inspect and manually
  restart.
- Does Qud need to be at the main menu when the harness starts? Or can it be
  mid-game? For the demo: assume main menu.
