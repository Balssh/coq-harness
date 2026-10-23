"""TCP relay between the Windows bridge and the WSL harness.

The Windows firewall blocks inbound connections from WSL to Windows,
but Windows can connect OUT to WSL. So the bridge connects to this relay,
and the harness connects to localhost. The relay pipes bytes between them.

  Bridge (Windows) ──connects to──> 0.0.0.0:9091 (relay)
  Harness (WSL)    ──connects to──> 127.0.0.1:9090 (relay)
  Relay pipes data bidirectionally between the two connections.

Loops to handle sequential sessions (bridge reconnects, harness reconnects).
If the bridge disconnects while we are still waiting for the harness, the
session is abandoned and the relay goes back to waiting for a bridge.

Usage: python -m client.relay [bridge_port] [harness_port]
"""

import select
import socket
import sys
import threading


def _pipe(src: socket.socket, dst: socket.socket, label: str) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass
        print(f"[relay] {label} pipe closed", flush=True)


def _relay_session(bridge_conn: socket.socket, harness_conn: socket.socket) -> None:
    """Pipe data between one bridge and one harness connection until either closes."""
    t1 = threading.Thread(
        target=_pipe, args=(bridge_conn, harness_conn, "bridge->harness"), daemon=True
    )
    t2 = threading.Thread(
        target=_pipe, args=(harness_conn, bridge_conn, "harness->bridge"), daemon=True
    )
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def _bridge_alive(conn: socket.socket) -> bool:
    """Check (non-blocking) whether the bridge connection is still open."""
    try:
        readable, _, _ = select.select([conn], [], [], 0)
        if not readable:
            return True
        # Readable with no pending request means EOF (the bridge only speaks
        # when spoken to, so real data here is unexpected but harmless).
        return conn.recv(1, socket.MSG_PEEK) != b""
    except OSError:
        return False


def _accept_harness(
    listener: socket.socket, bridge_conn: socket.socket, poll: float = 0.5
) -> tuple[socket.socket, tuple] | None:
    """Accept a harness connection, but give up if the bridge dies first.

    Returns (conn, addr), or None if the bridge disconnected while waiting.
    """
    listener.settimeout(poll)
    try:
        while True:
            try:
                return listener.accept()
            except socket.timeout:
                if not _bridge_alive(bridge_conn):
                    return None
    finally:
        listener.settimeout(None)


def main(bridge_port: int = 9091, harness_port: int = 9090) -> None:
    # Persistent listeners
    bridge_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bridge_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bridge_listener.bind(("0.0.0.0", bridge_port))
    bridge_listener.listen(5)
    print(f"[relay] Listening for bridge on 0.0.0.0:{bridge_port}", flush=True)

    harness_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    harness_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    harness_listener.bind(("127.0.0.1", harness_port))
    harness_listener.listen(5)
    print(f"[relay] Listening for harness on 127.0.0.1:{harness_port}", flush=True)

    try:
        while True:
            print("[relay] Waiting for bridge connection ...", flush=True)
            bridge_conn, bridge_addr = bridge_listener.accept()
            print(f"[relay] Bridge connected from {bridge_addr}", flush=True)

            print("[relay] Waiting for harness connection ...", flush=True)
            accepted = _accept_harness(harness_listener, bridge_conn)
            if accepted is None:
                print("[relay] Bridge disconnected before harness connected; "
                      "waiting for next bridge ...", flush=True)
                bridge_conn.close()
                continue
            harness_conn, harness_addr = accepted
            print(f"[relay] Harness connected from {harness_addr}", flush=True)

            print("[relay] Relay active — piping bridge <-> harness", flush=True)
            _relay_session(bridge_conn, harness_conn)
            print("[relay] Session ended, waiting for next ...", flush=True)
    except KeyboardInterrupt:
        print("\n[relay] Shutting down", flush=True)
    finally:
        bridge_listener.close()
        harness_listener.close()


if __name__ == "__main__":
    _bridge_port = int(sys.argv[1]) if len(sys.argv) > 1 else 9091
    _harness_port = int(sys.argv[2]) if len(sys.argv) > 2 else 9090
    main(bridge_port=_bridge_port, harness_port=_harness_port)
