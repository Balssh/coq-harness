# Spec: Logging (Recorder + Replay Viewer)

## Purpose

Record everything that happens during an episode, and provide a way to replay it.
The replay viewer is **non-negotiable for debugging** — without it, you're blind
to what the model actually did and why.

## Recorder (`recording/recorder.py`)

### What Gets Recorded

Every turn, plus intermediate frames within a turn:

| Event | Data |
|-------|------|
| Turn start | Full screenshot (PNG), turn number |
| Decision | Reasoning, tool, args, screen, goal, hp, hunger, location, journal_note |
| After action | Full screenshot (PNG) — state after keys sent, before turn resolves |
| Turn end | Full screenshot (PNG) — state after wait_for_change |
| Tool result | Text, any images returned by the tool |
| Intermediate frames | Screenshots at key points within a tool (e.g., menu opened, item selected) |
| Transcript update | What the model transcribed from the log this turn |
| Timing | Decision latency (LLM call), turn duration, wait_for_change result |

### Storage Format

```
runs/2026-10-20_episode-3/
  frames/
    turn-0000-00-start.png       # turn 0, frame 0, "start" label
    turn-0000-01-after-action.png
    turn-0000-02-end.png
    turn-0001-00-start.png
    ...
  log.jsonl                     # one JSON object per event
  meta.json                     # episode metadata
```

### JSONL Event Format

Each line in `log.jsonl` is a JSON object:

```json
{"type": "turn_start", "turn": 0, "frame": "turn-0000-00-start.png", "timestamp": 1729440000.0}
{"type": "decision", "turn": 0, "reasoning": "I see a snapjaw...", "tool": "move", "args": {"direction": "west"}, "screen": "play", "goal": "explore Joppa", "hp": 25, "max_hp": 25, "hunger": "Satiated", "location": "Joppa"}
{"type": "tool_result", "turn": 0, "text": "", "error": false}
{"type": "frame", "turn": 0, "label": "after-action", "frame": "turn-0000-01-after-action.png"}
{"type": "frame", "turn": 0, "label": "end", "frame": "turn-0000-02-end.png", "turn_changed": true, "wait_time": 0.3}
{"type": "transcript", "turn": 0, "text": "You hit the snapjaw. The snapjaw dies!"}
{"type": "timing", "turn": 0, "decision_ms": 2340, "turn_total_ms": 2890}
{"type": "turn_end", "turn": 0}
```

### Recorder API

```python
class Recorder:
    def __init__(self, run_dir: str) -> None: ...

    def start_turn(self, turn: int) -> None: ...

    def record_decision(self, decision: Decision) -> None: ...

    def capture(self, label: str) -> str: ...
    """Capture an intermediate frame. Returns the frame filename."""

    def record_tool_result(self, result: ToolResult) -> None: ...

    def end_turn(self, turn_changed: bool, wait_time: float) -> None: ...

    def record_transcript(self, text: str) -> None: ...

    def save_meta(self, **kwargs) -> None: ...

    def close(self) -> None: ...
```

### Integration

The recorder is a singleton, started at episode begin and stopped at episode end.
The turn loop calls recorder methods at each step. Tools can call
`recorder.capture("label")` for intermediate frames.

## Replay Viewer (`recording/replay.py` + `recording/viewer/`)

A single-page HTML/JS app served by a tiny local HTTP server.

### Usage

```bash
python -m recording.replay runs/2026-10-20_episode-3/
```

### Features

- Frame timeline: all frames in sequence, grouped by turn
- Step controls: arrow keys to step, space to play/pause
- Decision panel: reasoning, tool call, args, state report
- Transcript panel: transcript update for current turn
- Turn jump: input to jump to a specific turn
- Intermediate frames: sub-steps within a turn
- Timing info: decision latency, turn duration

### Implementation

- Server: `http.server` (stdlib)
- Viewer: single `index.html` with inline CSS + JS, no build step, no framework
- Data: server reads `log.jsonl` and serves it as JSON; frames served as static files
- Playback: JS timer, configurable speed

### File Layout

```
recording/
  __init__.py
  recorder.py          # Recorder class
  replay.py            # CLI entry point
  viewer/
    index.html         # single-page app (HTML + CSS + JS inline)
```

## Dependencies

- Recorder: stdlib only
- Replay server: stdlib only
- No frontend framework, no build step

## Open Items

- Frame storage size: full-resolution PNGs add up. JPEG/WebP if disk becomes an issue.
- Viewer is read-only. No annotation.
- One episode at a time. Episode list page could be added later.
