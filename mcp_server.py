#!/usr/bin/env python3
"""MCP server bridge for Caves of Qud.

Launched by Vibe as a stdio MCP server. Connects to the in-game MCP bridge
over TCP (port 47321 on the Windows host) and exposes game actions as MCP tools.

Host: $COQ_HOST if set, else localhost (WSL mirrored networking), else the
WSL default gateway (NAT mode).

Usage: python mcp_server.py
"""

import sys
import os

# Put venv site-packages FIRST so the PyPI 'mcp' package is found
# before the local 'mcp/' directory in the project root.
_venv_sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "lib")
for _entry in os.listdir(_venv_sp):
    _path = os.path.join(_venv_sp, _entry, "site-packages")
    if os.path.isdir(_path):
        sys.path.insert(0, _path)
        break

import heapq
from collections import Counter
import itertools
import json
import re
import socket
import struct
import subprocess
import threading
import time
from typing import Any

from mcp.server.mcpserver import MCPServer

PORT = int(os.environ.get("COQ_PORT", "47321"))

# Actions that spend game time; after sending one we wait for the turn to
# resolve (or for a popup to appear) before reporting state.
TURN_TIMEOUT = 5.0

# ── TCP client for the in-game bridge ──────────────────────────────────

_cmd_counter = itertools.count()


def resolve_host(port: int = PORT) -> str:
    """$COQ_HOST, else the first of localhost / WSL gateway that accepts a connection."""
    if os.environ.get("COQ_HOST"):
        return os.environ["COQ_HOST"]
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
    return candidates[-1]


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed by server")
        buf.extend(chunk)
    return bytes(buf)


class GameBridge:
    """TCP client for the in-game MCP bridge."""

    def __init__(self, host: str | None = None, port: int = PORT, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._latest_state: dict | None = None
        self._state_event = threading.Event()
        self._command_results: dict[str, Any] = {}
        self._result_events: dict[str, threading.Event] = {}
        self._running = False
        self._reader_thread: threading.Thread | None = None
        self.warnings: list[str] = []  # auto-dismissed notices, shown in the next result

    def connect(self) -> None:
        if self._sock is not None:
            return
        host = self.host or resolve_host(self.port)
        sock = socket.create_connection((host, self.port), timeout=self.timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # The reader blocks indefinitely between broadcasts; a recv timeout
        # would be mistaken for a disconnect while the model is thinking.
        sock.settimeout(None)
        self._sock = sock
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self.get_state(timeout=10.0)

    def close(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _send(self, obj: dict) -> None:
        if self._sock is None:
            raise ConnectionError("Not connected")
        payload = json.dumps(obj).encode("utf-8")
        frame = struct.pack(">I", len(payload)) + payload
        with self._lock:
            self._sock.sendall(frame)

    def _read_loop(self) -> None:
        sock = self._sock
        while self._running and sock is not None:
            try:
                header = _recv_exactly(sock, 4)
                (length,) = struct.unpack(">I", header)
                if length > 16 * 1024 * 1024:
                    break
                payload = _recv_exactly(sock, length)
                self._handle_message(json.loads(payload.decode("utf-8")))
            except json.JSONDecodeError:
                continue
            except (ConnectionError, OSError):
                break
        # Disconnected: wake every waiter so it can raise.
        if self._sock is sock:
            self._sock = None
        self._state_event.set()
        for ev in list(self._result_events.values()):
            ev.set()

    def _handle_message(self, data: dict) -> None:
        msg_type = data.get("type", "")
        if msg_type == "state":
            self._latest_state = data
            self._state_event.set()
        elif msg_type == "command_result":
            result = data.get("result", {})
            cmd_id = result.get("cmdId", "default")
            self._command_results[cmd_id] = result
            if cmd_id in self._result_events:
                self._result_events[cmd_id].set()

    def get_state(self, timeout: float = 10.0) -> dict:
        if self._sock is None:
            raise ConnectionError("Not connected — server disconnected")
        self._state_event.clear()
        self._send({"type": "get_state"})
        if self._state_event.wait(timeout=timeout):
            if self._sock is None:
                raise ConnectionError("Disconnected while waiting for state")
            if self._latest_state is not None:
                return self._latest_state
        raise TimeoutError("Timed out waiting for state")

    def send_command(self, action: str, **params) -> dict:
        cmd_id = f"{action}_{next(_cmd_counter)}"
        cmd = {"type": "command", "cmdId": cmd_id, **params, "action": action}
        event = threading.Event()
        self._result_events[cmd_id] = event
        try:
            self._send(cmd)
            if not event.wait(timeout=self.timeout):
                raise TimeoutError(f"Timed out waiting for command result: {action}")
            if cmd_id not in self._command_results:
                raise ConnectionError("Disconnected while waiting for command result")
            return self._command_results.pop(cmd_id)
        finally:
            self._result_events.pop(cmd_id, None)

    def wait_for_turn(self, before: dict | None, timeout: float = TURN_TIMEOUT,
                      quiet: int = 1) -> tuple[dict, bool]:
        """Poll until game time advances, the log changes, or a popup opens.

        Returns (state, changed). Polls actively: while a popup blocks the
        game thread no turn broadcasts arrive, so waiting passively would
        just hit the timeout.
        """
        deadline = time.monotonic() + timeout
        state = before or {}
        while time.monotonic() < deadline:
            time.sleep(0.15)
            state = self._skip_notices(self.get_state())
            if state.get("popup"):
                return state, True
            if _progress(state) != _progress(before):
                return self._settle(state, deadline, quiet), True
        return state, False

    def _settle(self, state: dict, deadline: float, quiet: int = 1) -> dict:
        """A move can span several game updates (world-map travel advances time
        before the player changes cell; queued waits run one per update), so
        wait until `quiet` consecutive polls agree."""
        same = 0
        while time.monotonic() < deadline:
            time.sleep(0.15)
            nxt = self._skip_notices(self.get_state())
            if nxt.get("popup"):
                return nxt
            same = same + 1 if _progress(nxt) == _progress(state) else 0
            state = nxt
            if same >= quiet:
                break
        return state


    def _skip_notices(self, state: dict) -> dict:
        """Dismiss the low-HP warning popup (it re-opens on most hits below the
        threshold and only says what the HP line already shows) and keep its
        text for the next result."""
        for _ in range(3):
            popup = state.get("popup") or {}
            msg = _clean(popup.get("message") or "").strip()
            if not _is_hp_notice(popup, msg):
                break
            if "error" in self.send_command("respond_popup", dismiss=True):
                break
            if msg not in self.warnings:
                self.warnings.append(msg)
            time.sleep(0.1)
            state = self.get_state()
        return state


def _is_hp_notice(popup: dict, msg: str) -> bool:
    # Not the travel variant ("... Do you want to stop travelling?"), which asks.
    return ("health has dropped below" in msg.lower() and not popup.get("options")
            and "?" not in msg)


def _progress(state: dict | None) -> tuple:
    """Everything that changes when a turn resolves."""
    state = state or {}
    p = state.get("player") or {}
    return (_segment(state), state.get("msgCount"), p.get("x"), p.get("y"),
            (state.get("zone") or {}).get("id"), p.get("hp"))


def _segment(state: dict | None) -> int | None:
    if not state:
        return None
    return (state.get("time") or {}).get("segment")


# ── Global bridge instance ─────────────────────────────────────────────

_bridge: GameBridge | None = None


def get_bridge() -> GameBridge:
    global _bridge
    if _bridge is None:
        _bridge = GameBridge()
    if _bridge._sock is None:
        _bridge.connect()
    return _bridge


# ── Formatting ─────────────────────────────────────────────────────────

_MARKUP_RE = re.compile(r"\{\{[^|{}]*\||\}\}|&[a-zA-Z]|\^[a-zA-Z]")


def _clean(text: Any) -> str:
    return _MARKUP_RE.sub("", str(text))


def _fmt_popup(popup: dict) -> str:
    lines = ["!!! POPUP OPEN — the game is paused until you answer it with respond_popup !!!"]
    if popup.get("title"):
        lines.append(f"Title: {popup['title']}")
    if popup.get("message"):
        lines.append(popup["message"].strip())
    options = popup.get("options") or []
    if options:
        lines.append("Options (respond_popup option=N):")
        for o in options:
            text = re.sub(rf"^\[({o['n']}|[a-z])\]\s*", "", " ".join(o["text"].split()))
            lines.append(f"  {o['n']}. {text}")
    buttons = popup.get("buttons") or []
    if buttons:
        def label(b: dict) -> str:
            text = b.get("text") or ""
            return b["command"] if not text or text.lower().startswith("press ") else text
        labels = ", ".join(f"{label(b)} [{b['command']}]" for b in buttons)
        lines.append(f"Buttons (respond_popup button=...): {labels}")
    if not options and not buttons:
        lines.append("(any-key popup — respond_popup dismiss=true)")
    if popup.get("hasInput"):
        lines.append(f"Text input (respond_popup text=...): current value {popup.get('input', '')!r}")
    return "\n".join(lines)


def _is_stairs(c: dict) -> bool:
    return "stair" in c.get("name", "").lower()


_seen_msgs: list[str] = []


def _new_messages(msgs: list[str]) -> list[str]:
    """Messages not shown by the previous state report (the log is a sliding window)."""
    global _seen_msgs
    seen, _seen_msgs = _seen_msgs, list(msgs)
    for i in range(min(len(seen), len(msgs)), 0, -1):
        if msgs[:i] == seen[-i:]:
            return msgs[i:]
    return msgs


def _fmt_compact(state: dict) -> str:
    """Short state for action results: vitals, threats, new messages. get_state has the rest."""
    lines = []
    popup = state.get("popup")
    if popup:
        lines += [_fmt_popup(popup), ""]
    if "player" not in state:
        lines.append(f"Screen: {state.get('screen', '?')}  View stack: {state.get('viewStack', '')}")
        return _clean("\n".join(lines))
    p = state["player"]
    if _bridge is not None and _bridge.warnings:
        lines += [f"WARNING: {w}" for w in _bridge.warnings]
        _bridge.warnings.clear()
    lines.append(f"HP {p.get('hp', '?')}/{p.get('hpMax', '?')}  Lvl {p.get('level', '?')} "
                 f"XP {p.get('xp', '?')}/{p.get('xpNext', '?')}  at ({p.get('x', '?')},{p.get('y', '?')}) "
                 f"in {state.get('zone', {}).get('name', '?')}  {p.get('hunger', '?')}/{p.get('thirst', '?')}"
                 + ("  DEAD" if state.get("isDead") else ""))
    effects = state.get("effects", [])
    if effects:
        lines.append("Effects: " + ", ".join(e.get("name", "?") for e in effects[:10]))
    cells = sorted(state.get("cells", []), key=lambda c: c.get("distance", 999))
    hostiles = [c for c in cells if c.get("isCreature") and c.get("isHostile")]
    if hostiles:
        lines.append("Hostiles: " + "; ".join(
            f"{_clean(c.get('name') or c.get('blueprint', '?')).strip()} ({c['x']},{c['y']}) d={c.get('distance')} "
            f"HP={c.get('hp', '?')}/{c.get('hpMax', '?')}" for c in hostiles[:6]))
    adjacent = [c for c in cells if c.get("isCreature") and not c.get("isHostile") and c.get("distance") == 1]
    if adjacent:
        lines.append("Adjacent: " + "; ".join(
            f"{_clean(c.get('name') or '?').strip()} ({c['x']},{c['y']})" for c in adjacent))
    msgs = [_clean(m)[:200] for m in state.get("messages", []) if not isinstance(m, dict)]
    new = _new_messages(msgs)
    if new:
        lines.append("New messages:")
        recent: list[list] = []
        for m in new[-15:]:
            if recent and recent[-1][0] == m:
                recent[-1][1] += 1
            else:
                recent.append([m, 1])
        lines += [f"  {m}" + (f" (x{n})" if n > 1 else "") for m, n in recent]
    return _clean("\n".join(lines))


def _fmt_state(state: dict, full: bool = False) -> str:
    """Format game state as readable text for the LLM (compact unless full)."""
    if not full:
        return _fmt_compact(state)
    lines = []
    popup = state.get("popup")
    if popup:
        lines.append(_fmt_popup(popup))
        lines.append("")

    if "player" not in state:
        lines.append(f"Screen: {state.get('screen', '?')}  In chargen: {state.get('inChargen')}  "
                     f"Main menu: {state.get('inMainMenu')}  View stack: {state.get('viewStack', '')}")
        return _clean("\n".join(lines))

    p = state.get("player", {})
    z = state.get("zone", {})
    t = state.get("time", {})

    lines.append(f"=== {p.get('name', '?')} — Level {p.get('level', '?')} ===")
    lines.append(f"HP: {p.get('hp', '?')}/{p.get('hpMax', '?')}  "
                 f"XP: {p.get('xp', '?')}/{p.get('xpNext', '?')}")
    lines.append(f"STR {p.get('strength', '?')} AGI {p.get('agility', '?')} "
                 f"TOU {p.get('toughness', '?')} WIL {p.get('willpower', '?')} "
                 f"EGO {p.get('ego', '?')} INT {p.get('intelligence', '?')}")
    lines.append(f"AV {p.get('av', '?')} DV {p.get('dv', '?')} MA {p.get('ma', '?')}")
    lines.append(f"Hunger: {p.get('hunger', '?')}  Thirst: {p.get('thirst', '?')}")
    lines.append(f"Position: ({p.get('x', '?')}, {p.get('y', '?')})  "
                 f"Location: {p.get('location', '?')}  "
                 f"Zone: {z.get('name', '?')}")
    lines.append(f"In Combat: {p.get('inCombat', False)}  "
                 f"Screen: {state.get('screen', '?')}  "
                 f"Dead: {state.get('isDead', False)}")
    lines.append(f"Time: {'Day' if t.get('isDay') else 'Night'}, turn segment {t.get('segment', '?')}")

    effects = state.get("effects", [])
    if effects:
        lines.append(f"\nEffects: {', '.join(e.get('name', '?') for e in effects[:10])}")

    abilities = state.get("abilities", [])
    if abilities:
        lines.append(f"\nAbilities: {', '.join(a.get('name', '?') for a in abilities[:15])}")

    inv = state.get("inventory", [])
    if inv:
        lines.append(f"\n=== Inventory ({len(inv)}) ===")
        for item in inv[:30]:
            eq = " [equipped]" if item.get("equipped") else ""
            slot = item.get("slot", "")
            lines.append(f"  {item.get('name', '?')} ({slot}){eq}")

    cells = state.get("cells", [])
    if cells:
        nearby = sorted(cells, key=lambda c: c.get("distance", 999))
        creatures = [c for c in nearby if c.get("isCreature")]
        stairs = [c for c in nearby if _is_stairs(c)]
        items = [c for c in nearby if c.get("isItem") and not c.get("isContainer")]
        containers = [c for c in nearby if c.get("isContainer")]
        doors = [c for c in nearby if c.get("isDoor")]

        def row(c: dict) -> str:
            tags = []
            if c.get("isHostile"): tags.append("HOSTILE")
            elif c.get("isFriendly"): tags.append("friendly")
            elif c.get("isNeutral"): tags.append("neutral")
            hp = f" HP={c.get('hp', '?')}/{c.get('hpMax', '?')}" if c.get("isCreature") else ""
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            name = _clean(c.get("name") or "").strip() or c.get("blueprint", "?")
            return f"  ({c.get('x', '?')},{c.get('y', '?')}) d={c.get('distance', '?')} {name}{hp}{tag_str}"

        lines.append("\n=== Nearby (coordinates are x,y in this zone; go_to(x, y) walks there) ===")
        for title, group, limit in (("Creatures", creatures, 15), ("Stairs", stairs, 5),
                                    ("Items", items, 10), ("Doors", doors, 6),
                                    ("Containers", containers, 6)):
            if group:
                more = f" (nearest {limit} of {len(group)})" if len(group) > limit else ""
                lines.append(f"{title}{more}:")
                lines.extend(row(c) for c in group[:limit])

    msgs = [m for m in state.get("messages", []) if not isinstance(m, dict)]
    _new_messages([_clean(m)[:200] for m in msgs])
    if msgs:
        lines.append(f"\n=== Messages ({len(msgs)}) ===")
        recent: list[list] = []
        for m in msgs[-25:]:
            m = _clean(m)[:150]
            if recent and recent[-1][0] == m:
                recent[-1][1] += 1
            else:
                recent.append([m, 1])
        for m, n in recent[-12:]:
            lines.append(f"  {m}" + (f" (x{n})" if n > 1 else ""))

    return _clean("\n".join(lines))


def _act(action: str, label: str, takes_turn: bool = False, quiet: int = 1,
         timeout: float = TURN_TIMEOUT, **params) -> str:
    """Send a command, report errors, optionally wait for the turn, return state."""
    bridge = get_bridge()
    before = bridge.get_state() if takes_turn else None
    result = bridge.send_command(action, **params)
    if "error" in result:
        # Mod errors that concern a popup carry it; show it so the model can react.
        state = bridge.get_state()
        return f"FAILED {action}: {result['error']}\n\n{_fmt_state(state)}"
    if takes_turn:
        state, changed = bridge.wait_for_turn(before, timeout=timeout, quiet=quiet)
        note = "" if changed else " (no turn change detected)"
        return f"{label}{note}.\n{_fmt_state(state)}"
    time.sleep(0.2)  # let UI actions (screens, popups) settle
    state = bridge.get_state()
    return f"{label}.\n{_fmt_state(state)}"


# ── MCP Server ─────────────────────────────────────────────────────────

server = MCPServer(
    name="caves-of-qud",
    version="1.1.0",
    description="Play Caves of Qud — get game state and send commands. "
                "If the state shows a POPUP, answer it with respond_popup before doing anything else. "
                "Action results show a short status (HP, hostiles, new messages); "
                "call get_state for inventory and everything nearby.",
)

_DIRECTIONS = ("north/n/up, south/s/down, east/e/right, west/w/left, "
               "northeast/ne/up_right, northwest/nw/up_left, southeast/se/down_right, southwest/sw/down_left")


@server.tool(description="Get the current game state: any open popup/dialog, player stats, HP, position, inventory, nearby creatures/items, messages.")
def get_state() -> str:
    return _fmt_state(get_bridge().get_state(), full=True)


@server.tool(description="Get the raw game state as JSON. Useful for detailed programmatic access to all fields.")
def get_state_raw() -> str:
    return json.dumps(get_bridge().get_state(), default=str)


@server.tool(description=f"Move the player one tile. Valid directions: {_DIRECTIONS}. Moving into a creature attacks it.")
def _on_world_map(state: dict) -> bool:
    return str((state.get("zone") or {}).get("id", "")).endswith("World")


def move(direction: str) -> str:
    # A world-map step passes hours of game time, several seconds in real time.
    world = _on_world_map(get_bridge().get_state())
    return _act("move", f"Moved {direction}", takes_turn=True, quiet=3 if world else 2,
                timeout=30.0 if world else TURN_TIMEOUT, direction=direction)


_STEP_DIRS = {(0, -1): "north", (0, 1): "south", (1, 0): "east", (-1, 0): "west",
              (1, -1): "northeast", (-1, -1): "northwest", (1, 1): "southeast", (-1, 1): "southwest"}


def _blocked(state: dict, extra: set) -> set:
    """Cells the player can't step into. Closed doors are passable (bumping opens
    them); creatures are handled step by step in go_to."""
    out = set(extra)
    for c in state.get("cells", []):
        if c.get("blocksMovement") and not c.get("isDoor") and not c.get("isCreature"):
            out.add((c["x"], c["y"]))
    return out


def _explored(state: dict, x: int, y: int) -> bool:
    rows = (state.get("zone") or {}).get("explored")
    if not rows or not (0 <= y < len(rows)) or not (0 <= x < len(rows[y])):
        return True  # older mod or world map: no info
    return rows[y][x] == "1"


def _find_path(state: dict, goal: tuple[int, int], extra_blocked: set,
               avoid: set = frozenset(), avoid_cost: int = 40) -> list[tuple[int, int]] | None:
    """8-way shortest path from the player to goal (or next to it, if goal itself
    is blocked). Cells in `avoid` (hostiles) are passable but expensive, so the
    route only goes through one when there is no way around."""
    zone = state.get("zone") or {}
    w, h = zone.get("width", 80), zone.get("height", 25)
    p = state["player"]
    start = (p["x"], p["y"])
    blocked = _blocked(state, extra_blocked) - {start}
    goal_ok = goal not in blocked
    prev = {start: None}
    dist = {start: 0}
    heap = [(0, start)]
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist[cur]:
            continue
        if cur == goal or (not goal_ok and max(abs(cur[0] - goal[0]), abs(cur[1] - goal[1])) == 1):
            path = []
            while cur != start:
                path.append(cur)
                cur = prev[cur]
            return path[::-1]
        for dx, dy in _STEP_DIRS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if not (0 <= nxt[0] < w and 0 <= nxt[1] < h) or nxt in blocked:
                continue
            nd = (d + 1 + (avoid_cost if nxt in avoid and nxt != goal else 0)
                  + (2 if not _explored(state, *nxt) else 0))
            if nd < dist.get(nxt, 1 << 30):
                dist[nxt] = nd
                prev[nxt] = cur
                heapq.heappush(heap, (nd, nxt))
    return None


@server.tool(description="Walk to cell (x, y) of the current zone along a shortest path (around walls; "
                         "if the target is occupied, stops next to it without attacking). Stops early if a popup opens, "
                         "a newly seen hostile comes within 5 tiles, a hostile gets adjacent, or you take damage. "
                         "Then use move (to attack), go_stairs, interact, etc.")
def go_to(x: int, y: int, max_steps: int = 120) -> str:
    bridge = get_bridge()
    goal = (x, y)
    state = bridge.get_state()
    if state.get("popup"):
        return "A popup is open — answer it first.\n\n" + _fmt_state(state)
    if "player" not in state:
        return "Not in game.\n\n" + _fmt_state(state)
    start_hp = state["player"].get("hp")
    # Hostiles already known when the walk starts don't stop it (walking up to a
    # known enemy is the point); new arrivals near you, or anything that gets
    # adjacent, do. No creature IDs in the snapshot, so count by name.
    known = Counter(_clean(c.get("name", "")) for c in state.get("cells", []) if c.get("isHostile"))
    extra: set = set()
    steps, stuck = 0, 0
    reason = "step limit reached"
    while steps < max_steps:
        p = state["player"]
        here = (p["x"], p["y"])
        hostile_cells = {(c["x"], c["y"]) for c in state.get("cells", []) if c.get("isHostile")}
        path = _find_path(state, goal, extra, avoid=hostile_cells)
        if path is None:
            reason = "no known path"
            break
        if not path:
            reason = "arrived"
            break
        nxt = path[0]
        occupant = next((c for c in state.get("cells", []) if c.get("isCreature")
                         and (c["x"], c["y"]) == nxt), None)
        if occupant is not None and nxt == goal:
            reason = f"arrived next to {_clean(occupant['name'])}"
            break
        if occupant is not None:
            if occupant.get("isHostile"):
                reason = f"hostile {_clean(occupant['name'])} in the way at ({nxt[0]},{nxt[1]})"
                break
            extra.add(nxt)  # don't shove neutrals around; route past them
            continue
        direction = _STEP_DIRS[(nxt[0] - here[0], nxt[1] - here[1])]
        res = bridge.send_command("move", direction=direction)
        if "error" in res:
            reason = f"move failed: {res['error']}"
            break
        state, _ = bridge.wait_for_turn(state)
        steps += 1
        p = state.get("player") or {}
        if state.get("popup"):
            reason = "a popup opened"
            break
        if (p.get("x"), p.get("y")) == here:
            # Bumped something the map didn't show as blocking (or opened a door): retry, then route around.
            stuck += 1
            if stuck >= 2:
                extra.add(nxt)
                stuck = 0
            continue
        stuck = 0
        if start_hp is not None and p.get("hp", start_hp) < start_hp:
            reason = f"took damage (HP {p.get('hp')}/{p.get('hpMax')})"
            break
        now = [c for c in state.get("cells", []) if c.get("isHostile")]
        counts = Counter(_clean(c.get("name", "")) for c in now)
        hostiles = [c for c in now if c.get("distance", 99) <= 1 and (c["x"], c["y"]) != goal]
        hostiles += [c for c in now if c.get("distance", 99) <= 5
                     and counts[_clean(c.get("name", ""))] > known[_clean(c.get("name", ""))]]
        known |= counts
        if hostiles:
            reason = "hostile nearby: " + ", ".join(f"{_clean(c['name'])} at ({c['x']},{c['y']})" for c in hostiles[:3])
            break
    p = state.get("player") or {}
    if start_hp is not None and p.get("hp", start_hp) < start_hp:
        reason += f"; HP {start_hp} -> {p.get('hp')}/{p.get('hpMax')}"
    return (f"go_to({x},{y}): {reason} after {steps} steps, now at ({p.get('x')},{p.get('y')}).\n\n"
            + _fmt_state(state))


def _map_char(cs: list[dict]) -> str:
    if any(c.get("isCreature") for c in cs):
        return "H" if any(c.get("isHostile") for c in cs) else "c"
    for c in cs:
        if _is_stairs(c):
            return "<" if "up" in c.get("name", "").lower() else ">"
    if any(c.get("isDoor") for c in cs): return "+"
    if any(c.get("isContainer") for c in cs): return "="
    if any(c.get("isItem") for c in cs): return "*"
    if any(c.get("blocksMovement") for c in cs): return "#"
    return "."


@server.tool(description="ASCII map of the current zone for route planning. Legend: @ you, H hostile, c other creature, "
                         "> stairs down, < stairs up, + door, = container, * item, # impassable, . terrain feature, "
                         "space = open ground, ? unexplored. Only creatures you can see are shown. "
                         "Row/column numbers are the x,y used by go_to.")
def get_map() -> str:
    state = get_bridge().get_state()
    if "player" not in state:
        return "Not in game."
    zone = state.get("zone") or {}
    w, h = zone.get("width", 80), zone.get("height", 25)
    grid: dict[tuple[int, int], list[dict]] = {}
    for c in state.get("cells", []):
        grid.setdefault((c["x"], c["y"]), []).append(c)
    p = state["player"]
    lines = [f"Zone: {_clean(zone.get('name', '?'))}  You: ({p['x']},{p['y']})",
             "    " + "".join(str(x // 10) for x in range(w)),
             "    " + "".join(str(x % 10) for x in range(w))]
    for y in range(h):
        row = "".join("@" if (x, y) == (p["x"], p["y"]) else
                      _map_char(grid[(x, y)]) if (x, y) in grid else
                      " " if _explored(state, x, y) else "?" for x in range(w))
        lines.append(f"{y:3d} {row}")
    return "\n".join(lines)


@server.tool(description="Wait for N turns (default 1). Passes time without moving.")
def wait(turns: int = 1) -> str:
    return _act("wait", f"Waited {turns} turn(s)", takes_turn=True, quiet=4,
                timeout=TURN_TIMEOUT + 0.2 * turns, turns=turns)


@server.tool(description="Rest until healed (the game's 'wait until healed'). Stops early if a hostile "
                         "appears or something happens. Do this after every fight.")
def rest() -> str:
    before = get_bridge().get_state()
    hp = (before.get("player") or {}).get("hp")
    out = _act("press_command", "Rested", takes_turn=True, quiet=6, timeout=90.0,
               command="CmdWaitUntilHealed")
    return out.replace("Rested.", f"Rested (HP was {hp}).", 1)


@server.tool(description=f"Interact with something adjacent (talk to NPC, open door/container). Direction is optional — omit to interact with your own tile. Valid directions: {_DIRECTIONS}. Talking opens a conversation popup; answer it with respond_popup.")
def interact(direction: str = "") -> str:
    return _act("interact", f"Interacted {direction or '(here)'}", takes_turn=True, direction=direction)


@server.tool(description="Pick up items on the current tile.")
def get() -> str:
    return _act("get", "Get", takes_turn=True)


@server.tool(description="Use an item from inventory. item_action: eat, drink/quaff, equip/wear/wield, apply, drop, unequip. item is the item name (partial match OK).")
def use_item(item: str, item_action: str = "eat") -> str:
    return _act("use_item", f"Used {item} ({item_action})", takes_turn=True, item=item, item_action=item_action)


@server.tool(description=(
    "Answer the open popup/dialog/conversation. Give exactly one of: "
    "option=N (1-based number from the popup's Options list), "
    "button='Yes'/'No'/'Cancel'/'Continue'/... (a button from the popup's Buttons list), "
    "or dismiss=true (Cancel/Continue/any-key). "
    "For text or number prompts pass text='...' (it is typed in and submitted)."))
def respond_popup(option: int = 0, button: str = "", dismiss: bool = False, text: str | None = None) -> str:
    params: dict[str, Any] = {"option": option, "button": button, "dismiss": dismiss}
    if text is not None:
        params["text"] = text
    what = (f"option {option}" if option else f"button {button!r}" if button
            else f"text {text!r}" if text is not None else "dismiss")
    out = _act("respond_popup", f"Answered popup with {what}", **params)
    if out.startswith("FAILED") or "POPUP OPEN" in out:
        return out
    # Popups often come in chains (quest step -> XP -> level up) and the next
    # one opens a moment later; show it rather than an idle state.
    bridge = get_bridge()
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        time.sleep(0.15)
        state = bridge.get_state()
        if state.get("popup"):
            return f"Answered popup with {what}; another popup opened.\n{_fmt_state(state)}"
    return out


@server.tool(description="Choose a numbered option in the open popup or conversation (1-based). Same as respond_popup(option=N).")
def choose_option(option: int) -> str:
    return _act("choose_option", f"Chose option {option}", option=option)


@server.tool(description="Press a button on the open popup by name, default 'Yes'. Same as respond_popup(button=...).")
def confirm_popup(button: str = "Yes") -> str:
    return _act("confirm_popup", f"Pressed popup button {button!r}", command=button)


@server.tool(description="Open a game screen. Valid screens: inventory, equipment, character, abilities, skills, quests, journal, factions, effects, messages, help, options.")
def open_screen(screen: str) -> str:
    return _act("open_screen", f"Opened screen {screen}", screen=screen)


@server.tool(description="Close the open popup (Cancel/Continue) or menu/screen.")
def close_menu() -> str:
    return _act("close_menu", "Closed menu")


@server.tool(description="Enter look mode to examine things.")
def look() -> str:
    return _act("look", "Look mode")


@server.tool(description="Auto-explore: wander automatically to discover new tiles. Stops when something interesting happens.")
def auto_explore() -> str:
    bridge = get_bridge()
    before = bridge.get_state()
    result = bridge.send_command("auto_explore")
    if "error" in result:
        return f"FAILED auto_explore: {result['error']}\n\n{_fmt_state(bridge.get_state())}"
    # Keep waiting while the explore run is still advancing time.
    state, changed = bridge.wait_for_turn(before, timeout=5.0)
    deadline = time.monotonic() + 30.0
    while changed and not state.get("popup") and time.monotonic() < deadline:
        state, changed = bridge.wait_for_turn(state, timeout=1.0)
    return f"Auto-explored.\n{_fmt_state(state)}"


@server.tool(description="Travel far in a cardinal direction (north/south/east/west) until something interesting happens.")
def travel(direction: str) -> str:
    return _act("travel", f"Travel {direction}", takes_turn=True, quiet=4, direction=direction)


@server.tool(description="Go up or down stairs. direction: 'up' or 'down'.")
def go_stairs(direction: str) -> str:
    return _act("go_stairs", f"Went {direction} stairs", takes_turn=True, quiet=4,
                timeout=30.0, direction=direction)


@server.tool(description="Save the game. Creates a quicksave.")
def save_game() -> str:
    return json.dumps(get_bridge().send_command("save_game"), default=str)


@server.tool(description="Quit to the main menu. Usually opens a confirmation popup — answer it with respond_popup.")
def quit_to_menu() -> str:
    return _act("quit_to_menu", "Quit requested")


@server.tool(description="Start a new game from the main menu.")
def start_new_game() -> str:
    return json.dumps(get_bridge().send_command("start_new_game"), default=str)


@server.tool(description="Load a save from the main menu (default: the most recent one; save_id comes from list_saves). Waits for the game to finish loading.")
def continue_game(save_id: str = "") -> str:
    bridge = get_bridge()
    for _ in range(4):  # right after launch the main menu may not take input yet
        res = bridge.send_command("continue_game", save_id=save_id)
        if res.get("ok") or "did not open" not in str(res.get("error", "")):
            break
        time.sleep(3)
    if not res.get("ok"):
        return "continue_game failed: " + json.dumps(res, default=str)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            state = bridge.get_state()
        except Exception:
            continue
        if (state.get("inGame") and state.get("screen") == "Stage") or state.get("popup"):
            return "Game loaded.\n\n" + _fmt_state(state, full=True)
    return "Load requested, but the game was not in play after 120s.\n\n" + _fmt_state(bridge.get_state())


@server.tool(description="Auto-complete character creation with random choices. Selects Classic mode and Random character.")
def chargen_auto() -> str:
    bridge = get_bridge()
    for _ in range(20):  # start_new_game returns before the character builder exists
        res = bridge.send_command("chargen_auto")
        if "EmbarkBuilder not found" not in str(res.get("error", "")):
            break
        time.sleep(0.5)
    return json.dumps(res, default=str)


@server.tool(description="List available saves.")
def list_saves() -> str:
    return json.dumps(get_bridge().send_command("list_saves"), default=str)


@server.tool(description="List skills and powers you own or can buy now with skill points (SP), plus "
                         "unspent SP and attribute points (AP). all=true also lists ones you can't buy yet.")
def list_skills(all: bool = False) -> str:
    r = get_bridge().send_command("list_skills", all=all)
    if "error" in r:
        return f"FAILED list_skills: {r['error']}"
    lines = [f"Skill points: {r.get('sp')}  Attribute points: {r.get('ap')}"]
    for s in r.get("skills", []):
        tag = "OWNED" if s.get("owned") else ("can learn" if s.get("canLearn") else s.get("why", ""))
        lines.append(f"{s['name']} ({s['cost']} SP) [{tag}]")
        for p in s.get("powers", []):
            ptag = "OWNED" if p.get("owned") else ("can learn" if p.get("canLearn") else p.get("why", ""))
            lines.append(f"    {p['name']} ({p['cost']} SP) [{ptag}]")
    return "\n".join(lines)


@server.tool(description="With the trade screen open (talk to a merchant -> Trade): list the trader's goods "
                         "(side 0) and yours (side 1) with index, count, price each in drams, and how many are "
                         "selected; plus both water (dram) balances. Water is the currency.")
def trade_list() -> str:
    r = get_bridge().send_command("trade_list")
    if "error" in r:
        return f"FAILED trade_list: {r['error']}"
    lines = [f"Trading with {r.get('trader')}. Your drams: {r.get('playerDrams')}  "
             f"Trader's drams: {r.get('traderDrams')}",
             f"Selected: {r.get('balance')}"]
    for side, title in ((0, "Trader's goods (side 0, you buy)"), (1, "Your goods (side 1, you sell)")):
        lines.append(f"{title}:")
        for e in r.get("sides", [[], []])[side]:
            sel = f"  [selected {e['selected']}]" if e.get("selected") else ""
            lines.append(f"  {e['index']}. {e['name']} (x{e['count']}) - {e['price']} drams each{sel}")
    return "\n".join(lines)


@server.tool(description="On the trade screen, set how many of an entry to trade: side 0 = buy from trader, "
                         "side 1 = sell yours; index from trade_list; count=-1 for the whole stack, 0 to unselect. "
                         "Then trade_offer.")
def trade_select(side: int, index: int, count: int = 1) -> str:
    r = get_bridge().send_command("trade_select", side=side, index=index, count=count)
    if "error" in r:
        return f"FAILED trade_select: {r['error']}"
    return f"Selected {r.get('selected')} x {r.get('item')}. {r.get('balance')}"


@server.tool(description="Offer the selected trade (the trade screen's Offer button). The game asks to confirm "
                         "any dram difference in a popup; answer it with respond_popup.")
def trade_offer() -> str:
    bridge = get_bridge()
    r = bridge.send_command("trade_offer")
    if "error" in r:
        return f"FAILED trade_offer: {r['error']}"
    deadline = time.monotonic() + 2.0
    state = bridge.get_state()
    while not state.get("popup") and time.monotonic() < deadline:
        time.sleep(0.15)
        state = bridge.get_state()
    return "Offered the trade.\n" + _fmt_state(state)


_ATTACK_DIRS = {"n": "N", "north": "N", "up": "N", "s": "S", "south": "S", "down": "S",
                "e": "E", "east": "E", "right": "E", "w": "W", "west": "W", "left": "W",
                "ne": "NE", "northeast": "NE", "up_right": "NE", "nw": "NW", "northwest": "NW", "up_left": "NW",
                "se": "SE", "southeast": "SE", "down_right": "SE", "sw": "SW", "southwest": "SW",
                "down_left": "SW"}


@server.tool(description=f"Melee-attack in a direction even if nothing would block a move there — needed for "
                         f"creatures you can walk over (e.g. hostile plants like dreadroots). Directions: {_DIRECTIONS}.")
def attack(direction: str) -> str:
    d = _ATTACK_DIRS.get(direction.strip().lower())
    if d is None:
        return f"FAILED attack: invalid direction {direction!r}"
    return _act("press_command", f"Attacked {direction}", takes_turn=True, quiet=2, command=f"CmdAttack{d}")


@server.tool(description="Use an activated ability by name (the Abilities line of get_state), e.g. Sprint "
                         "(run, also to flee), Flurry (attack every adjacent enemy). Abilities that need a "
                         "target or direction may open a prompt.")
def use_ability(name: str) -> str:
    bridge = get_bridge()
    abilities = bridge.get_state().get("abilities") or []
    wanted = name.strip().lower()
    match = (next((a for a in abilities if a.get("name", "").lower() == wanted), None)
             or next((a for a in abilities if wanted in a.get("name", "").lower()), None))
    if match is None:
        return (f"FAILED use_ability: no ability named {name!r}. You have: "
                + ", ".join(a.get("name", "?") for a in abilities))
    return _act("press_command", f"Used {match['name']}", takes_turn=True, quiet=2,
                command=match["command"])


@server.tool(description="Fire your missile weapon (bow, gun) at cell (x, y) — default: the nearest "
                         "hostile — reloading first if needed. Shoot enemies while they approach.")
def fire(x: int = -1, y: int = -1) -> str:
    bridge = get_bridge()
    before = bridge.get_state()
    if before.get("popup"):
        return "A popup is open — answer it first.\n\n" + _fmt_state(before)
    auto = x < 0 or y < 0
    state = before
    for attempt in range(2):
        if auto:  # (re)aim at the nearest hostile — it may have moved while we reloaded
            hostiles = sorted((c for c in state.get("cells", []) if c.get("isHostile")),
                              key=lambda c: c.get("distance", 999))
            if not hostiles:
                return "No hostile to fire at.\n" + _fmt_state(state)
            x, y = hostiles[0]["x"], hostiles[0]["y"]
        r = bridge.send_command("fire_at", x=x, y=y)
        if "error" in r:
            return f"FAILED fire: {r['error']}\n\n" + _fmt_state(bridge.get_state())
        prev = state
        state, _ = bridge.wait_for_turn(state, quiet=2)
        popup = state.get("popup") or {}
        new = " ".join(m for m in state.get("messages", [])[len(prev.get("messages", [])) - 3:]
                       if isinstance(m, str)).lower()
        needs_reload = "reload" in (popup.get("message") or "").lower() or "no more ammo" in new
        if attempt == 0 and needs_reload:
            if popup:
                bridge.send_command("respond_popup", dismiss=True)
            state = bridge.get_state()
            bridge.send_command("press_command", command="CmdReload")
            state, _ = bridge.wait_for_turn(state, quiet=2)
            continue
        break
    new = " ".join(m for m in state.get("messages", [])[-4:] if isinstance(m, str)).lower()
    if "no more ammo" in new or "out of ammo" in new:
        return "Out of ammo — nothing to reload with. Fight in melee or find/buy ammo.\n" + _fmt_state(state)
    target = r.get("target") or "nothing there"
    return f"Fired at ({x},{y}) [{target}].\n" + _fmt_state(state)


@server.tool(description="Buy a skill or power by name with skill points (see list_skills).")
def learn_skill(name: str) -> str:
    r = get_bridge().send_command("learn_skill", name=name)
    if "error" in r:
        return f"FAILED learn_skill: {r['error']}"
    return f"Learned {r.get('learned')} for {r.get('cost')} SP ({r.get('spLeft')} SP left)."


@server.tool(description="Spend one attribute point (AP, gained on some level-ups) on Strength, Agility, "
                         "Toughness, Intelligence, Willpower or Ego.")
def raise_attribute(attribute: str) -> str:
    r = get_bridge().send_command("raise_attribute", attribute=attribute)
    if "error" in r:
        return f"FAILED raise_attribute: {r['error']}"
    return f"{r.get('attribute')} is now {r.get('value')} ({r.get('apLeft')} AP left)."


@server.tool(description="Press a raw key by name (e.g. 'space', 'escape', 'enter', 'tab', a letter or digit). Last resort — prefer semantic tools; does not answer modern popups (use respond_popup).")
def press_key(key: str) -> str:
    return _act("press_key", f"Pressed {key}", key=key)


@server.tool(description="Bring the game window to the foreground. Normally unnecessary: the bridge works while the window is unfocused (but not minimized).")
def focus_window() -> str:
    return json.dumps(get_bridge().send_command("focus_window"), default=str)


@server.tool(description="Quit the game entirely.")
def quit_game() -> str:
    return json.dumps(get_bridge().send_command("quit"), default=str)


@server.tool(description="Abandon the current character (permadeath).")
def abandon() -> str:
    return json.dumps(get_bridge().send_command("abandon"), default=str)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
