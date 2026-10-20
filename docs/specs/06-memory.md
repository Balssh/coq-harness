# Spec: Memory

## Purpose

Four modules that give the model persistent memory across turns and episodes:

- `state.py`: harness-tracked state (turn count, phase, goal)
- `transcript.py`: running text transcript of the message log, transcribed by the model
- `journal.py`: cross-episode free-text notes (also serves as map memory)
- `map_memory.py`: the model's structured notes about locations, folded into the journal

## State (`memory/state.py`)

Harness-tracked state. The harness owns this — the model doesn't set it directly,
but may report observations that update it.

```python
@dataclass
class GameState:
    turn_count: int = 0          # increments every turn (after wait_for_change)
    phase: str = "chargen"       # chargen / play / death — mirrors model's report
    goal: str = ""               # model's current high-level goal (from model output)
    screen: str = "unknown"      # model's last reported screen (Screen enum value)
    hp: int | None = None        # model-reported HP (cached, not parsed by harness)
    max_hp: int | None = None
    hunger: str = ""             # model-reported hunger level
    location: str = ""           # model-reported location name

def get_state() -> GameState: ...
def update(**kwargs) -> None: ...
def reset() -> None: ...         # reset for new episode
```

The harness tracks `turn_count` and `phase` independently. HP/hunger/location are
**model-reported** (the model reads them from the stats bar screenshot and includes
them in its decision output). The harness caches them for logging and journal context.

## Transcript (`memory/transcript.py`)

A running text transcript of the message log. The model transcribes the log region
from the screenshot each step and appends it to the transcript.

```python
class Transcript:
    def append(self, text: str) -> None: ...
    """Append model-transcribed log text for this turn."""

    def get(self, max_turns: int | None = None) -> str: ...
    """Return the full transcript, or the last N turns."""

    def clear(self) -> None: ...
```

For the demo: **keep it raw**. No summarization, no truncation. The transcript
grows unbounded within an episode. If context limits become a problem later,
summarization can be added.

The transcript is included in the model's context each turn (or a recent window
of it). It serves as the model's short-term memory of what happened.

## Journal (`memory/journal.py`)

Cross-episode free-text notes. Persisted to disk between episodes. Prepended to
the system prompt at the start of each new episode.

```python
class Journal:
    def add(self, note: str) -> None: ...
    """Add a free-text note. Called by the model during or after an episode."""

    def get(self) -> str: ...
    """Return all notes as a single string for the system prompt."""

    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...
```

Journal is **free text**. The model writes whatever it thinks is important:

```
Joppa: friendly town, has a quest from the mayor.
The Rusted Archer quest: kill 3 snapjaws, reward is a carbine.
Level 1 characters should avoid the desert at night — dawngliders.
Found a legendary sword in the mayor's house (locked door, need lockpick).
```

## Map Memory (`memory/map_memory.py`)

Map memory is **folded into the journal**. The model writes location notes to the
journal, which serves as both cross-episode memory and map memory.

There is no separate tile-grid map. The model's spatial memory comes from:

1. **The journal** — location descriptions, exits, landmarks, dangers
2. **The transcript** — what the model saw and did recently
3. **The current screenshot** — the viewport shows the immediate surroundings

`map_memory.py` provides helper functions for the model to write structured-by-
location notes:

```python
def add_location_note(location: str, note: str) -> None:
    """Add a note about a specific location. Stored in the journal with a
    location prefix for easy retrieval."""
    journal.add(f"[{location}] {note}")

def get_location_notes(location: str) -> str:
    """Return all journal notes for a specific location."""
    ...
```

The model calls these via a `journal_note` tool (see `tools/meta.py`) or includes
notes in its regular output.

## File Layout

```
memory/
  __init__.py
  state.py         # GameState dataclass, get_state(), update(), reset()
  transcript.py    # Transcript class (append, get, clear)
  journal.py       # Journal class (add, get, save, load) — persisted to disk
  map_memory.py    # add_location_note(), get_location_notes() — helpers over journal
```

## Dependencies

- Stdlib only (dataclasses, json for journal persistence)
- Journal persisted as JSON: `{"notes": ["note1", "note2", ...]}`

## Open Items

- Journal persistence format: JSON file per session, or a single append-only file?
  For the demo: one JSON file per session, path configurable.
- Should the journal be editable by the user between runs? (Nice for debugging.)
- `add_location_note` / `get_location_notes` filtering: simple string prefix
  matching (`[location]` prefix), or more structured?
