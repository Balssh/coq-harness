# Spec: Bridge Client (WSL)

## Purpose

WSL-side Python module that connects to the Windows bridge and provides a clean,
typed API for the rest of the harness. Everything in perception, tools, and the
loop calls this module instead of touching sockets directly.

## Design Decisions

- **Sync API**: Simple request/response. No async complexity — the agent loop can
  wrap calls in `asyncio.to_thread()` if it ever needs to be async. For a single
  connection sending one command at a time, async buys nothing.
- **Singleton**: One bridge, one connection. Module-level lazy-initialized instance.
  No scenario for multiple connections exists.
- **Always fresh**: `grab()` always fetches from the bridge. No client-side caching.
- **Fail loud**: Bridge errors raise `BridgeError`. No auto-reconnect, no retries.
  If the bridge dies, the harness crashes and the user restarts. Silent failures
  are worse than loud ones for debugging.
- **Timeouts**: 5s default on all socket operations.
- **Third-party libs**: Fine to use if they simplify things, but stdlib is
  preferred when it's sufficient.

## API

```python
class BridgeError(Exception):
    """Raised on any bridge communication failure."""
    pass


class BridgeClient:
    def __init__(self, host: str = "localhost", port: int = 9090,
                 timeout: float = 5.0) -> None: ...

    def connect(self) -> None: ...
    def close(self) -> None: ...

    def ping(self) -> dict: ...
    """Health check. Returns {"status": "ok", "uptime": float}."""

    def grab(self) -> bytes: ...
    """Full window frame as PNG bytes."""

    def grab_region(self, x: int, y: int, w: int, h: int) -> bytes: ...
    """Cropped region as PNG bytes. (x, y) = top-left offset in window coords."""

    def keys(self, keys: list[str]) -> None: ...
    """Send a key chord, e.g. ["shift", "up"]."""

    def key_down(self, key: str) -> None: ...
    def key_up(self, key: str) -> None: ...

    def wait_for_change(self, timeout: float = 3.0) -> bool: ...
    """Block until the log region changes or timeout. Returns True if changed."""


_client: BridgeClient | None = None

def get_client() -> BridgeClient:
    """Lazy-initialized singleton. Raises BridgeError if not connected."""
    ...
```

## Protocol Implementation

- **Framing**: 4-byte uint32 big-endian length prefix + payload, both directions.
- **Requests**: JSON payload (UTF-8). Always has an `action` field.
- **Responses**:
  - `grab` / `grab_region`: raw PNG bytes (no JSON wrapper).
  - All other methods: JSON payload (UTF-8).
- The client knows the expected response type based on the method called — no
  type field needed in responses.

### Wire Format Examples

Request `keys(["up"])`:
```
[4 bytes: length=24][{"action": "keys", "keys": ["up"]}]
```

Response to `grab`:
```
[4 bytes: length=N][N bytes of PNG data]
```

Response to `ping`:
```
[4 bytes: length=30][{"status": "ok", "uptime": 123.45}]
```

## Error Handling

`BridgeError` is raised for:

| Condition | Cause |
|-----------|-------|
| Connection refused | Bridge not running, wrong host/port |
| Socket timeout | Bridge hung, network issue |
| Bridge returns `{"error": ...}` | Bridge-side error (e.g., window not found) |
| Malformed response | Unexpected bytes, protocol mismatch |
| Not connected | `get_client()` called before `connect()` |

No retry logic. The caller decides what to do — usually crash.

## File Layout

```
client/
  __init__.py
  bridge_client.py    # BridgeClient class, BridgeError, get_client() singleton
```

## Dependencies

Stdlib only: `socket`, `struct`, `json`.

## Testing

1. **Manual smoke test**: Start bridge on Windows, run a test script from WSL:
   ```python
   from client.bridge_client import BridgeClient
   c = BridgeClient()
   c.connect()
   print(c.ping())
   frame = c.grab()
   with open("/tmp/frame.png", "wb") as f:
       f.write(frame)
   c.keys(["up"])
   changed = c.wait_for_change(3.0)
   print(f"changed: {changed}")
   c.close()
   ```
2. **Error test**: Call `grab()` without connecting → expect `BridgeError`.
3. **Timeout test**: Call `wait_for_change(0.5)` when no action is pending →
   expect `False` after ~0.5s.
