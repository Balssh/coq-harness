# Spec: Windows Bridge

## Purpose

One long-lived Python process on Windows that owns everything hardware-adjacent:
screen capture (Windows Graphics Capture), input injection (PostMessage / SendInput),
and frame-diffing for turn detection. Exposes a socket API that the WSL side calls.

The bridge is **dumb infrastructure**. It doesn't know what Qud is, what a "turn" means
beyond "the log region changed", or what the agent is trying to do. It just captures,
injects, and diffs.

## Process Model

- Single process, started manually (or via a startup script) before a run begins.
- Multi-threaded internally:
  - **Main thread**: socket accept loop, spawns a handler thread per connection.
  - **Capture thread**: WGC capture loop running continuously (or on-demand — TBD).
  - **Handler threads**: one per WSL client connection, process commands sequentially.
- The bridge stays alive across episodes. The WSL side connects/disconnects as needed.

## Socket Protocol

TCP socket. Default port: **9090** (configurable via CLI arg).

### Framing

Every message in both directions is length-prefixed:

```
[4 bytes: uint32 big-endian payload length][payload bytes]
```

This prevents message bleeding on a stream socket.

### Requests (WSL → Windows)

Payload is JSON (UTF-8). All requests have an `action` field.

| Action | Fields | Response |
|--------|--------|----------|
| `grab` | — | Raw PNG bytes (full window frame) |
| `grab_region` | `x`, `y`, `w`, `h` | Raw PNG bytes (cropped region) |
| `keys` | `keys`: array of key names (e.g. `["up"]`, `["shift", "up"]`) | JSON `{"status": "ok"}` |
| `key_down` | `key`: key name | JSON `{"status": "ok"}` |
| `key_up` | `key`: key name | JSON `{"status": "ok"}` |
| `wait_for_change` | `timeout`: float (seconds) | JSON `{"changed": bool, "elapsed": float}` |
| `ping` | — | JSON `{"status": "ok", "uptime": float}` |

### Responses (Windows → WSL)

- `grab` / `grab_region`: payload is raw PNG bytes (no JSON wrapper).
- All other actions: payload is JSON (UTF-8).

### Key Names

Use a fixed keymap (see `input.py`). Supported keys:

- Directions: `up`, `down`, `left`, `right`, `up_left`, `up_right`, `down_left`, `down_right`
- Modifiers: `shift`, `ctrl`, `alt`
- Actions: `enter`, `escape`, `tab`, `space`, `backspace`
- Function keys: `f1`–`f12`
- Letters: `a`–`z`
- Digits: `0`–`9`
- Numpad: `num_0`–`num_9`, `num_add`, `num_sub`, `num_mul`, `num_div`, `num_enter`

Key combinations in `keys` are sent as a chord: all keys go down in order, then all
come up in reverse order. E.g. `["shift", "up"]` = Shift+Up.

## API Endpoints (detailed)

### `grab`
Returns a PNG-encoded screenshot of the Qud window (full window, not full screen).
Captured via WGC by window title.

### `grab_region`
Returns a PNG of a sub-region: `x`, `y` are top-left offset in window coordinates,
`w`, `h` are dimensions.

### `keys`
Sends a key chord. Implementation:
1. Try `PostMessage(WM_KEYDOWN)` for each key to the Qud HWND.
2. Small delay (~30ms).
3. `PostMessage(WM_KEYUP)` for each key in reverse order.
4. If PostMessage fails (see spike results), fall back to `AttachThreadInput` +
   `AllowSetForegroundWindow` + `SendInput` + restore previous foreground.

### `key_down` / `key_up`
For holding a key across multiple commands (e.g., for movement that requires
holding a direction). Rarely needed; most actions are chords.

### `wait_for_change`
Blocks until the **message log region** changes (frame-diff detects new pixels),
or until `timeout` seconds elapse. Returns whether a change was detected.

The log region is a fixed rectangle on the right side of the Qud window. Its
coordinates are configured at bridge startup (or auto-detected — TBD).

This is the **turn clock**. The WSL side calls this after every action.

### `ping`
Health check. Returns bridge uptime in seconds.

## Module Breakdown

### `bridge/server.py`
- Socket server (TCP, threaded).
- Parses length-prefixed messages.
- Dispatches to capture/input/framediff modules.
- CLI args: `--port`, `--window-title`, `--log-region x y w h`.

### `bridge/capture.py`
- WGC capture by window title.
- Finds HWND by title (via `win32gui.FindWindow`).
- Starts a `Windows.Graphics.Capture` session targeting that HWND.
- `grab() -> bytes`: returns latest frame as PNG bytes (via Pillow).
- `grab_region(x, y, w, h) -> bytes`: crops the latest frame, returns PNG bytes.
- Keeps the latest frame in memory (updated by WGC callback or polled).

### `bridge/input.py`
- Keymap: string name → virtual key code + scan code.
- `send_chord(keys: list[str])`: PostMessage-first, SendInput fallback.
- `key_down(key: str)`, `key_up(key: str)`: individual key events.
- Focus management for the SendInput fallback:
  `AttachThreadInput` + `AllowSetForegroundWindow` + restore previous foreground.

### `bridge/framediff.py`
- `wait_for_change(log_region: tuple, timeout: float) -> bool`:
  - Captures the log region of the current frame.
  - Compares to the previous capture (pixel-level diff via numpy).
  - If diff exceeds threshold (e.g., > 50 changed pixels), returns `True`.
  - Polls every ~50ms until change or timeout.
- Threshold and poll interval are configurable.

## Dependencies

```
python >= 3.10
pywin32          # win32gui, win32api, win32con
windows-capture  # WGC bindings
numpy            # frame diffing
pillow           # PNG encoding, image cropping
```

Install: `uv pip install pywin32 windows-capture numpy pillow`

## Configuration

- Window title: default `"Caves of Qud"` (configurable).
- Log region: default coordinates TBD (need to measure from a Qud screenshot).
- Port: default `9090`.
- Diff threshold: default `50` changed pixels.
- Poll interval: default `50ms`.

## Error Handling

- **Window not found**: `grab` returns an error JSON `{"error": "window not found"}`.
- **WGC session fails**: log error, retry on next `grab` call.
- **Client disconnects**: handler thread cleans up, bridge keeps running.
- **Bridge crash**: WSL side detects via `ping` timeout, can attempt reconnect.
  Bridge should be restarted manually (or via a watchdog script — future work).

## Open Questions / Spikes

1. **PostMessage when unfocused**: Does Qud process `PostMessage(WM_KEYDOWN)` when
   the window doesn't have focus? Test: alt-tab away, send PostMessage, check if
   the character moves. If not, the SendInput fallback requires focus — meaning
   the user can't alt-tab freely during a run.

2. **WGC when occluded**: Does WGC return fresh frames when the window is fully
   covered by another window? The docs say yes, but verify with a Unity game.

3. **WGC when off-screen**: Does WGC work when the window is dragged partially
   or fully off the monitor? (Windows may stop rendering off-screen windows.)

4. **Log region auto-detection**: Can we auto-detect the log region from a
   screenshot (e.g., find the rightmost column of text)? Or just hardcode
   coordinates after measuring once?

5. **Capture latency**: How fast is WGC capture → PNG encode? If it's >100ms,
   we might want to skip PNG encoding and send raw pixel arrays (larger but faster).

## Testing Strategy

1. **Manual smoke test**: Start bridge, connect from WSL with a test script,
   call `ping`, `grab` (save PNG, verify it looks like Qud), `keys(["up"])`
   (verify character moves in-game).
2. **PostMessage spike**: See open question #1.
3. **WGC occlusion spike**: See open question #2.
4. **Turn clock test**: Send a movement key, call `wait_for_change`, verify
   it returns `True` quickly. Send a no-op (e.g., press a key that does nothing),
   verify it times out.
