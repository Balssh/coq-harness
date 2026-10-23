"""WSL-side bridge client.

Sync, singleton, always-fresh, fail-loud. Talks to the Windows bridge
over a length-prefixed TCP socket.
"""

import json
import socket
import struct

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class BridgeError(Exception):
    """Raised on any bridge communication failure."""
    pass


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise BridgeError("Bridge closed the connection")
        buf.extend(chunk)
    return bytes(buf)


class BridgeClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 9090,
        timeout: float = 30.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        if self._sock is not None:
            return
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            # Length-prefixed request/response — don't let Nagle batch them
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (ConnectionRefusedError, OSError, socket.timeout) as exc:
            raise BridgeError(
                f"Cannot connect to bridge at {self.host}:{self.port}: {exc}"
            ) from exc

    def reconnect(self) -> None:
        """Drop the current connection (if any) and connect again."""
        self.close()
        self.connect()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _ensure_connected(self) -> socket.socket:
        if self._sock is None:
            raise BridgeError("Not connected. Call connect() first.")
        return self._sock

    def _send_request(self, obj: dict) -> None:
        sock = self._ensure_connected()
        payload = json.dumps(obj).encode("utf-8")
        try:
            sock.sendall(struct.pack(">I", len(payload)) + payload)
        except OSError as exc:
            raise BridgeError(f"Failed to send request: {exc}") from exc

    def _recv_response(self) -> bytes:
        sock = self._ensure_connected()
        try:
            header = _recv_exactly(sock, 4)
            (length,) = struct.unpack(">I", header)
            return _recv_exactly(sock, length)
        except BridgeError:
            raise
        except OSError as exc:
            raise BridgeError(f"Failed to receive response: {exc}") from exc

    def _recv_json(self) -> dict:
        payload = self._recv_response()
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BridgeError(f"Malformed JSON response: {exc}") from exc
        if isinstance(obj, dict) and "error" in obj:
            raise BridgeError(f"Bridge error: {obj['error']}")
        return obj

    def _recv_binary(self, what: str) -> bytes:
        """Receive a payload that should be raw bytes (PNG).

        The bridge answers grab/grab_region with raw PNG bytes, but on
        failure it sends a JSON error object instead. Detect that and raise
        instead of returning JSON bytes masquerading as an image.
        """
        payload = self._recv_response()
        if payload.startswith(_PNG_MAGIC):
            return payload
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise BridgeError(
                f"Bridge returned a malformed {what} payload ({len(payload)} bytes)"
            ) from None
        if isinstance(obj, dict) and "error" in obj:
            raise BridgeError(f"Bridge error: {obj['error']}")
        raise BridgeError(f"Bridge returned an unexpected {what} payload: {payload[:200]!r}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ping(self) -> dict:
        """Health check. Returns {"status": "ok", "uptime": float}."""
        self._send_request({"action": "ping"})
        return self._recv_json()

    def grab(self) -> bytes:
        """Full window frame as PNG bytes."""
        self._send_request({"action": "grab"})
        return self._recv_binary("grab")

    def grab_region(self, x: int, y: int, w: int, h: int) -> bytes:
        """Cropped region as PNG bytes. (x, y) = top-left in window coords."""
        self._send_request({"action": "grab_region", "x": x, "y": y, "w": w, "h": h})
        return self._recv_binary("grab_region")

    def keys(self, keys: list[str]) -> None:
        """Send a key chord, e.g. ["shift", "up"]."""
        self._send_request({"action": "keys", "keys": keys})
        self._recv_json()

    def key_down(self, key: str) -> None:
        self._send_request({"action": "key_down", "key": key})
        self._recv_json()

    def key_up(self, key: str) -> None:
        self._send_request({"action": "key_up", "key": key})
        self._recv_json()

    def wait_for_change(self, timeout: float = 3.0) -> bool:
        """Block until the log region changes or timeout. Returns True if changed."""
        self._send_request({"action": "wait_for_change", "timeout": timeout})
        # Use a longer socket timeout so the bridge has time to respond
        sock = self._ensure_connected()
        old_timeout = sock.gettimeout()
        sock.settimeout(timeout + 5.0)
        try:
            result = self._recv_json()
        finally:
            sock.settimeout(old_timeout)
        return bool(result.get("changed", False))

    def __enter__(self) -> "BridgeClient":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_client: BridgeClient | None = None


def get_client() -> BridgeClient:
    """Lazy-initialized singleton. Raises BridgeError if not connected."""
    global _client
    if _client is None:
        raise BridgeError("Bridge client not initialized. Call init_client() first.")
    return _client


def init_client(
    host: str = "localhost",
    port: int = 9090,
    timeout: float = 30.0,
) -> BridgeClient:
    """Initialize and connect the singleton bridge client."""
    global _client
    if _client is not None:
        _client.close()
    _client = BridgeClient(host=host, port=port, timeout=timeout)
    _client.connect()
    return _client
