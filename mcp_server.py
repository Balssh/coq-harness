#!/usr/bin/env python3
"""MCP server bridge for Caves of Qud.

Launched by Vibe as a stdio MCP server. Connects to the in-game MCP bridge
over TCP (172.24.128.1:47321) and exposes game actions as MCP tools.

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

import asyncio
import itertools
import json
import socket
import struct
import threading
import time
from typing import Any

from mcp.server.mcpserver import MCPServer

# ── TCP client for the in-game bridge ──────────────────────────────────

_cmd_counter = itertools.count()


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

    def __init__(self, host: str = "172.24.128.1", port: int = 47321, timeout: float = 30.0):
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
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        # Wait for first state
        self._state_event.clear()
        self._send({"type": "get_state"})
        self._state_event.wait(timeout=10.0)

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
        while self._running and self._sock is not None:
            try:
                header = _recv_exactly(self._sock, 4)
                (length,) = struct.unpack(">I", header)
                if length > 16 * 1024 * 1024:
                    break
                payload = _recv_exactly(self._sock, length)
                data = json.loads(payload.decode("utf-8"))
                self._handle_message(data)
            except (ConnectionError, OSError, json.JSONDecodeError):
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
        if self._sock is None:
            self._result_events.pop(cmd_id, None)
            raise ConnectionError("Not connected — server disconnected")
        self._send(cmd)
        if event.wait(timeout=self.timeout):
            self._result_events.pop(cmd_id, None)
            if self._sock is None and cmd_id not in self._command_results:
                raise ConnectionError("Disconnected while waiting for command result")
            return self._command_results.pop(cmd_id, {})
        else:
            self._result_events.pop(cmd_id, None)
            raise TimeoutError(f"Timed out waiting for command result: {action}")

    def wait_for_turn(self, timeout: float = 30.0) -> dict:
        old = self._latest_state
        old_seg = old.get("time", {}).get("segment") if old else None
        old_msgs = old.get("msgCount", 0) if old else 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.1)
            cur = self._latest_state
            if cur is None:
                continue
            seg = cur.get("time", {}).get("segment")
            if seg is not None and old_seg is not None and seg > old_seg:
                return cur
            if cur.get("msgCount", 0) > old_msgs and cur is not old:
                return cur
        if self._latest_state is not None:
            return self._latest_state
        raise TimeoutError("Timed out waiting for turn")


# ── Global bridge instance ─────────────────────────────────────────────

_bridge: GameBridge | None = None


def get_bridge() -> GameBridge:
    global _bridge
    if _bridge is None:
        _bridge = GameBridge()
        _bridge.connect()
    elif _bridge._sock is None:
        _bridge.connect()
    return _bridge


# ── MCP Server ─────────────────────────────────────────────────────────

server = MCPServer(
    name="caves-of-qud",
    version="1.0.0",
    description="Play Caves of Qud — get game state and send commands",
)


def _fmt_state(state: dict) -> str:
    """Format game state as readable text for the LLM."""
    import re
    p = state.get("player", {})
    z = state.get("zone", {})
    t = state.get("time", {})

    lines = []
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
    lines.append(f"Time: Day {t.get('day', '?')} Hour {t.get('hour', '?')} "
                 f"({'Day' if t.get('isDay') else 'Night'}) Segment {t.get('segment', '?')}")

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
        items = [c for c in nearby if c.get("isItem") and not c.get("isContainer")]
        containers = [c for c in nearby if c.get("isContainer")]
        doors = [c for c in nearby if c.get("isDoor")]
        stairs = [c for c in nearby if "stair" in c.get("name", "").lower()]

        lines.append(f"\n=== Nearby ===")
        lines.append(f"Creatures: {len(creatures)}  Items: {len(items)}  "
                     f"Containers: {len(containers)}  Doors: {len(doors)}  Stairs: {len(stairs)}")
        for c in nearby[:40]:
            d = c.get("distance", "?")
            tags = []
            if c.get("isHostile"): tags.append("HOSTILE")
            elif c.get("isFriendly"): tags.append("friendly")
            elif c.get("isNeutral"): tags.append("neutral")
            if c.get("isItem"): tags.append("item")
            if c.get("isDoor"): tags.append("door")
            if c.get("isContainer"): tags.append("container")
            if c.get("blocksMovement"): tags.append("blocks")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            hp = f" HP={c.get('hp','?')}/{c.get('hpMax','?')}" if c.get("isCreature") else ""
            lines.append(f"  ({c.get('x','?')},{c.get('y','?')}) d={d} "
                        f"{c.get('name', '?')}{hp}{tag_str}")

    msgs = state.get("messages", [])
    if msgs:
        lines.append(f"\n=== Messages ({len(msgs)}) ===")
        for m in msgs[-15:]:
            clean = re.sub(r'&[a-zA-Z|]', '', str(m))
            clean = clean.replace('{{', '').replace('}}', '')
            lines.append(f"  {clean[:150]}")

    return "\n".join(lines)


@server.tool(description="Get the current game state: player stats, HP, position, inventory, nearby creatures/items, messages. Returns a formatted text summary.")
def get_state() -> str:
    bridge = get_bridge()
    state = bridge.get_state()
    return _fmt_state(state)


@server.tool(description="Get the raw game state as JSON. Useful for detailed programmatic access to all fields.")
def get_state_raw() -> str:
    bridge = get_bridge()
    state = bridge.get_state()
    return json.dumps(state, default=str)


@server.tool(description="Move the player in a direction. Valid directions: north/n/up, south/s/down, east/e/right, west/w/left, northeast/ne/up_right, northwest/nw/up_left, southeast/se/down_right, southwest/sw/down_left.")
def move(direction: str) -> str:
    bridge = get_bridge()
    result = bridge.send_command("move", direction=direction)
    # Wait for the turn to resolve
    try:
        state = bridge.wait_for_turn(timeout=5.0)
        return f"Moved {direction}.\n{_fmt_state(state)}"
    except TimeoutError:
        state = bridge.get_state()
        return f"Moved {direction} (no turn change detected).\n{_fmt_state(state)}"


@server.tool(description="Wait for N turns (default 1). Passes time without moving.")
def wait(turns: int = 1) -> str:
    bridge = get_bridge()
    result = bridge.send_command("wait", turns=turns)
    try:
        state = bridge.wait_for_turn(timeout=10.0)
        return f"Waited {turns} turn(s).\n{_fmt_state(state)}"
    except TimeoutError:
        state = bridge.get_state()
        return f"Waited (no turn change).\n{_fmt_state(state)}"


@server.tool(description="Interact with something in a direction (talk, open door, attack). Direction is optional — omit to interact with what's on the current tile. Valid directions: same as move.")
def interact(direction: str = "") -> str:
    bridge = get_bridge()
    result = bridge.send_command("interact", direction=direction)
    try:
        state = bridge.wait_for_turn(timeout=5.0)
        return f"Interacted {direction or '(here)'}.\n{_fmt_state(state)}"
    except TimeoutError:
        state = bridge.get_state()
        return f"Interacted {direction or '(here)'} (no turn change).\n{_fmt_state(state)}"


@server.tool(description="Pick up items on the current tile.")
def get() -> str:
    bridge = get_bridge()
    result = bridge.send_command("get")
    try:
        state = bridge.wait_for_turn(timeout=5.0)
        return f"Picked up items.\n{_fmt_state(state)}"
    except TimeoutError:
        state = bridge.get_state()
        return f"Get (no turn change).\n{_fmt_state(state)}"


@server.tool(description="Use an item from inventory. item_action: eat, drink/quaff, equip/wear/wield, apply, drop, unequip. item is the item name (partial match OK).")
def use_item(item: str, item_action: str = "eat") -> str:
    bridge = get_bridge()
    result = bridge.send_command("use_item", item=item, item_action=item_action)
    try:
        state = bridge.wait_for_turn(timeout=5.0)
        return f"Used {item} ({item_action}).\n{_fmt_state(state)}"
    except TimeoutError:
        state = bridge.get_state()
        return f"Used {item} ({item_action}) (no turn change).\n{_fmt_state(state)}"


@server.tool(description="Open a game screen. Valid screens: inventory, equipment, character, abilities, skills, mutations, reputation, journal, map, options, look, help.")
def open_screen(screen: str) -> str:
    bridge = get_bridge()
    result = bridge.send_command("open_screen", screen=screen)
    state = bridge.get_state()
    return f"Opened screen: {screen}. Current screen: {state.get('screen', '?')}\n{_fmt_state(state)}"


@server.tool(description="Close any open menu or screen. Presses Escape.")
def close_menu() -> str:
    bridge = get_bridge()
    result = bridge.send_command("close_menu")
    state = bridge.get_state()
    return f"Closed menu. Current screen: {state.get('screen', '?')}\n{_fmt_state(state)}"


@server.tool(description="Enter look mode to examine things. Then use move directions to move the cursor, and read the description.")
def look() -> str:
    bridge = get_bridge()
    result = bridge.send_command("look")
    state = bridge.get_state()
    return f"Look mode. Screen: {state.get('screen', '?')}\n{_fmt_state(state)}"


@server.tool(description="Auto-explore: wander automatically to discover new tiles. Returns after exploring or getting stuck.")
def auto_explore() -> str:
    bridge = get_bridge()
    result = bridge.send_command("auto_explore")
    try:
        state = bridge.wait_for_turn(timeout=30.0)
        return f"Auto-explored.\n{_fmt_state(state)}"
    except TimeoutError:
        state = bridge.get_state()
        return f"Auto-explore (timeout).\n{_fmt_state(state)}"


@server.tool(description="Travel to a destination on the world map. Use after reaching the world map (overland).")
def travel(direction: str) -> str:
    bridge = get_bridge()
    result = bridge.send_command("travel", direction=direction)
    state = bridge.get_state()
    return f"Travel {direction}.\n{_fmt_state(state)}"


@server.tool(description="Go up or down stairs. direction: 'up' or 'down'.")
def go_stairs(direction: str) -> str:
    bridge = get_bridge()
    result = bridge.send_command("go_stairs", direction=direction)
    try:
        state = bridge.wait_for_turn(timeout=10.0)
        return f"Went {direction} stairs.\n{_fmt_state(state)}"
    except TimeoutError:
        state = bridge.get_state()
        return f"Go stairs {direction} (no turn change).\n{_fmt_state(state)}"


@server.tool(description="Save the game. Creates a quicksave.")
def save_game() -> str:
    bridge = get_bridge()
    result = bridge.send_command("save_game")
    return json.dumps(result, default=str)


@server.tool(description="Quit to the main menu.")
def quit_to_menu() -> str:
    bridge = get_bridge()
    result = bridge.send_command("quit_to_menu")
    return json.dumps(result, default=str)


@server.tool(description="Confirm a popup dialog (e.g. 'Yes' to quit/save confirmation).")
def confirm_popup() -> str:
    bridge = get_bridge()
    result = bridge.send_command("confirm_popup")
    return json.dumps(result, default=str)


@server.tool(description="Start a new game from the main menu.")
def start_new_game() -> str:
    bridge = get_bridge()
    result = bridge.send_command("start_new_game")
    return json.dumps(result, default=str)


@server.tool(description="Continue/load the most recent save from the main menu.")
def continue_game() -> str:
    bridge = get_bridge()
    result = bridge.send_command("continue_game")
    return json.dumps(result, default=str)


@server.tool(description="Auto-complete character creation with random choices. Selects Classic mode and Random character.")
def chargen_auto() -> str:
    bridge = get_bridge()
    result = bridge.send_command("chargen_auto")
    return json.dumps(result, default=str)


@server.tool(description="List available saves.")
def list_saves() -> str:
    bridge = get_bridge()
    result = bridge.send_command("list_saves")
    return json.dumps(result, default=str)


@server.tool(description="Press a key by name (e.g. 'space', 'escape', 'enter', 'tab').")
def press_key(key: str) -> str:
    bridge = get_bridge()
    result = bridge.send_command("press_key", key=key)
    state = bridge.get_state()
    return f"Pressed {key}. Screen: {state.get('screen', '?')}"


@server.tool(description="Focus the game window (bring to foreground).")
def focus_window() -> str:
    bridge = get_bridge()
    result = bridge.send_command("focus_window")
    return json.dumps(result, default=str)


@server.tool(description="Show item/equipment labels on screen (like the in-game labels feature).")
def show_labels() -> str:
    bridge = get_bridge()
    result = bridge.send_command("show_labels")
    return json.dumps(result, default=str)


@server.tool(description="Choose an option from a menu by number (1-based) or text.")
def choose_option(option: str) -> str:
    bridge = get_bridge()
    result = bridge.send_command("choose_option", option=option)
    state = bridge.get_state()
    return f"Chose option: {option}. Screen: {state.get('screen', '?')}"


@server.tool(description="Quit the game entirely.")
def quit_game() -> str:
    bridge = get_bridge()
    result = bridge.send_command("quit")
    return json.dumps(result, default=str)


@server.tool(description="Abandon the current character (permadeath).")
def abandon() -> str:
    bridge = get_bridge()
    result = bridge.send_command("abandon")
    return json.dumps(result, default=str)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
