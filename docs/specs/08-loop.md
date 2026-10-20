# Spec: Loop

## Purpose

The turn loop ties everything together: capture → decide → execute → wait → repeat.
Plus phase management (chargen → play → death) and a watchdog for stuck detection.

## Turn Loop (`loop/turn.py`)

One iteration of the loop:

```
1. Capture perception
   - viewport + log (every turn)
   - + stats + abilities (turn 0, or every 10 turns)

2. Model transcribes log → append to transcript

3. Call decide() → Decision
   - reasoning, tool, args, screen, goal, hp, hunger, location, journal_note

4. Update harness state (memory/state.py)
   - turn_count += 1
   - phase = Decision.screen
   - goal, hp, max_hp, hunger, location from Decision

5. If Decision.journal_note: write to journal

6. Execute tool (tools/)
   - Look up tool by name
   - Validate args against schema
   - tool.execute(**args) → ToolResult

7. If tool.advances_turn:
   - bridge.wait_for_change(timeout=3.0)

8. Capture fresh frame (full screenshot for replay recording)

9. Recorder logs everything
   - Frame (full screenshot)
   - Decision (reasoning, tool, args, state report)
   - ToolResult (text, image)
   - Timing (decision latency, turn duration)

10. Append to conversation context
    - User message: images + transcript update + ToolResult
    - Assistant message: Decision JSON

11. Watchdog check (see below)

12. Go to 1
```

```python
def run_turn() -> None:
    """Execute one full turn. Called in a loop by the phase manager."""
    ...
```

## Phases (`loop/phases.py`)

The model reports `screen` in its Decision each turn. The loop uses it to manage
the game phase:

| Screen | Phase | Prompt | Turn clock |
|--------|-------|--------|------------|
| `chargen` | Character creation | `system_base` + `system_creation` | No — chargen has its own flow |
| `play` | Main game | `system_base` + `system_play` | Yes — wait_for_change after actions |
| `menu` | Menu open | `system_base` + `system_play` | No — model navigates menus by keys |
| `death` | Death screen | — | Episode ends |
| `unknown` | Can't tell | Current prompt | Current behavior — log warning |

```python
class Phase(Enum):
    CHARGEN = "chargen"
    PLAY = "play"
    DEATH = "death"

def current_phase() -> Phase: ...
def transition_to(new_phase: Phase) -> None: ...
```

### Phase Transitions

- **chargen → play**: model reports `screen: "play"`. Switch prompt to play mode.
  Reset turn-specific state if needed.
- **play → death**: model reports `screen: "death"`. End episode:
  1. Write final journal notes
  2. Save recording
  3. Signal run manager to start a new episode
- **any → chargen**: shouldn't happen mid-episode, but if model reports chargen
  during play, log warning and continue.

### Chargen Flow

Chargen is model-led (see `run/creation.py`). The turn loop runs but with
chargen-specific handling:

- No `wait_for_change` — chargen screens don't use the turn clock
- The model navigates creation menus by calling tools (or raw key tools if needed)
- A separate chargen watchdog applies (see below)

## Watchdog (`loop/watchdog.py`)

Detects when the agent is stuck or exceeding budgets. For a demo, the watchdog
is simple: **log loudly and end the episode**. No auto-recovery.

### Triggers

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Same screen for N turns | 20 consecutive turns | End episode, log "stuck" |
| `wait_for_change` timeout streak | 5 consecutive timeouts | End episode, log "game not responding" |
| Episode turn budget | 5000 turns | End episode, log "turn budget exceeded" |
| Episode time budget | 2 hours wall-clock | End episode, log "time budget exceeded" |
| Chargen time budget | 10 minutes | End chargen, restart |
| Chargen no-progress | 30 steps without screen change | End chargen, restart |

### Implementation

```python
class Watchdog:
    def __init__(self) -> None:
        self.last_screen: str = ""
        self.same_screen_count: int = 0
        self.timeout_streak: int = 0
        self.episode_start_time: float = 0.0
        self.episode_start_turn: int = 0

    def check(self, decision: Decision, turn_changed: bool) -> WatchdogAction | None:
        """
        Called every turn. Returns an action if a threshold is exceeded,
        or None to continue.
        """
        ...

    def reset(self) -> None: ...
```

### Actions

```python
class WatchdogAction(Enum):
    CONTINUE = "continue"
    END_EPISODE = "end_episode"
    RESTART_CHARGEN = "restart_chargen"
```

When the watchdog triggers, the loop logs the reason (with full context from the
recorder) and signals the run manager.

## File Layout

```
loop/
  __init__.py
  turn.py        # run_turn() — the main loop iteration
  phases.py      # Phase enum, phase transitions, prompt switching
  watchdog.py    # Watchdog class, triggers, actions
```

## Dependencies

- `agent/decide.py` (for Decision)
- `tools/` (for tool execution)
- `perception/` (for capture)
- `memory/` (for state, transcript, journal)
- `logging/recorder.py` (for recording)
- `run/manager.py` (for episode lifecycle signals)

## Open Items

- Chargen flow details — see `run/creation.py` spec (09-run.md)
- The watchdog is not expected to be heavily used in the demo. It's a safety net.
- Phase transitions are model-driven (the model reports the screen). If the model
  misreports, the loop follows the wrong phase. Trust the model for the demo.
