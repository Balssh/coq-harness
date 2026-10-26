"""MCP client for the CoQ C# mod bridge.

Connects to the in-game MCP server over TCP (localhost:47321) and provides
a clean Python API for getting game state and sending commands.

Protocol: length-prefixed JSON frames.
  [4 bytes: big-endian uint32 length][UTF-8 JSON payload]

The server broadcasts state snapshots after every turn.
The client sends commands and receives command results.
"""

import itertools
import json
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any


class McpError(Exception):
    pass


def resolve_host(port: int = 47321) -> str:
    """Pick the MCP server host: localhost if reachable, else the WSL gateway.

    Qud runs on Windows. In WSL mirrored mode, localhost is shared; in NAT mode
    the Windows host is reachable via the default gateway (from `ip route`).
    """
    candidates = ["127.0.0.1"]
    try:
        out = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5)
        for line in out.stdout.splitlines():
            if line.startswith("default via"):
                candidates.append(line.split()[2])
    except Exception:
        pass
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            for line in f:
                if line.startswith("nameserver"):
                    candidates.append(line.split()[1])
    except OSError:
        pass
    for host in candidates:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return host
        except OSError:
            continue
    return candidates[0]


_cmd_counter = itertools.count()


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise McpError("Connection closed by server")
        buf.extend(chunk)
    return bytes(buf)


@dataclass
class GameStateData:
    """Structured game state from the MCP server."""
    raw: dict = field(default_factory=dict)

    @property
    def player(self) -> dict:
        return self.raw.get("player", {})

    @property
    def zone(self) -> dict:
        return self.raw.get("zone", {})

    @property
    def cells(self) -> list[dict]:
        return self.raw.get("cells", [])

    @property
    def messages(self) -> list[str]:
        msgs = self.raw.get("messages", [])
        if isinstance(msgs, list):
            return [m for m in msgs if isinstance(m, str)]
        return []

    @property
    def msg_count(self) -> int:
        return self.raw.get("msgCount", 0)

    @property
    def effects(self) -> list[dict]:
        return self.raw.get("effects", [])

    @property
    def inventory(self) -> list[dict]:
        return self.raw.get("inventory", [])

    @property
    def abilities(self) -> list[dict]:
        return self.raw.get("abilities", [])

    @property
    def time(self) -> dict:
        return self.raw.get("time", {})

    @property
    def hp(self) -> int | None:
        return self.player.get("hp")

    @property
    def hp_max(self) -> int | None:
        return self.player.get("hpMax")

    @property
    def level(self) -> int | None:
        return self.player.get("level")

    @property
    def xp(self) -> int | None:
        return self.player.get("xp")

    @property
    def name(self) -> str | None:
        return self.player.get("name")

    @property
    def location(self) -> str | None:
        return self.player.get("location")

    @property
    def position(self) -> tuple[int, int] | None:
        x = self.player.get("x")
        y = self.player.get("y")
        if x is not None and y is not None:
            return (x, y)
        return None

    @property
    def in_combat(self) -> bool:
        return self.player.get("inCombat", False)

    @property
    def screen(self) -> str | None:
        return self.raw.get("screen")

    @property
    def in_game(self) -> bool:
        return self.raw.get("inGame", True)

    @property
    def is_dead(self) -> bool:
        return self.raw.get("isDead", False)

    @property
    def segment(self) -> int | None:
        return self.time.get("segment")

    def creatures_nearby(self, max_distance: int = 10) -> list[dict]:
        return [
            c for c in self.cells
            if c.get("isCreature") and c.get("distance", 999) <= max_distance
        ]

    def hostile_nearby(self, max_distance: int = 10) -> list[dict]:
        return [
            c for c in self.creatures_nearby(max_distance)
            if c.get("isHostile")
        ]

    def items_on_ground(self) -> list[dict]:
        return [
            c for c in self.cells
            if c.get("isItem") and c.get("distance", 999) == 0
        ]

    def format_for_prompt(self, max_cells: int = 100, max_messages: int = 30) -> str:
        """Format the game state as text for the LLM prompt."""
        lines = []

        p = self.player
        lines.append(f"=== Player: {p.get('name', '?')} ===")
        lines.append(
            f"HP: {p.get('hp', '?')}/{p.get('hpMax', '?')}  "
            f"Level: {p.get('level', '?')}  XP: {p.get('xp', '?')}/{p.get('xpNext', '?')}"
        )
        lines.append(
            f"Stats: STR {p.get('strength', '?')} AGI {p.get('agility', '?')} "
            f"TOU {p.get('toughness', '?')} WIL {p.get('willpower', '?')} "
            f"EGO {p.get('ego', '?')} INT {p.get('intelligence', '?')}"
        )
        lines.append(
            f"Combat: AV {p.get('av', '?')} DV {p.get('dv', '?')} MA {p.get('ma', '?')} "
            f"QN {p.get('qn', '?')} MS {p.get('ms', '?')}"
        )
        lines.append(
            f"Hunger: {p.get('hunger', '?')}  Thirst: {p.get('thirst', '?')}  "
            f"Temp: {p.get('temperature', '?')}  Weight: {p.get('weight', '?')}%"
        )
        pos = self.position
        if pos:
            lines.append(f"Position: ({pos[0]}, {pos[1]})")
        lines.append(f"Location: {p.get('location', '?')}")
        lines.append(f"In Combat: {p.get('inCombat', False)}")

        z = self.zone
        if z:
            lines.append(f"\n=== Zone: {z.get('name', '?')} ({z.get('width', '?')}x{z.get('height', '?')}) ===")
            lines.append(f"Zone ID: {z.get('id', '?')}")

        t = self.time
        if t:
            lines.append(f"\n=== Time: Day {t.get('day', '?')}, Hour {t.get('hour', '?')} "
                        f"({'Day' if t.get('isDay') else 'Night'}) ===")

        effects = self.effects
        if effects:
            lines.append(f"\n=== Effects ({len(effects)}) ===")
            for e in effects[:20]:
                dur = e.get("duration", "?")
                lines.append(f"  - {e.get('name', '?')} ({dur} turns)")

        abilities = self.abilities
        if abilities:
            lines.append(f"\n=== Abilities ({len(abilities)}) ===")
            for a in abilities[:20]:
                lines.append(f"  - {a.get('name', '?')} [{a.get('hotkey', '?')}] ({a.get('command', '?')})")

        inventory = self.inventory
        if inventory:
            lines.append(f"\n=== Inventory ({len(inventory)}) ===")
            for item in inventory[:30]:
                slot = item.get("slot", "")
                equipped = " [equipped]" if item.get("equipped") else ""
                lines.append(f"  - {item.get('name', '?')}{equipped}")

        cells = self.cells
        if cells:
            creatures = [c for c in cells if c.get("isCreature")]
            items = [c for c in cells if c.get("isItem")]
            doors = [c for c in cells if c.get("isDoor")]
            containers = [c for c in cells if c.get("isContainer")]
            walls = [c for c in cells if c.get("blocksMovement") and not c.get("isCreature")]

            lines.append(f"\n=== Nearby Objects ===")
            lines.append(f"Creatures: {len(creatures)}, Items: {len(items)}, "
                        f"Doors: {len(doors)}, Containers: {len(containers)}, Walls: {len(walls)}")

            nearby = sorted(cells, key=lambda c: c.get("distance", 999))[:max_cells]
            for c in nearby:
                dist = c.get("distance", "?")
                pos_str = f"({c.get('x', '?')},{c.get('y', '?')})"
                name = c.get("name", "?")
                tags = []
                if c.get("isCreature"):
                    tags.append("creature")
                    if c.get("isHostile"): tags.append("HOSTILE")
                    elif c.get("isFriendly"): tags.append("friendly")
                    elif c.get("isNeutral"): tags.append("neutral")
                    hp = c.get("hp", "?")
                    hp_max = c.get("hpMax", "?")
                    lvl = c.get("level", "?")
                    tags.append(f"HP {hp}/{hp_max}")
                    tags.append(f"Lvl {lvl}")
                if c.get("isItem"): tags.append("item")
                if c.get("isDoor"): tags.append("door")
                if c.get("isContainer"): tags.append("container")
                if c.get("blocksMovement"): tags.append("blocks")
                lines.append(f"  {name} at {pos_str} (dist {dist}) [{', '.join(tags)}]")

        msgs = self.messages[-max_messages:]
        if msgs:
            lines.append(f"\n=== Recent Messages ({len(msgs)}) ===")
            for m in msgs:
                lines.append(f"  {m}")

        return "\n".join(lines)


class McpClient:
    """Client for the CoQ MCP bridge server."""

    def __init__(
        self,
        host: str | None = None,
        port: int = 47321,
        timeout: float = 30.0,
    ) -> None:
        self.host = host or resolve_host(port)
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._latest_state: GameStateData | None = None
        self._state_event = threading.Event()
        self._command_results: dict[str, Any] = {}
        self._result_events: dict[str, threading.Event] = {}
        self._running = False
        self._reader_thread: threading.Thread | None = None

    def connect(self) -> None:
        if self._sock is not None:
            return
        self._sock = socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        )
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def close(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def reconnect(self) -> None:
        self.close()
        self.connect()

    def _send(self, obj: dict) -> None:
        if self._sock is None:
            raise McpError("Not connected")
        payload = json.dumps(obj).encode("utf-8")
        frame = struct.pack(">I", len(payload)) + payload
        with self._lock:
            self._sock.sendall(frame)

    def _read_loop(self) -> None:
        while self._running and self._sock is not None:
            try:
                header = _recv_exactly(self._sock, 4)
                (length,) = struct.unpack(">I", header)
                if length > 16 * 1024 * 1024:
                    break
                payload = _recv_exactly(self._sock, length)
                data = json.loads(payload.decode("utf-8"))
                self._handle_message(data)
            except (McpError, OSError, json.JSONDecodeError):
                if not self._running:
                    break
                self._sock = None
                self._state_event.set()
                for ev in self._result_events.values():
                    ev.set()
                break

    def _handle_message(self, data: dict) -> None:
        msg_type = data.get("type", "")

        if msg_type == "state":
            self._latest_state = GameStateData(raw=data)
            self._state_event.set()
        elif msg_type == "command_result":
            result = data.get("result", {})
            cmd_id = result.get("cmdId", "default")
            self._command_results[cmd_id] = result
            if cmd_id in self._result_events:
                self._result_events[cmd_id].set()
        elif msg_type == "error":
            pass

    def get_state(self, timeout: float = 10.0) -> GameStateData:
        """Request a fresh state snapshot and wait for it."""
        if self._sock is None:
            raise McpError("Not connected — server disconnected")
        self._state_event.clear()
        self._send({"type": "get_state"})
        if self._state_event.wait(timeout=timeout):
            if self._sock is None:
                raise McpError("Disconnected while waiting for state")
            if self._latest_state is not None:
                return self._latest_state
        raise McpError("Timed out waiting for state")

    def send_command(self, action: str, **params) -> dict:
        """Send a command and wait for the result."""
        cmd_id = f"{action}_{next(_cmd_counter)}"
        cmd = {"type": "command", "cmdId": cmd_id, **params, "action": action}

        event = threading.Event()
        self._result_events[cmd_id] = event

        if self._sock is None:
            self._result_events.pop(cmd_id, None)
            raise McpError("Not connected — server disconnected")

        self._send(cmd)

        if event.wait(timeout=self.timeout):
            self._result_events.pop(cmd_id, None)
            if self._sock is None and cmd_id not in self._command_results:
                raise McpError("Disconnected while waiting for command result")
            result = self._command_results.pop(cmd_id, {})
            return result
        else:
            self._result_events.pop(cmd_id, None)
            raise McpError(f"Timed out waiting for command result: {action}")

    def wait_for_turn(self, timeout: float = 30.0) -> GameStateData:
        """Wait for the game segment (turn counter) to advance."""
        old_state = self._latest_state
        old_segment = old_state.segment if old_state else None
        old_msg_count = old_state.msg_count if old_state else 0

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.1)
            current = self._latest_state
            if current is None:
                continue
            new_segment = current.segment
            if new_segment is not None and old_segment is not None and new_segment > old_segment:
                return current
            if new_segment is not None and old_segment is None:
                return current
            if current.msg_count > old_msg_count and current is not old_state:
                return current

        if self._latest_state is not None:
            return self._latest_state
        raise McpError("Timed out waiting for turn")

    @property
    def latest_state(self) -> GameStateData | None:
        return self._latest_state

    def __enter__(self) -> "McpClient":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.close()


_client: McpClient | None = None


def get_client() -> McpClient:
    global _client
    if _client is None:
        raise McpError("MCP client not initialized. Call init_client() first.")
    return _client


def init_client(
    host: str | None = None,
    port: int = 47321,
    timeout: float = 30.0,
) -> McpClient:
    global _client
    if _client is not None:
        _client.close()
    _client = McpClient(host=host, port=port, timeout=timeout)
    _client.connect()
    return _client
