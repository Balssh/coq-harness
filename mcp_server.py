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

    def wait_for_turn(self, before: dict | None, timeout: float = TURN_TIMEOUT) -> tuple[dict, bool]:
        """Poll until game time advances, the log changes, or a popup opens.

        Returns (state, changed). Polls actively: while a popup blocks the
        game thread no turn broadcasts arrive, so waiting passively would
        just hit the timeout.
        """
        deadline = time.monotonic() + timeout
        state = before or {}
        while time.monotonic() < deadline:
            time.sleep(0.15)
            state = self.get_state()
            if state.get("popup"):
                return state, True
            if _progress(state) != _progress(before):
                return self._settle(state, deadline), True
        return state, False

    def _settle(self, state: dict, deadline: float) -> dict:
        """A move can span several game updates (world-map travel advances time
        before the player changes cell), so wait until two polls agree."""
        while time.monotonic() < deadline:
            time.sleep(0.15)
            nxt = self.get_state()
            if nxt.get("popup") or _progress(nxt) == _progress(state):
                return nxt
            state = nxt
        return state


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
            text = re.sub(rf"^\[{o['n']}\]\s*", "", " ".join(o["text"].split()))
            lines.append(f"  {o['n']}. {text}")
    buttons = popup.get("buttons") or []
    if buttons:
        labels = ", ".join(f"{b['text'] or b['command']} [{b['command']}]" for b in buttons)
        lines.append(f"Buttons (respond_popup button=...): {labels}")
    if not options and not buttons:
        lines.append("(any-key popup — respond_popup dismiss=true)")
    if popup.get("hasInput"):
        lines.append(f"Text input (respond_popup text=...): current value {popup.get('input', '')!r}")
    return "\n".join(lines)


def _is_stairs(c: dict) -> bool:
    return "stair" in c.get("name", "").lower()


def _fmt_state(state: dict) -> str:
    """Format game state as readable text for the LLM."""
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


def _act(action: str, label: str, takes_turn: bool = False, **params) -> str:
    """Send a command, report errors, optionally wait for the turn, return state."""
    bridge = get_bridge()
    before = bridge.get_state() if takes_turn else None
    result = bridge.send_command(action, **params)
    if "error" in result:
        # Mod errors that concern a popup carry it; show it so the model can react.
        state = bridge.get_state()
        return f"FAILED {action}: {result['error']}\n\n{_fmt_state(state)}"
    if takes_turn:
        state, changed = bridge.wait_for_turn(before)
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
                "If the state shows a POPUP, answer it with respond_popup before doing anything else.",
)

_DIRECTIONS = ("north/n/up, south/s/down, east/e/right, west/w/left, "
               "northeast/ne/up_right, northwest/nw/up_left, southeast/se/down_right, southwest/sw/down_left")


@server.tool(description="Get the current game state: any open popup/dialog, player stats, HP, position, inventory, nearby creatures/items, messages.")
def get_state() -> str:
    return _fmt_state(get_bridge().get_state())


@server.tool(description="Get the raw game state as JSON. Useful for detailed programmatic access to all fields.")
def get_state_raw() -> str:
    return json.dumps(get_bridge().get_state(), default=str)


@server.tool(description=f"Move the player one tile. Valid directions: {_DIRECTIONS}. Moving into a creature attacks it.")
def move(direction: str) -> str:
    return _act("move", f"Moved {direction}", takes_turn=True, direction=direction)


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
            nd = d + 1 + (avoid_cost if nxt in avoid and nxt != goal else 0)
            if nd < dist.get(nxt, 1 << 30):
                dist[nxt] = nd
                prev[nxt] = cur
                heapq.heappush(heap, (nd, nxt))
    return None


@server.tool(description="Walk to cell (x, y) of the current zone along a shortest path (around walls; "
                         "if the target is occupied, stops next to it). Stops early if a popup opens, "
                         "a hostile comes within 5 tiles, or you take damage. Then use go_stairs/interact/etc.")
def go_to(x: int, y: int, max_steps: int = 120) -> str:
    bridge = get_bridge()
    goal = (x, y)
    state = bridge.get_state()
    if state.get("popup"):
        return "A popup is open — answer it first.\n\n" + _fmt_state(state)
    if "player" not in state:
        return "Not in game.\n\n" + _fmt_state(state)
    start_hp = state["player"].get("hp")
    seen_hostiles = {(c["x"], c["y"]) for c in state.get("cells", []) if c.get("isHostile") and c.get("distance", 99) <= 5}
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
        if occupant is not None and nxt != goal:
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
        hostiles = [c for c in state.get("cells", []) if c.get("isHostile") and c.get("distance", 99) <= 5
                    and (c["x"], c["y"]) not in seen_hostiles]
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
                         "space = open ground. Row/column numbers are the x,y used by go_to.")
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
                      (_map_char(grid[(x, y)]) if (x, y) in grid else " ") for x in range(w))
        lines.append(f"{y:3d} {row}")
    return "\n".join(lines)


@server.tool(description="Wait for N turns (default 1). Passes time without moving.")
def wait(turns: int = 1) -> str:
    return _act("wait", f"Waited {turns} turn(s)", takes_turn=True, turns=turns)


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
    return _act("respond_popup", f"Answered popup with {what}", **params)


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
    return _act("travel", f"Travel {direction}", takes_turn=True, direction=direction)


@server.tool(description="Go up or down stairs. direction: 'up' or 'down'.")
def go_stairs(direction: str) -> str:
    return _act("go_stairs", f"Went {direction} stairs", takes_turn=True, direction=direction)


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
    res = bridge.send_command("continue_game", save_id=save_id)
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
            return "Game loaded.\n\n" + _fmt_state(state)
    return "Load requested, but the game was not in play after 120s.\n\n" + _fmt_state(bridge.get_state())


@server.tool(description="Auto-complete character creation with random choices. Selects Classic mode and Random character.")
def chargen_auto() -> str:
    return json.dumps(get_bridge().send_command("chargen_auto"), default=str)


@server.tool(description="List available saves.")
def list_saves() -> str:
    return json.dumps(get_bridge().send_command("list_saves"), default=str)


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
