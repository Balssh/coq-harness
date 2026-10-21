"""TCP relay between the Windows bridge and the WSL harness.

The Windows firewall blocks inbound connections from WSL to Windows,
but Windows can connect OUT to WSL. So the bridge connects to this relay,
and the harness connects to localhost. The relay pipes bytes between them.

  Bridge (Windows) ──connects to──> 0.0.0.0:9091 (relay)
  Harness (WSL)    ──connects to──> 127.0.0.1:9090 (relay)
  Relay pipes data bidirectionally between the two connections.

Loops to handle sequential sessions (bridge reconnects, harness reconnects).
"""

import socket
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


def main() -> None:
    bridge_port = 9091   # Windows bridge connects here
    harness_port = 9090  # WSL harness connects here (localhost)

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

    while True:
        print("[relay] Waiting for bridge connection ...", flush=True)
        bridge_conn, bridge_addr = bridge_listener.accept()
        print(f"[relay] Bridge connected from {bridge_addr}", flush=True)

        print("[relay] Waiting for harness connection ...", flush=True)
        harness_conn, harness_addr = harness_listener.accept()
        print(f"[relay] Harness connected from {harness_addr}", flush=True)

        print("[relay] Relay active — piping bridge <-> harness", flush=True)
        _relay_session(bridge_conn, harness_conn)
        print("[relay] Session ended, waiting for next ...", flush=True)


if __name__ == "__main__":
    main()
