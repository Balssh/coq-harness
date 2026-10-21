"""Bridge socket server (Windows side).

Long-lived process that owns capture, input, and frame-diffing.
Exposes a length-prefixed JSON/PNG socket API on TCP port 9090.

Protocol:
  [4 bytes: uint32 big-endian payload length][payload bytes]

  Requests are JSON with an "action" field.
  Responses to grab/grab_region are raw PNG bytes.
  All other responses are JSON.
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
        self._start_time = time.monotonic()

        # Find the window
        self.hwnd = win32gui.FindWindow(None, window_title)
        if not self.hwnd:
            raise RuntimeError(f"Window not found: {window_title!r}")

        print(f"[bridge] Found window {window_title!r} (HWND={self.hwnd})")

        # Start capture
        self.capture = WindowCapture(window_title)
        self.capture.start()
        print("[bridge] WGC capture started")

        # Set up input + frame diff
        self.input = InputInjector(self.hwnd)
        self.differ = FrameDiffer(
            self.capture,
            region=log_region if log_region != (0, 0, 0, 0) else (0, 0, 1, 1),
            threshold=diff_threshold,
            poll_interval=poll_interval,
        )
        print(f"[bridge] Log region: {log_region}, threshold: {diff_threshold}")

    def handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """Handle one client connection (sequential command processing)."""
        print(f"[bridge] Client connected: {addr}")
        try:
            while True:
                payload = _recv_message(conn)
                request = json.loads(payload.decode("utf-8"))
                action = request.get("action", "")

                if action == "ping":
                    _send_json(conn, {
                        "status": "ok",
                        "uptime": round(time.monotonic() - self._start_time, 3),
                    })

                elif action == "grab":
                    try:
                        png = self.capture.grab_png()
                        _send_message(conn, png)
                    except Exception as exc:
                        _send_error(conn, str(exc))

                elif action == "grab_region":
                    try:
                        x = int(request["x"])
                        y = int(request["y"])
                        w = int(request["w"])
                        h = int(request["h"])
                        png = self.capture.grab_region_png(x, y, w, h)
                        _send_message(conn, png)
                    except Exception as exc:
                        _send_error(conn, str(exc))

                elif action == "keys":
                    keys = request.get("keys", [])
                    try:
                        self.differ.reset_baseline()
                        self.input.send_chord(keys)
                        _send_json(conn, {"status": "ok"})
                    except Exception as exc:
                        _send_error(conn, str(exc))

                elif action == "key_down":
                    key = request.get("key", "")
                    try:
                        self.differ.reset_baseline()
                        self.input.key_down(key)
                        _send_json(conn, {"status": "ok"})
                    except Exception as exc:
                        _send_error(conn, str(exc))

                elif action == "key_up":
                    key = request.get("key", "")
                    try:
                        self.input.key_up(key)
                        _send_json(conn, {"status": "ok"})
                    except Exception as exc:
                        _send_error(conn, str(exc))

                elif action == "wait_for_change":
                    timeout = float(request.get("timeout", 3.0))
                    try:
                        changed, elapsed = self.differ.wait_for_change(timeout)
                        _send_json(conn, {
                            "changed": changed,
                            "elapsed": round(elapsed, 3),
                        })
                    except Exception as exc:
                        _send_error(conn, str(exc))

                else:
                    _send_error(conn, f"Unknown action: {action!r}")

        except (ConnectionError, socket.error):
            print(f"[bridge] Client disconnected: {addr}")
        except Exception as exc:
            print(f"[bridge] Error handling {addr}: {exc}")
        finally:
            conn.close()

    def serve(self, host: str = "0.0.0.0", port: int = 9090) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(5)
        print(f"[bridge] Listening on {host}:{port}")
        try:
            while True:
                conn, addr = sock.accept()
                t = threading.Thread(
                    target=self.handle_connection, args=(conn, addr), daemon=True
                )
                t.start()
        except KeyboardInterrupt:
            print("\n[bridge] Shutting down")
        finally:
            self.capture.stop()
            sock.close()


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
    args = parser.parse_args()

    log_region = tuple(args.log_region)
    server = BridgeServer(
        window_title=args.window_title,
        log_region=log_region,
        diff_threshold=args.diff_threshold,
        poll_interval=args.poll_interval,
    )
    server.serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
