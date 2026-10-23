"""Bridge socket server (Windows side).

Long-lived process that owns capture, input, and frame-diffing.
Exposes a length-prefixed JSON/PNG socket API on TCP port 9090.

Protocol:
  [4 bytes: uint32 big-endian payload length][payload bytes]

  Requests are JSON with an "action" field.
  Responses to grab/grab_region are raw PNG bytes (or a JSON error object).
  All other responses are JSON.

Reliability:
- The bridge can start before the Qud window exists; the window is attached
  lazily on the first request that needs it, and re-attached if the window
  is re-created (new HWND).
- A failed request (bad JSON, missing window, capture error) returns a JSON
  error and keeps the session alive. Only a dead socket ends a session.
- Commands are serialized with a lock: input is global and the frame-differ
  baseline is shared, so concurrent connections must not interleave
  keys/wait_for_change.
"""

import argparse
import json
import socket
import struct
import threading
import time

import win32gui

from bridge.capture import WindowCapture
from bridge.framediff import FrameDiffer
from bridge.input import InputInjector

# ---------------------------------------------------------------------------
# Framing helpers
# ---------------------------------------------------------------------------

def _recv_exactly(conn: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Client disconnected")
        buf.extend(chunk)
    return bytes(buf)


def _recv_message(conn: socket.socket) -> bytes:
    header = _recv_exactly(conn, 4)
    (length,) = struct.unpack(">I", header)
    return _recv_exactly(conn, length)


def _send_message(conn: socket.socket, payload: bytes) -> None:
    conn.sendall(struct.pack(">I", len(payload)) + payload)


def _send_json(conn: socket.socket, obj: dict) -> None:
    _send_message(conn, json.dumps(obj).encode("utf-8"))


def _send_error(conn: socket.socket, message: str) -> None:
    _send_json(conn, {"error": message})


# ---------------------------------------------------------------------------
# Bridge server
# ---------------------------------------------------------------------------

class BridgeServer:
    def __init__(
        self,
        window_title: str = "Caves of Qud",
        log_region: tuple[int, int, int, int] = (0, 0, 0, 0),  # x, y, w, h
        diff_threshold: int = 50,
        poll_interval: float = 0.05,
    ) -> None:
        self.window_title = window_title
        self.log_region = log_region
        self.diff_threshold = diff_threshold
        self.poll_interval = poll_interval
        self._start_time = time.monotonic()

        # Serializes command dispatch. Input is global and the differ
        # baseline is shared state, so commands must not interleave.
        self._cmd_lock = threading.Lock()

        # Window/capture/input are attached lazily: the bridge may start
        # before Qud is launched.
        self.hwnd: int | None = None
        self.capture: WindowCapture | None = None
        self.input: InputInjector | None = None
        self.differ: FrameDiffer | None = None

        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd:
            self._attach_window(hwnd)
        else:
            print(f"[bridge] Window {window_title!r} not found yet; will attach on first request")

    # ------------------------------------------------------------------
    # Window / capture lifecycle
    # ------------------------------------------------------------------

    def _attach_window(self, hwnd: int) -> None:
        """(Re)create capture, input, and differ for the given HWND."""
        self.hwnd = hwnd
        capture = WindowCapture(self.window_title, hwnd=hwnd)
        capture.start()
        old_capture = self.capture
        self.capture = capture
        self.input = InputInjector(hwnd)
        region = self.log_region if self.log_region != (0, 0, 0, 0) else (0, 0, 1, 1)
        self.differ = FrameDiffer(
            capture,
            region=region,
            threshold=self.diff_threshold,
            poll_interval=self.poll_interval,
        )
        if old_capture is not None:
            old_capture.stop()
        print(f"[bridge] Capture attached (HWND={hwnd}, log region: {self.log_region})")

    def _ensure_window(self) -> None:
        """Make sure the window is attached and the HWND is still valid.

        Raises RuntimeError if the window cannot be found — callers turn
        that into a JSON error response without dropping the session.
        """
        if self.capture is not None and self.hwnd and win32gui.IsWindow(self.hwnd):
            return
        new_hwnd = win32gui.FindWindow(None, self.window_title)
        if not new_hwnd:
            raise RuntimeError(f"Window not found: {self.window_title!r}")
        if self.capture is None:
            print(f"[bridge] Found window {self.window_title!r} (HWND={new_hwnd})")
        else:
            print(f"[bridge] Window re-found: HWND {self.hwnd} -> {new_hwnd}")
        self._attach_window(new_hwnd)

    # ------------------------------------------------------------------
    # Request dispatch
    # ------------------------------------------------------------------

    def handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """Handle one client connection (sequential command processing)."""
        print(f"[bridge] Client connected: {addr}")
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        try:
            while True:
                # A dead socket ends the session; anything else does not.
                payload = _recv_message(conn)
                try:
                    self._handle_request(conn, payload)
                except Exception as exc:
                    # Per-request failure: report it, keep the session alive.
                    print(f"[bridge] Request failed for {addr}: {exc}")
                    try:
                        _send_error(conn, str(exc))
                    except OSError:
                        raise ConnectionError("Client disconnected")
        except (ConnectionError, socket.error):
            print(f"[bridge] Client disconnected: {addr}")
        finally:
            conn.close()

    def _handle_request(self, conn: socket.socket, payload: bytes) -> None:
        try:
            request = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Malformed request: {exc}") from exc
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object")
        action = request.get("action", "")

        if action == "ping":
            # ping never requires the game window — the harness polls it
            # while waiting for Qud to be launched.
            _send_json(conn, {
                "status": "ok",
                "uptime": round(time.monotonic() - self._start_time, 3),
                "capture_alive": self.capture.is_alive if self.capture else False,
                "frame_age": self.capture.frame_age if self.capture else None,
            })
            return

        # All other actions need the game window and must not interleave.
        with self._cmd_lock:
            self._ensure_window()
            assert self.capture is not None and self.input is not None and self.differ is not None

            if action == "grab":
                png = self.capture.grab_png()
                _send_message(conn, png)

            elif action == "grab_region":
                x = int(request["x"])
                y = int(request["y"])
                w = int(request["w"])
                h = int(request["h"])
                png = self.capture.grab_region_png(x, y, w, h)
                _send_message(conn, png)

            elif action == "keys":
                keys = request.get("keys", [])
                if not isinstance(keys, list):
                    raise ValueError("'keys' must be a list of key names")
                self.differ.reset_baseline()
                self.input.send_chord(keys)
                _send_json(conn, {"status": "ok"})

            elif action == "keys_seq":
                keys = request.get("keys", [])
                if not isinstance(keys, list):
                    raise ValueError("'keys' must be a list of key names")
                delay = float(request.get("delay", 0.08))
                self.differ.reset_baseline()
                self.input.send_sequence(keys, delay=delay)
                _send_json(conn, {"status": "ok"})

            elif action == "key_down":
                key = request.get("key", "")
                self.differ.reset_baseline()
                self.input.key_down(key)
                _send_json(conn, {"status": "ok"})

            elif action == "key_up":
                key = request.get("key", "")
                self.input.key_up(key)
                _send_json(conn, {"status": "ok"})

            elif action == "wait_for_change":
                timeout = float(request.get("timeout", 3.0))
                changed, elapsed = self.differ.wait_for_change(timeout)
                _send_json(conn, {
                    "changed": changed,
                    "elapsed": round(elapsed, 3),
                })

            else:
                _send_error(conn, f"Unknown action: {action!r}")

    # ------------------------------------------------------------------
    # Serving
    # ------------------------------------------------------------------

    def serve(self, host: str = "0.0.0.0", port: int = 9090) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(5)
        print(f"[bridge] Listening on {host}:{port}")
        try:
            while True:
                try:
                    conn, addr = sock.accept()
                except OSError as exc:
                    print(f"[bridge] Accept failed: {exc}, continuing ...")
                    time.sleep(0.5)
                    continue
                t = threading.Thread(
                    target=self.handle_connection, args=(conn, addr), daemon=True
                )
                t.start()
        except KeyboardInterrupt:
            print("\n[bridge] Shutting down")
        finally:
            if self.capture is not None:
                self.capture.stop()
            sock.close()

    def connect(self, host: str, port: int) -> None:
        """Connect to a WSL relay instead of listening.

        Used when the Windows firewall blocks inbound connections from WSL.
        The bridge initiates an outbound connection to the relay, which then
        pipes data between the bridge and the WSL harness.

        Reconnects automatically if the relay or harness disconnects.
        """
        import time as _time
        while True:
            try:
                print(f"[bridge] Connecting to relay at {host}:{port} ...")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((host, port))
                print(f"[bridge] Connected to relay at {host}:{port}")
                self.handle_connection(sock, (host, port))
            except KeyboardInterrupt:
                print("\n[bridge] Shutting down")
                break
            except (ConnectionError, socket.error, OSError) as exc:
                print(f"[bridge] Connection lost: {exc}, retrying in 2s ...")
                _time.sleep(2)
            else:
                print("[bridge] Client disconnected, waiting for relay ...")
                _time.sleep(1)
        if self.capture is not None:
            self.capture.stop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Caves of Qud bridge server")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--window-title", default="Caves of Qud")
    parser.add_argument(
        "--log-region",
        type=int,
        nargs=4,
        metavar=("X", "Y", "W", "H"),
        default=[0, 0, 0, 0],
        help="Log region for turn detection: x y w h (0 0 0 0 = disabled)",
    )
    parser.add_argument("--diff-threshold", type=int, default=50)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    parser.add_argument(
        "--connect",
        type=str,
        default=None,
        metavar="HOST:PORT",
        help="Connect to WSL relay at HOST:PORT instead of listening (for firewall workaround)",
    )
    args = parser.parse_args()

    log_region = tuple(args.log_region)
    server = BridgeServer(
        window_title=args.window_title,
        log_region=log_region,
        diff_threshold=args.diff_threshold,
        poll_interval=args.poll_interval,
    )
    if args.connect:
        host, port_str = args.connect.rsplit(":", 1)
        server.connect(host, int(port_str))
    else:
        server.serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
