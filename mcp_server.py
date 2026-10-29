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


def _difficulty(c: dict) -> str:
    d = _clean(c.get("difficulty") or "").strip()
    return f" [{d}]" if d else ""


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
_msg_count = {"seen": None, "lower": 0}


def _new_messages(msgs: list[str], count: int | None = None) -> list[str]:
    """Messages not shown by the previous state report. The mod sends the last 40 messages and the
    log's total count; the count's increase is what's new. Comparing windows instead breaks when the
    game merges a repeat into the last line ("... (x2)"), and an occasional stale snapshot (count
    84 between 500 and 504 in run 7) then made all 40 old messages look new and get learned twice."""
    global _seen_msgs
    seen, _seen_msgs = _seen_msgs, list(msgs)
    if isinstance(count, int):
        prev = _msg_count["seen"]
        if prev is not None and count < prev:
            # A stale snapshot, or a new game; believe a lower count once it repeats.
            _msg_count["lower"] += 1
            if _msg_count["lower"] < 2:
                _seen_msgs = seen
                return []
        _msg_count.update(seen=count, lower=0)
        if prev is None or count < prev:
            return msgs
        return msgs[len(msgs) - min(count - prev, len(msgs)):] if count > prev else []
    for i in range(min(len(seen), len(msgs)), 0, -1):
        if msgs[:i] == seen[-i:]:
            return msgs[i:]
    return msgs


def _world_pos(zone_id: str) -> tuple[int, int, int] | None:
    """Absolute zone x, y and depth from an id like JoppaWorld.11.22.1.1.10 (depth 10 = surface)."""
    parts = (zone_id or "").split(".")
    if len(parts) != 6 or not all(x.isdigit() for x in parts[1:]):
        return None
    px, py, zx, zy, z = map(int, parts[1:])
    return px * 3 + zx, py * 3 + zy, z


def _away(dx: int, dy: int) -> str:
    """'2 N 1 E' for an offset, 'here' for none."""
    return " ".join(f"{abs(d)} {w}" for d, w in ((dy, "N" if dy < 0 else "S"), (dx, "W" if dx < 0 else "E"))
                    if d) or "here"


# World-map lookups (mod action world_info) per parasang; refreshed when the player changes parasang
# and now and then, since places get revealed by conversations and exploring.
_world_cache: dict = {"key": None, "info": None, "uses": 0}


def _world_info(state: dict, radius: int = 6) -> dict | None:
    if _on_world_map(state):
        p = state.get("player") or {}
        key = (p.get("x"), p.get("y"))
    else:
        pos = _world_pos((state.get("zone") or {}).get("id", ""))
        if not pos:
            return None
        key = (pos[0] // 3, pos[1] // 3)
    c = _world_cache
    c["uses"] += 1
    # A failed lookup (e.g. while a save is still loading) is retried after a few calls.
    if c["key"] != (key, radius) or c["uses"] > (25 if c["info"] else 3):
        try:
            info = get_bridge().send_command("world_info", radius=radius)
        except Exception:
            info = {}
        c.update(key=(key, radius), info=info if info.get("ok") else None, uses=0)
    return c["info"]


def _places(info: dict) -> list[dict]:
    """Known named places: revealed map notes plus named (capitalized) terrain such as Joppa or Red Rock."""
    places, names = [], set()

    def key(text: str) -> str:
        return re.sub(r"^(the|a|an|some) ", "", text.lower())

    for n in info.get("places", []):
        text = _clean(n.get("text", ""))
        if text and key(text) not in names:
            names.add(key(text))
            places.append({**n, "text": text})
    for x, y, name in info.get("cells", []):
        if name[:1].isupper() and key(name) not in names:
            names.add(key(name))
            places.append({"text": name, "x": x, "y": y, "zx": 1, "zy": 1, "visited": False})
    return places


def _terrain_at(info: dict, x: int, y: int) -> str:
    return next((n for cx, cy, n in info.get("cells", []) if (cx, cy) == (x, y)), "?")


def _fmt_world(state: dict) -> str:
    """Where this zone is, what the parasangs around it are, and which way the known places are."""
    info = _world_info(state)
    if _on_world_map(state):
        p = state.get("player") or {}
        x, y = p.get("x"), p.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return ""
        here = f"WORLD MAP: you are at parasang ({x},{y})"
        if not info:
            return here + "; each move here is one parasang (3x3 zones). go_stairs('down') enters the local zones here."
        places = sorted(_places(info), key=lambda n: max(abs(n["x"] - x), abs(n["y"] - y)))[:6]
        return (f"{here}, {_terrain_at(info, x, y)}; each move here is one parasang (3x3 zones). "
                f"Next parasangs: {_around(info, x, y)}. "
                + (f"Known places, parasangs away: {'; '.join(n['text'] + ' ' + _away(n['x'] - x, n['y'] - y) for n in places)}. "
                   if places else "")
                + "go_stairs('down') enters the local zones here; world_map shows more.")
    pos = _world_pos((state.get("zone") or {}).get("id", ""))
    if not pos:
        return ""
    x, y, z = pos
    depth = "surface" if z == 10 else f"{z - 10} levels underground" if z > 10 else f"{10 - z} levels up"
    line = f"World: zone ({x},{y}), {depth}"
    if not info:
        return line
    px, py = x // 3, y // 3
    places = []
    for n in _places(info):
        dx, dy = n["x"] * 3 + n.get("zx", 1) - x, n["y"] * 3 + n.get("zy", 1) - y
        places.append((max(abs(dx), abs(dy)), n["text"] + " " + _away(dx, dy)))
    places = [t for _, t in sorted(places)[:6]]
    return (f"{line}, in the {_terrain_at(info, px, py)} parasang ({px},{py}). "
            f"Next parasangs: {_around(info, px, py)}"
            + (f". Known places, zones away: {'; '.join(places)}" if places else ""))


def _around(info: dict, x: int, y: int) -> str:
    return ", ".join(f"{d} {_terrain_at(info, x + dx, y + dy)}"
                     for d, (dx, dy) in (("N", (0, -1)), ("E", (1, 0)), ("S", (0, 1)), ("W", (-1, 0))))


# ── Creature knowledge ──────────────────────────────────────────────────
# A kind of creature is known by its base name: the name without the words the game adds for its
# state ("bloody hulking baboon", "wounded snapjaw"), which the mod reads from the creature's Render
# part. Blueprints only link names together; variants like "Snapjaw Scavenger 0" and "... 1" are one
# kind to the player. Messages carry display names, so a name from a message is matched to the known
# name it shares the most trailing words with. What the player learns is kept across runs in
# runs/bestiary.json.

# "The baboon hits (x2) for 6 damage with its bite.", "The vine hits you (x1) with a seed for 2 damage!",
# "The hulking baboon hits with a small boulder (x1) for 7 damage!"
_HIT_RE = re.compile(r"^The (.+?) (?:critically )?hits (?:you )?(?:with [^(!]*?)?\(x\d+\)(?: with [^!]*?)? "
                     r"for (\d+) damage", re.I)
_MISS_RE = re.compile(r"^The (.+?) misses you\b", re.I)
_DIES_RE = re.compile(r"^The (.+?) (?:dies|is destroyed)[.!]", re.I)
_XP_RE = re.compile(r"^You gain \d+ XP", re.I)
# The player's own actions end a creature's round of attacks.
_PLAYER_ACT = re.compile(r"^(You (?:critically )?(?:hit|miss|fire|throw|reload|pass by|equip|eat|drink|apply)\b|"
                         r"Your .+ fails to penetrate)", re.I)
_HEALING = re.compile(r"salve injector|bandage|witchwood|tonic|medkit|ubernostrum", re.I)
_ROOT = os.path.dirname(os.path.abspath(__file__))


def _name_key(name: Any) -> str:
    """Lower-case name without markup or a leading article."""
    return re.sub(r"^(the|a|an|some) ", "", " ".join(_clean(name or "").lower().split()))


def _suffix_len(a: str, b: str) -> int:
    """Words in the shorter name if it is the whole tail of the longer one, else 0."""
    aw, bw = a.split(), b.split()
    m = min(len(aw), len(bw))
    return m if m and aw[-m:] == bw[-m:] else 0


class _Bestiary:
    def __init__(self, path: str, tactics_path: str):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data: dict[str, dict] = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        try:
            with open(tactics_path, encoding="utf-8") as f:
                self.tactics = {k: v["tactics"] for k, v in json.load(f).items() if not k.startswith("_")}
        except (OSError, ValueError, KeyError, TypeError):
            self.tactics = {}
        self.names = {n: k for k, e in self.data.items() for n in e.get("names", [])}  # name -> kind
        self.shown: set[tuple] = set()  # (zone id, kind) already given a KNOW line
        self.last_hitter = ""
        self.dead = False

    def entry(self, kind: str) -> dict:
        e = self.data.setdefault(kind, {})
        for k, v in (("names", []), ("blueprints", []), ("hpMax", 0), ("hits", []), ("rounds", []),
                     ("kills", []), ("deaths", []), ("taken", 0)):
            e.setdefault(k, v)
        return e

    def kind(self, c: dict) -> str:
        """The kind of creature a state cell is: its base name, or what its blueprint was filed under."""
        base = _name_key(c.get("baseName"))
        if base:
            return base
        bp = c.get("blueprint")
        known = next((k for k, e in self.data.items() if bp and bp in e.get("blueprints", [])), "")
        return known or self.resolve(c.get("name")) or _name_key(c.get("name"))

    def _merge(self, into: str, other: str) -> None:
        a, b = self.entry(into), self.data.pop(other)
        for k in ("names", "blueprints"):
            a[k] += [x for x in b.get(k, []) if x not in a[k]]
        for k in ("hits", "rounds", "kills", "deaths"):
            a[k] = (a[k] + b.get(k, []))[-(10 if k == "rounds" else 12 if k == "hits" else 999):]
        a["hpMax"] = max(a["hpMax"], b.get("hpMax", 0))
        a["taken"] += b.get("taken", 0)
        for n in a["names"]:
            self.names[n] = into

    def observe(self, cells: list[dict]) -> bool:
        """Learn the names and HP of hostile creatures in view; True if anything new."""
        changed = False
        for c in cells:
            if not (c.get("isCreature") and c.get("isHostile")):
                continue
            kind, bp, shown = self.kind(c), c.get("blueprint"), _name_key(c.get("name"))
            if _name_key(c.get("baseName")):
                # Fold in what was filed under an older guess for the same creatures ("wet glowfish").
                for other in [k for k, e in self.data.items() if k != kind and bp in e.get("blueprints", [])]:
                    self._merge(kind, other)
                    changed = True
            elif kind in self.data and len(shown.split()) < len(kind.split()) and _suffix_len(shown, kind):
                # No base name from the mod: the shortest name seen is the best guess ("glowfish").
                self._merge(shown, kind)
                kind, changed = shown, True
            e = self.entry(kind)
            if bp and bp not in e["blueprints"]:
                e["blueprints"].append(bp)
                changed = True
            for n in (kind, _name_key(c.get("name"))):
                if n and n not in e["names"]:
                    e["names"].append(n)
                    changed = True
                if n:
                    self.names[n] = kind
            if isinstance(c.get("hpMax"), int) and c["hpMax"] > e["hpMax"]:
                e["hpMax"], changed = c["hpMax"], True
        return changed

    def resolve(self, name: str) -> str:
        """The kind of creature a name from a message refers to ('' if unknown or ambiguous)."""
        n = _name_key(name)
        if n in self.names:
            return self.names[n]
        best, best_len, tie = "", 0, False
        for k, kind in self.names.items():
            m = _suffix_len(k, n)
            if m > best_len:
                best, best_len, tie = kind, m, False
            elif m and m == best_len and kind != best:
                tie = True
        return "" if tie else best

    def learn(self, messages: list[str], state: dict) -> None:
        level = (state.get("player") or {}).get("level") or 0
        changed = self.observe(state.get("cells") or [])
        rounds: dict[str, int] = {}
        died: list[str] = []
        last = ""

        def close_rounds() -> None:
            for kind, dmg in rounds.items():
                r = self.entry(kind)["rounds"]
                r.append(dmg)
                del r[:-10]
            rounds.clear()

        for m in messages:
            m = _clean(m).strip()
            if hit := _HIT_RE.match(m):
                kind = self.resolve(hit.group(1)) or _name_key(hit.group(1))
                self.names.setdefault(_name_key(hit.group(1)), kind)
                e, dmg = self.entry(kind), int(hit.group(2))
                if _name_key(hit.group(1)) not in e["names"]:
                    e["names"].append(_name_key(hit.group(1)))
                e["hits"].append(dmg)
                del e["hits"][:-12]
                e["taken"] += dmg
                rounds[kind] = rounds.get(kind, 0) + dmg
                last, changed = kind, True
            elif _MISS_RE.match(m):
                continue
            elif dies := _DIES_RE.match(m):
                if kind := self.resolve(dies.group(1)):
                    died.append(kind)
            elif _XP_RE.match(m) and died:
                self.entry(died.pop(0))["kills"].append(level)
                changed = True
            elif _PLAYER_ACT.match(m):
                close_rounds()
        close_rounds()
        self.last_hitter = last or self.last_hitter
        dead = bool(state.get("isDead")) or (state.get("player") or {}).get("hp", 1) <= 0
        if dead and not self.dead and self.last_hitter:
            self.entry(self.last_hitter)["deaths"].append(level)
            changed = True
        self.dead = dead
        if changed:
            self.save()

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(self.path + ".tmp", self.path)
        except OSError:
            pass

    def hit_range(self, c: dict) -> tuple[int, int] | None:
        hits = self.data.get(self.kind(c), {}).get("hits")
        return (min(hits), max(hits)) if hits else None

    def worst_round(self, c: dict) -> int:
        return max(self.data.get(self.kind(c), {}).get("rounds") or [0])

    def tactic(self, base: str) -> str:
        """The tactics entry whose name ends (or starts) the creature's name, longest first."""
        best, best_len = "", 0
        for key, text in self.tactics.items():
            m = _suffix_len(key, base)
            if not m and base.split()[:len(key.split())] == key.split():
                m = len(key.split()) - 0.5  # 'snapjaw' for 'snapjaw scavenger', below a tail match
            if m > best_len:
                best, best_len = text, m
        return best

    def record(self, c: dict) -> str:
        e = self.data.get(self.kind(c))
        if not e:
            return ""
        parts = []
        if e.get("hpMax"):
            parts.append(f"{e['hpMax']} HP")
        if e.get("hits"):
            worst = max(e.get("rounds") or [0])
            parts.append(f"hits you for {min(e['hits'])}-{max(e['hits'])}"
                         + (f", up to {worst} in one round" if worst > max(e["hits"]) else ""))
        if e["kills"]:
            parts.append(f"you killed {len(e['kills'])} (at level {min(e['kills'])}"
                         + (f"-{max(e['kills'])}" if max(e["kills"]) != min(e["kills"]) else "") + ")")
        if e["taken"]:
            parts.append(f"they have done {e['taken']} damage to you in all")
        if e["deaths"]:
            parts.append(f"it killed you {len(e['deaths'])}x (at level {', '.join(map(str, e['deaths']))})")
        return "; ".join(parts)

    def know(self, c: dict) -> str:
        base = self.kind(c)
        tactic, record = self.tactic(base), self.record(c)
        if not tactic and not record:
            return ""
        return f"KNOW {base}: " + (tactic + " " if tactic else "") + (f"Your record: {record}." if record else "")


_beasts = _Bestiary(os.environ.get("COQ_BESTIARY") or os.path.join(_ROOT, "runs", "bestiary.json"),
                    os.path.join(_ROOT, "data", "creatures.json"))


def _know_lines(state: dict, hostiles: list[dict], only_new: bool = True, limit: int = 2) -> list[str]:
    """KNOW lines for the creature types in view; by default only those not yet covered in this zone."""
    zone, out, seen = (state.get("zone") or {}).get("id"), [], set()
    for c in hostiles:
        kind = _beasts.kind(c)
        if not kind or kind in seen or (only_new and (zone, kind) in _beasts.shown):
            continue
        seen.add(kind)
        _beasts.shown.add((zone, kind))
        line = _beasts.know(c)
        if line:
            out.append(line)
    return out[:limit] if limit else out


def _danger(state: dict) -> str:
    """A plain warning when the fight in front of the player is likely to kill them."""
    p = state.get("player") or {}
    hp, hp_max = p.get("hp"), p.get("hpMax") or 1
    if not isinstance(hp, int) or _on_world_map(state):
        return ""
    near = [c for c in state.get("cells") or [] if c.get("isCreature") and c.get("isHostile")
            and c.get("distance", 99) <= 3]
    if not near:
        return ""
    reasons = []
    for c in near:
        name = _clean(c.get("name") or "?").strip()
        rng, worst = _beasts.hit_range(c), _beasts.worst_round(c)
        # Many creatures attack several times a round (a bite and fists): two of its worst rounds,
        # or three of its hardest single hits.
        if worst and hp <= 2 * worst:
            reasons.append(f"the {name} has done up to {worst} damage in one round and you have {hp} HP")
        elif rng and hp <= 3 * rng[1]:
            reasons.append(f"the {name} has hit you for up to {rng[1]} at a time and you have {hp} HP")
        if _clean(c.get("difficulty", "")) in ("Very Tough", "Impossible") and c.get("distance", 99) <= 1:
            reasons.append(f"the {name} is rated {c['difficulty']} for you; don't trade melee blows with it")
    if hp * 100 < hp_max * 40:
        reasons.append(f"HP is below 40% ({hp}/{hp_max}) with {len(near)} hostile(s) within 3 tiles")
    if not reasons:
        return ""
    worst_c = min(near, key=lambda c: c.get("distance", 99))
    wname = _clean(worst_c.get("name", "?")).strip()
    nearly_dead = (isinstance(worst_c.get("hp"), int) and isinstance(worst_c.get("hpMax"), int)
                   and worst_c["hp"] * 4 <= worst_c["hpMax"])
    heals = [_clean(i.get("name", "")) for i in state.get("inventory") or [] if _HEALING.search(i.get("name", ""))]
    heal = (f"You carry {', '.join(heals)}: heal now with use_item(..., 'apply')" if heals
            else "You carry nothing to heal with")
    # Running from an adjacent enemy gives it free hits (run 7 died stepping away from a hulking
    # baboon at 1 HP); flee() only helps with a head start.
    if worst_c.get("distance", 99) <= 1:
        advice = (f"The {wname} is next to you, and turning your back gives it free hits. {heal}"
                  + (f"; it is nearly dead (HP {worst_c['hp']}/{worst_c['hpMax']}), so finishing it may be safest."
                     if nearly_dead else "; flee() only helps once you have a head start."))
    else:
        advice = f"Leave now with flee() while you have a head start, or keep shooting from range. {heal}."
    return "DANGER: " + "; ".join(dict.fromkeys(reasons)) + ". " + advice


_world_shown = {"zone": None, "n": 0}


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
    screen = state.get("screen")
    if not popup and screen == "WorldCreationProgress":
        lines.append("LOADING: the world is still being generated. Use wait until the map appears; don't close it.")
    elif not popup and screen not in (None, "", "Stage"):
        lines.append(f"SCREEN OPEN: {screen}. Movement and turns are blocked until close_menu closes it.")
    if _bridge is not None and _bridge.warnings:
        lines += [f"WARNING: {w}" for w in _bridge.warnings]
        _bridge.warnings.clear()
    lines.append(f"HP {p.get('hp', '?')}/{p.get('hpMax', '?')}  Lvl {p.get('level', '?')} "
                 f"XP {p.get('xp', '?')}/{p.get('xpNext', '?')}  at ({p.get('x', '?')},{p.get('y', '?')}) "
                 f"in {state.get('zone', {}).get('name', '?')}  {p.get('hunger', '?')}/{p.get('thirst', '?')}"
                 + ("  DEAD" if state.get("isDead") else ""))
    # The World line is long and only changes with the zone: show it on entering a zone, then every
    # 10th result (get_state always has it).
    zone_id = (state.get("zone") or {}).get("id")
    _world_shown["n"] += 1
    if zone_id != _world_shown["zone"] or _world_shown["n"] >= 10:
        world = _fmt_world(state)
        if world:
            lines.append(world)
            _world_shown.update(zone=zone_id, n=0)
    effects = state.get("effects", [])
    if effects:
        lines.append("Effects: " + ", ".join(e.get("name", "?") for e in effects[:10]))
    cells = sorted(state.get("cells", []), key=lambda c: c.get("distance", 999))
    hostiles = [c for c in cells if c.get("isCreature") and c.get("isHostile")]
    msgs = [_clean(m)[:200] for m in state.get("messages", []) if not isinstance(m, dict)]
    new = _new_messages(msgs, state.get("msgCount"))
    _beasts.learn(new, state)
    if hostiles:
        lines.append("Hostiles: " + "; ".join(
            f"{_clean(c.get('name') or c.get('blueprint', '?')).strip()} ({c['x']},{c['y']}) d={c.get('distance')} "
            f"HP={c.get('hp', '?')}/{c.get('hpMax', '?')}{_difficulty(c)}"
            + (f" hits you for {r[0]}-{r[1]}" if (r := _beasts.hit_range(c)) else "") for c in hostiles[:6]))
        lines += _know_lines(state, hostiles)
        danger = _danger(state)
        if danger:
            lines.append(danger)
    adjacent = [c for c in cells if c.get("isCreature") and not c.get("isHostile") and c.get("distance") == 1]
    if adjacent:
        lines.append("Adjacent: " + "; ".join(
            f"{_clean(c.get('name') or '?').strip()} ({c['x']},{c['y']})" for c in adjacent))
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
    if _fmt_world(state):
        lines.append(_fmt_world(state))
    lines.append(f"In Combat: {p.get('inCombat', False)}  "
                 f"Screen: {state.get('screen', '?')}  "
                 f"Dead: {state.get('isDead', False)}")
    lines.append(f"Time: {'Day' if t.get('isDay') else 'Night'}, turn segment {t.get('segment', '?')}")
    msgs = [m for m in state.get("messages", []) if not isinstance(m, dict)]
    _beasts.learn(_new_messages([_clean(m)[:200] for m in msgs], state.get("msgCount")), state)
    if _danger(state):
        lines.append(_danger(state))

    effects = state.get("effects", [])
    if effects:
        lines.append(f"\nEffects: {', '.join(e.get('name', '?') for e in effects[:10])}")

    abilities = state.get("abilities", [])
    if abilities:
        lines.append(f"\nAbilities: {', '.join(a.get('name', '?') for a in abilities[:15])}")

    quests = state.get("quests", [])
    if quests:
        lines.append(f"\n=== Quests ({len(quests)}) ===")
        for q in quests:
            giver = f" (from {q['giver']}{', ' + q['giverLocation'] if q.get('giverLocation') else ''})" if q.get("giver") else ""
            lines.append(f"  {q.get('name', '?')}{giver}")
            for st in q.get("steps", []):
                mark = "x" if st.get("finished") else "FAILED" if st.get("failed") else " "
                opt = " (optional)" if st.get("optional") else ""
                text = f": {' '.join(st['text'].split())[:200]}" if st.get("text") and not st.get("finished") else ""
                lines.append(f"    [{mark}] {st.get('name', '?')}{opt}{text}")

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
            if c.get("isCreature") and _clean(c.get("difficulty") or "").strip():
                tags.append(_clean(c["difficulty"]).strip())
            hp = f" HP={c.get('hp', '?')}/{c.get('hpMax', '?')}" if c.get("isCreature") else ""
            if c.get("isHostile") and (r := _beasts.hit_range(c)):
                hp += f" hits you for {r[0]}-{r[1]}"
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
        know = _know_lines(state, [c for c in creatures if c.get("isHostile")], only_new=False, limit=0)
        if know:
            lines.append("\n=== What you know about these creatures ===")
            lines += know

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


def _on_world_map(state: dict) -> bool:
    return str((state.get("zone") or {}).get("id", "")).endswith("World")


@server.tool(description=f"Move the player one tile. Valid directions: {_DIRECTIONS}. Moving into a creature attacks it.")
def move(direction: str) -> str:
    bridge = get_bridge()
    before = bridge.get_state()
    # A world-map step passes hours of game time, several seconds in real time.
    world = _on_world_map(before)
    out = _act("move", f"Moved {direction}", takes_turn=True, quiet=3 if world else 2,
               timeout=30.0 if world else TURN_TIMEOUT, direction=direction)
    if world or out.startswith("FAILED") or "POPUP OPEN" in out:
        return out
    # Say when the move didn't happen; "Moved south" while standing still misleads.
    b, after = before.get("player") or {}, bridge.get_state()
    a = after.get("player") or {}
    same_zone = (before.get("zone") or {}).get("id") == (after.get("zone") or {}).get("id")
    if not same_zone or (a.get("x"), a.get("y")) != (b.get("x"), b.get("y")):
        return out
    step = next((k for k, v in _STEP_DIRS.items() if v == _FULL_DIRS.get(direction.strip().lower())), None)
    target = (b.get("x", 0) + step[0], b.get("y", 0) + step[1]) if step else None
    occupant = next((c for c in before.get("cells") or [] if c.get("isCreature")
                     and (c["x"], c["y"]) == target), None)
    if occupant:
        what = (f"Attacked {_clean(occupant.get('name', '?'))} at ({target[0]},{target[1]}) "
                f"(moving into a creature attacks it); you did not move")
    else:
        held = [_clean(e.get("name", "")) for e in after.get("effects") or []
                if re.search(r"stuck|engulf|grab|held|paraly|immobil|web|pinned|prone|stun", _clean(e.get("name", "")), re.I)]
        what = (f"Did not move {direction}: ({target[0]},{target[1]}) is blocked"
                + (f", or an effect holds you ({', '.join(held)})" if held else ""))
    return what + out[len(f"Moved {direction}"):]


_FULL_DIRS = {"n": "north", "north": "north", "up": "north", "s": "south", "south": "south", "down": "south",
              "e": "east", "east": "east", "right": "east", "w": "west", "west": "west", "left": "west",
              "ne": "northeast", "northeast": "northeast", "up_right": "northeast",
              "nw": "northwest", "northwest": "northwest", "up_left": "northwest",
              "se": "southeast", "southeast": "southeast", "down_right": "southeast",
              "sw": "southwest", "southwest": "southwest", "down_left": "southwest"}

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


def _distances(state: dict, avoid: set, avoid_cost: int = 6) -> dict[tuple[int, int], int]:
    """Walking cost from the player to every reachable cell; cells in `avoid` (next to hostiles)
    cost extra."""
    zone = state.get("zone") or {}
    w, h = zone.get("width", 80), zone.get("height", 25)
    p = state["player"]
    start = (p["x"], p["y"])
    blocked = _blocked(state, set()) - {start}
    blocked |= {(c["x"], c["y"]) for c in state.get("cells", []) if c.get("isCreature")} - {start}
    dist = {start: 0}
    heap = [(0, start)]
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist[cur]:
            continue
        for dx, dy in _STEP_DIRS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if not (0 <= nxt[0] < w and 0 <= nxt[1] < h) or nxt in blocked or not _explored(state, *nxt):
                continue
            nd = d + 1 + (avoid_cost if nxt in avoid else 0)
            if nd < dist.get(nxt, 1 << 30):
                dist[nxt] = nd
                heapq.heappush(heap, (nd, nxt))
    return dist


def _escape_target(state: dict) -> tuple[tuple[int, int], str] | None:
    """The exit (zone edge or stairs) the player reaches soonest relative to the hostiles."""
    zone = state.get("zone") or {}
    w, h = zone.get("width", 80), zone.get("height", 25)
    foes = [(c["x"], c["y"]) for c in state.get("cells", []) if c.get("isCreature") and c.get("isHostile")]
    near_foes = {(fx + dx, fy + dy) for fx, fy in foes for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    dist = _distances(state, near_foes)
    exits = {(x, y): "edge" for (x, y) in dist if x in (0, w - 1) or y in (0, h - 1)}
    for c in state.get("cells", []):
        if _is_stairs(c) and (c["x"], c["y"]) in dist:
            exits[(c["x"], c["y"])] = "up" if "up" in _clean(c.get("name", "")).lower() else "down"
    if not exits:
        return None

    def score(cell: tuple[int, int]) -> int:
        foe = min((max(abs(cell[0] - fx), abs(cell[1] - fy)) for fx, fy in foes), default=99)
        return dist[cell] - foe  # get there well before anything that chases you

    best = min(exits, key=score)
    return best, exits[best]


@server.tool(description="Run from the hostiles in view: walks (up to max_steps) toward the zone edge or "
                         "stairs you can reach well ahead of them, around walls and away from the enemies, then "
                         "leaves the zone there (stepping across the edge, or taking the stairs). Pursuers that "
                         "follow arrive one at a time. Use it when a fight is going badly.")
def flee(max_steps: int = 15) -> str:
    bridge = get_bridge()
    state = bridge.get_state()
    if state.get("popup"):
        return "A popup is open — answer it first.\n\n" + _fmt_state(state)
    if "player" not in state or _on_world_map(state):
        return "FAILED flee: only works inside a zone.\n\n" + _fmt_state(state)
    if not any(c.get("isCreature") and c.get("isHostile") for c in state.get("cells", [])):
        return "No hostiles in view; nothing to flee from. Rest or move on.\n\n" + _fmt_state(state)
    start_hp = state["player"].get("hp")
    target = _escape_target(state)
    if target is None:
        return "FAILED flee: no reachable zone edge or stairs on the explored map. Fight, or heal.\n\n" + _fmt_state(state)
    (tx, ty), kind = target
    steps, reason = 0, "step limit reached"
    zone = state.get("zone") or {}
    w, h = zone.get("width", 80), zone.get("height", 25)
    zone_id = zone.get("id")
    while steps < max_steps:
        p = state["player"]
        here = (p["x"], p["y"])
        if here == (tx, ty):
            if kind in ("up", "down"):
                out = go_stairs(kind)
                return f"Fled {steps} steps to the stairs and went {kind}.\n" + out
            d = "west" if here[0] == 0 else "east" if here[0] == w - 1 else "north" if here[1] == 0 else "south"
            out = move(d)
            return (f"Fled {steps} steps to the zone edge at ({tx},{ty}) and stepped {d} into the next zone; "
                    f"pursuers arrive one at a time. Step back or keep going.\n" + out)
        foes = {(c["x"], c["y"]) for c in state.get("cells", []) if c.get("isCreature") and c.get("isHostile")}
        near_foes = {(fx + dx, fy + dy) for fx, fy in foes for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        others = {(c["x"], c["y"]) for c in state.get("cells", []) if c.get("isCreature")} - {here}
        path = _find_path(state, (tx, ty), others, avoid=near_foes, avoid_cost=6)
        if not path:
            reason = "the way out is blocked"
            break
        nxt = path[0]
        if any(c.get("isCreature") and (c["x"], c["y"]) == nxt for c in state.get("cells", [])):
            reason = f"something is in the way at ({nxt[0]},{nxt[1]})"
            break
        res = bridge.send_command("move", direction=_STEP_DIRS[(nxt[0] - here[0], nxt[1] - here[1])])
        if "error" in res:
            reason = f"move failed: {res['error']}"
            break
        state, _ = bridge.wait_for_turn(state)
        steps += 1
        if state.get("popup"):
            reason = "a popup opened"
            break
        if (state.get("zone") or {}).get("id") != zone_id or _is_dead(state):
            reason = "left the zone"
            break
        p = state.get("player") or {}
        if (p.get("x"), p.get("y")) == here:
            reason = "could not move (held, or the way is blocked)"
            break
    p = state.get("player") or {}
    hp = f"; HP {start_hp} -> {p.get('hp')}/{p.get('hpMax')}" if p.get("hp") != start_hp else ""
    return (f"flee: {reason} after {steps} steps toward the {'stairs' if kind != 'edge' else 'zone edge'} at "
            f"({tx},{ty}), now at ({p.get('x')},{p.get('y')}){hp}.\n\n" + _fmt_state(state))


def _is_dead(state: dict) -> bool:
    return bool(state.get("isDead")) or (state.get("player") or {}).get("hp", 1) <= 0


# Terrain that kills low-level characters (see the novice notes); go_to_place routes around it.
_RISKY_TERRAIN = ("jungle", "mountain", "hills", "river", "banana", "rainbow", "fungal", "ruins", "lake", "flower")


def _find_place(info: dict, place: str) -> dict | None:
    want = place.strip().lower()
    places = _places(info)
    m = re.fullmatch(r"\(?\s*(\d+)\s*,\s*(\d+)\s*\)?", want)
    if m:
        return {"text": f"parasang ({m.group(1)},{m.group(2)})", "x": int(m.group(1)), "y": int(m.group(2)),
                "zx": 1, "zy": 1}
    return (next((n for n in places if n["text"].lower() == want), None)
            or next((n for n in places if want in n["text"].lower()), None))


@server.tool(description="Walk to a known place (a name from the World line or world_map, e.g. 'Red Rock', or "
                         "parasang coordinates '11,20') zone by zone on the surface, up to max_zones zones per "
                         "call. Avoids jungles, hills, rivers and other risky terrain where it can, and stops when "
                         "hostiles block the way, a popup opens or you take damage. Call again to continue.")
def go_to_place(place: str, max_zones: int = 9) -> str:
    bridge = get_bridge()
    state = bridge.get_state()
    if "player" not in state:
        return "Not in game."
    info = bridge.send_command("world_info", radius=12)
    if not info.get("ok"):
        return f"FAILED go_to_place: {info.get('error', 'no world map here')}"
    target = _find_place(info, place)
    if target is None:
        known = ", ".join(n["text"] for n in _places(info)[:12])
        return f"FAILED go_to_place: no known place matches {place!r}. Known: {known or 'none'}."
    terrain = {(x, y): n for x, y, n in info.get("cells", [])}
    level = (state.get("player") or {}).get("level") or 1
    log: list[str] = []
    for _ in range(max_zones):
        if _on_world_map(state):
            return ("You are on the world map; go_stairs('down') to enter the zones here first, then call "
                    "go_to_place again.\n" + _fmt_compact(state))
        pos = _world_pos((state.get("zone") or {}).get("id", ""))
        if not pos:
            return "FAILED go_to_place: can't tell where this zone is.\n" + _fmt_compact(state)
        x, y, z = pos
        if z != 10:
            return "FAILED go_to_place: you are underground; take the stairs up to the surface first.\n" + _fmt_compact(state)
        tx, ty = target["x"] * 3 + target.get("zx", 1), target["y"] * 3 + target.get("zy", 1)
        if (x, y) == (tx, ty):
            return (f"Arrived at {target['text']}" + (f" ({'; '.join(log)})" if log else "") + ".\n"
                    + _fmt_compact(state))
        options = []
        for d, (dx, dy), gap in (("east", (1, 0), tx - x), ("west", (-1, 0), x - tx),
                                 ("south", (0, 1), ty - y), ("north", (0, -1), y - ty)):
            if gap <= 0:
                continue
            nx, ny = (x + dx) // 3, (y + dy) // 3
            name = terrain.get((nx, ny), "")
            risky = (level < 10 and (nx, ny) != (target["x"], target["y"])
                     and any(r in name.lower() for r in _RISKY_TERRAIN))
            options.append((risky, -gap, d, name))
        options.sort()
        if not options:
            break
        risky, _, d, name = options[0]
        if risky:
            return (f"Stopped: every way toward {target['text']} from here goes through risky terrain "
                    f"({name}) for a level-{level} character. Choose a route yourself (world_map), or go "
                    f"anyway with travel.\n" + _fmt_compact(state))
        before_zone = (state.get("zone") or {}).get("id")
        hp0 = (state.get("player") or {}).get("hp")
        out = travel(d)
        state = bridge.get_state()
        if (state.get("zone") or {}).get("id") == before_zone or state.get("popup"):
            return (f"go_to_place {target['text']}: stopped going {d}"
                    + (f" after {'; '.join(log)}" if log else "") + ".\n" + out)
        log.append(d)
        hp1 = (state.get("player") or {}).get("hp")
        if any(c.get("isCreature") and c.get("isHostile") for c in state.get("cells", [])) or \
                (isinstance(hp0, int) and isinstance(hp1, int) and hp1 < hp0):
            return (f"go_to_place {target['text']}: stopped after {len(log)} zone(s) ({', '.join(log)}): "
                    f"hostiles in view or you took damage.\n" + _fmt_compact(state))
    return (f"go_to_place {target['text']}: crossed {len(log)} zone(s) ({', '.join(log)}); call again to "
            f"continue.\n" + _fmt_compact(state))


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


@server.tool(description="The world map around you, as the game's world map and look command show it: one "
                         "letter per parasang (3x3 zones) with a legend that names and describes each terrain, "
                         "and the named places you know (villages, lairs, sites) with their direction. Use it to "
                         "plan travel and to see what kind of land lies in each direction.")
def world_map(radius: int = 5) -> str:
    state = get_bridge().get_state()
    if "player" not in state:
        return "Not in game."
    info = get_bridge().send_command("world_info", radius=max(1, min(radius, 12)))
    if not info.get("ok"):
        return f"FAILED world_map: {info.get('error', 'no world here')}"
    x0, y0 = info["x"], info["y"]
    cells = {(cx, cy): n for cx, cy, n in info.get("cells", [])}
    letters: dict[str, str] = {}
    for name in dict.fromkeys(cells.values()):
        named = name[:1].isupper()
        pool = [ch.upper() if named else ch.lower() for ch in name if ch.isalpha()] + list("0123456789")
        letters[name] = next((ch for ch in pool if ch not in letters.values() and ch != "@"), "~")
    xs = sorted({cx for cx, _ in cells})
    ys = sorted({cy for _, cy in cells})
    lines = [f"World map around parasang ({x0},{y0}); @ = you, north is up, one letter = one parasang.",
             "     " + " ".join(f"{cx:>2}"[-2] for cx in xs), "     " + " ".join(f"{cx:>2}"[-1] for cx in xs)]
    for cy in ys:
        lines.append(f"{cy:>3}  " + " ".join("@" if (cx, cy) == (x0, y0) else letters.get(cells.get((cx, cy), ""), " ")
                                            for cx in xs))
    lines.append("Legend:")
    for name, ch in letters.items():
        desc = " ".join(_clean(info.get("terrain", {}).get(name, "")).split())
        if len(desc) > 220:
            desc = desc[:217].rsplit(" ", 1)[0] + "..."
        lines.append(f"  {ch} {name}" + (f": {desc}" if desc else ""))
    places = sorted(_places(info), key=lambda n: max(abs(n["x"] - x0), abs(n["y"] - y0)))
    if places:
        lines.append("Known places (parasangs away):")
        for n in places[:20]:
            lines.append(f"  {n['text']}: {_away(n['x'] - x0, n['y'] - y0)}"
                         + (f" (category {n['category']})" if n.get("category") else "")
                         + (", visited" if n.get("visited") else ""))
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


@server.tool(description="Use an item from inventory. item_action: eat, drink/quaff, equip/wear/wield, apply/use (injectors, bandages, tonics), drop, unequip. item is the item name (partial match OK).")
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


@server.tool(description="Open a game screen (close it again with close_menu). Valid screens: inventory, equipment, "
                         "character, abilities, skills, quests, journal, factions, effects, messages, help.")
def open_screen(screen: str) -> str:
    out = _act("open_screen", f"Opened screen {screen}", screen=screen)
    if out.startswith("Opened") and get_bridge().get_state().get("screen") in (None, "", "Stage"):
        return f"open_screen {screen}: no screen opened." + out[out.index("\n"):]
    return out


_NOT_CLOSABLE = {
    "WorldCreationProgress": "The world is still being generated; use wait until the map appears.",
    "MainMenu": "This is the main menu (not in a game).",
    "EmbarkBuilder": "This is character creation.",
    "Chargen": "This is character creation.",
}


@server.tool(description="Close the open popup (Cancel/Continue) or menu/screen.")
def close_menu() -> str:
    bridge = get_bridge()
    before = bridge.get_state().get("screen")
    if before in _NOT_CLOSABLE:
        # Exit() on these aborts world creation / character creation back to the main menu.
        return f"Nothing to close: {before} is not a menu you can close. {_NOT_CLOSABLE[before]}"
    result = bridge.send_command("close_menu")
    if "error" in result:
        return f"FAILED close_menu: {result['error']}\n\n{_fmt_state(bridge.get_state())}"
    state = bridge.get_state()
    for _ in range(10):  # screens close on a later frame
        if state.get("screen") != before or state.get("popup"):
            break
        time.sleep(0.2)
        state = bridge.get_state()
    after = state.get("screen")
    if result.get("method") == "none" and before in (None, "", "Stage"):
        return f"Nothing to close.\n{_fmt_state(state)}"
    if before not in (None, "", "Stage") and after == before and not state.get("popup"):
        return (f"close_menu did NOT close the {before} screen (tried: {result.get('method', '?')}). "
                f"Keys can't close it; report this as a bridge bug.\n{_fmt_state(state)}")
    return f"Closed {before or 'menu'}.\n{_fmt_state(state)}"


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


@server.tool(description="Travel far in a cardinal direction (north/south/east/west) until something interesting "
                         "happens; on reaching the zone edge it steps into the next zone. If terrain blocks the "
                         "straight line it walks around it.")
def travel(direction: str) -> str:
    d = direction.strip().lower()[:1]
    if d not in "nsew" or not d:
        return f"FAILED travel: direction must be north, south, east or west, not {direction!r}"
    bridge = get_bridge()

    def at_edge(state: dict) -> bool:
        p, zone = state.get("player") or {}, state.get("zone") or {}
        return {"n": p.get("y") == 0, "s": p.get("y") == zone.get("height", 25) - 1,
                "w": p.get("x") == 0, "e": p.get("x") == zone.get("width", 80) - 1}[d]

    def hostiles(state: dict) -> list[dict]:
        return [c for c in state.get("cells") or [] if c.get("isCreature") and c.get("isHostile")]

    def walkable(state: dict) -> bool:
        # Walking is fine with hostiles far off; the game only refuses to *run* while any is in view.
        return not state.get("popup") and all(c.get("distance", 99) > 6 for c in hostiles(state))

    def pos(state: dict) -> tuple:
        p = state.get("player") or {}
        return (state.get("zone") or {}).get("id"), p.get("x"), p.get("y")

    def walk_to_edge(state: dict, offsets, origin: tuple | None = None) -> str:
        """go_to the first reachable cell on the edge at one of the offsets along it from origin
        (default: the player's position)."""
        zone, p = state.get("zone") or {}, state.get("player") or {}
        w, h = zone.get("width", 80), zone.get("height", 25)
        x0, y0 = origin or (p.get("x", 0), p.get("y", 0))
        p = {"x": p.get("x"), "y": p.get("y")}
        for off in offsets:
            tx, ty = {"n": (x0 + off, 0), "s": (x0 + off, h - 1), "w": (0, y0 + off), "e": (w - 1, y0 + off)}[d]
            if 0 <= tx < w and 0 <= ty < h and (tx, ty) != (p["x"], p["y"]) \
                    and "arrived" in go_to(tx, ty).split("\n", 1)[0]:
                return f"({tx},{ty})"
        return ""

    def cross(state: dict) -> str:
        """Step over the edge; if the cell beyond is blocked, try nearby edge cells."""
        out = move(direction)
        after = bridge.get_state()
        origin = ((state.get("player") or {}).get("x", 0), (state.get("player") or {}).get("y", 0))
        for off in (1, -1, 2, -2, 4, -4, 8, -8):
            if pos(after)[0] != pos(state)[0] or after.get("popup") or not walkable(after):
                break
            if walk_to_edge(after, (off,), origin):
                out = f"(the way across was blocked; tried {off:+d} along the edge)\n" + move(direction)
                after = bridge.get_state()
        return out

    state = bridge.get_state()
    if _on_world_map(state):  # the game's travel command doesn't work here; a step is one parasang
        return move(direction)
    if at_edge(state):  # running stops at the edge; the next zone is one plain step away
        return cross(state)
    start = pos(state)
    out = ""
    for _ in range(3):  # the game stops running whenever something comes into view; keep going
        before = pos(state)
        out = _act("travel", f"Travel {direction}", takes_turn=True, quiet=4, direction=direction)
        state = bridge.get_state()
        if out.startswith("FAILED") or at_edge(state) or pos(state) == before or hostiles(state) \
                or state.get("popup"):
            break
    if pos(state) == start and walkable(state) and not out.startswith("FAILED"):
        # Blocked straight ahead, or hostiles far off in view: walk to a reachable cell on that edge.
        cell = walk_to_edge(state, (0, 4, -4, 10, -10, 20, -20))
        if cell:
            out = (f"Travel {direction} couldn't run" + (" (hostiles in view, all far away)" if hostiles(state) else "")
                   + f"; walked to {cell} instead.")
        state = bridge.get_state()
    if at_edge(state) and walkable(state):
        return out.split("\n", 1)[0] + "\n" + cross(state)
    near = ", ".join(f"{_clean(c.get('name', '?'))} ({c['x']},{c['y']}) d={c.get('distance')}" for c in hostiles(state)[:3])
    if pos(state) == start and near and not state.get("popup"):
        out = (f"Travel {direction} did not move: the game won't run while hostiles are in view ({near}). "
               f"Fight them, or walk away with go_to/move.\n" + out.split("\n", 1)[-1])
    elif pos(state)[0] == start[0] and not at_edge(state) and not state.get("popup"):
        p = state.get("player") or {}
        out = (f"Travel {direction} stopped at ({p.get('x')},{p.get('y')}) before the edge"
               + (f": hostiles in view ({near})" if near else "") + ".\n" + out.split("\n", 1)[-1])
    return out


@server.tool(description="Go up or down stairs. direction: 'up' or 'down'.")
def go_stairs(direction: str) -> str:
    return _act("go_stairs", f"Went {direction} stairs", takes_turn=True, quiet=4,
                timeout=30.0, direction=direction)


@server.tool(description="Save the game. Creates a quicksave.")
def save_game() -> str:
    return json.dumps(get_bridge().send_command("save_game"), default=str)


@server.tool(description="Save the game and quit to the main menu (through the system menu's Save and Quit).")
def quit_to_menu() -> str:
    # Saves first, then leaves through the system menu's "Save and Quit". The game's own
    # quit command (CmdQuit) asks "Do you want to save first?" but ignores the answer
    # when it's given through the bridge and goes on to the type-ABANDON prompt.
    bridge = get_bridge()
    state = bridge.get_state()
    if not state.get("inGame"):
        return "Not in a game."
    if state.get("popup"):
        return "Answer the open popup first.\n" + _fmt_state(state)
    if "WorldCreationProgress" in str(state.get("viewStack") or ""):
        # A new game shows this view until the first turn passes; Escape does nothing there.
        wait(turns=1)
    saved = bridge.send_command("save_game")
    if "error" in saved:
        return f"FAILED quit_to_menu: could not save first: {saved['error']}"
    bridge.send_command("press_key", key="escape")  # opens the system menu on the map
    option = 0
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not option:
        time.sleep(0.2)
        popup = bridge.get_state().get("popup") or {}
        option = next((o.get("n", 0) for o in popup.get("options") or []
                       if "save and quit" in _clean(o.get("text", "")).lower()), 0)
    if not option:
        return "FAILED quit_to_menu: the system menu did not open.\n" + _fmt_state(bridge.get_state())
    res = bridge.send_command("respond_popup", option=option, button="", dismiss=False)
    if "error" in res:
        return f"FAILED quit_to_menu: {res['error']}"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            state = bridge.get_state()
        except Exception:
            continue
        if state.get("inMainMenu") or state.get("screen") == "MainMenu":
            return "Saved and quit to the main menu."
        if "saved" in _clean((state.get("popup") or {}).get("message", "")).lower():
            bridge.send_command("respond_popup", option=0, button="", dismiss=True)  # "Game saved!"
    return "Save and Quit chosen, but the main menu did not appear within 60s.\n" + _fmt_state(bridge.get_state())


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
        hint = (" continue_game only works from the main menu; to reload, use quit_to_menu first."
                if "already in game" in str(res.get("error", "")) else "")
        return "continue_game failed: " + json.dumps(res, default=str) + hint
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


@server.tool(description="List the game's preset characters (name, genotype, short description) for chargen_auto.")
def chargen_presets() -> str:
    r = get_bridge().send_command("chargen_presets")
    if "error" in r:
        return f"FAILED chargen_presets: {r['error']}"
    return "\n".join(f"{p['name']} ({p['genotype']}): {p['description']}" for p in r.get("presets", []))


@server.tool(description="Auto-complete character creation in Classic mode. preset = a preset character's "
                         "name from chargen_presets (starts in Joppa); empty or 'random' rolls a random character.")
def chargen_auto(preset: str = "") -> str:
    bridge = get_bridge()
    pregen = ""
    if preset and preset.lower() != "random":
        names = [p["name"] for p in bridge.send_command("chargen_presets").get("presets", [])]
        pregen = next((n for n in names if n.lower() == preset.strip().lower()), "")
        if not pregen:
            return f"FAILED chargen_auto: no preset named {preset!r}. Presets: {', '.join(names)}"
    for _ in range(20):  # start_new_game returns before the character builder exists
        res = bridge.send_command("chargen_auto", pregen=pregen)
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


@server.tool(description=f"Melee-attack an adjacent cell: give its x, y (as listed in results), or a direction "
                         f"({_DIRECTIONS}); with neither, the adjacent hostile. Works even where a move wouldn't "
                         f"attack, e.g. hostile plants like dreadroots you can walk over.")
def attack(direction: str = "", x: int = -1, y: int = -1) -> str:
    if not direction:
        state = get_bridge().get_state()
        p = state.get("player") or {}
        if x < 0 or y < 0:
            adjacent = [c for c in state.get("cells") or []
                        if c.get("isCreature") and c.get("isHostile") and c.get("distance") == 1]
            if not adjacent:
                return "FAILED attack: no hostile is adjacent; give x, y or a direction.\n" + _fmt_compact(state)
            x, y = adjacent[0]["x"], adjacent[0]["y"]
        dx, dy = x - p.get("x", 0), y - p.get("y", 0)
        if max(abs(dx), abs(dy)) != 1:
            return f"FAILED attack: ({x},{y}) is not adjacent to you at ({p.get('x')},{p.get('y')}); go_to it first."
        direction = {(0, -1): "n", (0, 1): "s", (1, 0): "e", (-1, 0): "w",
                     (1, -1): "ne", (-1, -1): "nw", (1, 1): "se", (-1, 1): "sw"}[(dx, dy)]
    d = _ATTACK_DIRS.get(direction.strip().lower())
    if d is None:
        return f"FAILED attack: invalid direction {direction!r}"
    return _act("press_command", f"Attacked {direction}", takes_turn=True, quiet=2, command=f"CmdAttack{d}")


@server.tool(description="Use an activated ability or mutation by name (e.g. Sprint, Freezing Ray, Force Bubble). "
                         "Abilities that need a target are aimed at cell (x, y), or at the nearest visible hostile "
                         "when x/y are omitted.")
def use_ability(name: str, x: int = -1, y: int = -1) -> str:
    bridge = get_bridge()
    state = bridge.get_state()
    abilities = state.get("abilities") or []
    wanted = name.strip().lower()
    match = (next((a for a in abilities if a.get("name", "").lower() == wanted), None)
             or next((a for a in abilities if wanted in a.get("name", "").lower()), None))
    if match is None:
        return (f"FAILED use_ability: no ability named {name!r}. You have: "
                + ", ".join(a.get("name", "?") for a in abilities))
    res = bridge.send_command("press_command", command=match["command"])
    if "error" in res:
        return f"FAILED use_ability: {res['error']}\n\n{_fmt_state(bridge.get_state())}"
    # Targeted abilities open the targeting screen; answer it with the target cell.
    deadline = time.monotonic() + 1.5
    targeting = False
    while time.monotonic() < deadline:
        time.sleep(0.15)
        cur = bridge.get_state()
        if cur.get("screen") == "PickTarget":
            targeting = True
            break
        if cur.get("popup") or _progress(cur) != _progress(state):
            break
    if not targeting:
        state_after, changed = bridge.wait_for_turn(state, timeout=TURN_TIMEOUT, quiet=2)
        note = "" if changed else " (no turn change detected)"
        return f"Used {match['name']}{note}.\n{_fmt_state(state_after)}"
    if x < 0 or y < 0:
        p = state.get("player") or {}
        hostiles = [c for c in state.get("cells") or [] if c.get("isHostile") and c.get("isCreature")]
        if not hostiles:
            bridge.send_command("close_menu")
            return (f"{match['name']} needs a target and no hostile is in sight; cancelled. "
                    "Pass x and y to aim it at a cell.\n" + _fmt_state(bridge.get_state()))
        near = min(hostiles, key=lambda c: max(abs(c["x"] - p.get("x", 0)), abs(c["y"] - p.get("y", 0))))
        x, y = near["x"], near["y"]
    res = bridge.send_command("pick_target", x=x, y=y)
    if "error" in res:
        bridge.send_command("close_menu")
        return f"FAILED use_ability: could not aim {match['name']}: {res['error']}\n\n{_fmt_state(bridge.get_state())}"
    state_after, changed = bridge.wait_for_turn(state, timeout=TURN_TIMEOUT, quiet=2)
    if state_after.get("screen") == "PickTarget":
        bridge.send_command("close_menu")
        return (f"{match['name']} could not target ({x},{y}) (out of range or not visible?); cancelled.\n"
                + _fmt_state(bridge.get_state()))
    note = "" if changed else " (no turn change detected)"
    return f"Used {match['name']} at ({x},{y}){note}.\n{_fmt_state(state_after)}"


@server.tool(description="Fire your missile weapon (bow, gun) at cell (x, y) — default: the nearest "
                         "hostile — reloading first if needed. Shoot enemies while they approach.")
def fire(x: int = -1, y: int = -1) -> str:
    bridge = get_bridge()
    before = bridge.get_state()
    if before.get("popup"):
        return "A popup is open — answer it first.\n\n" + _fmt_state(before)
    auto = x < 0 or y < 0
    p = before.get("player") or {}
    if not auto and (x, y) == (p.get("x"), p.get("y")):
        return (f"FAILED fire: ({x},{y}) is your own position. Give a hostile's x, y, or no arguments to shoot "
                "the nearest hostile.\n" + _fmt_compact(before))
    note = ""
    if not auto and not any(c.get("isCreature") and (c["x"], c["y"]) == (x, y) for c in before.get("cells", [])):
        # Coordinates from an older result: the target has usually moved a tile or two (run 7 spent
        # 12 of 36 arrows on empty cells). Follow it if it is close; otherwise don't waste the turn.
        near = sorted((c for c in before.get("cells", []) if c.get("isCreature") and c.get("isHostile")
                       and max(abs(c["x"] - x), abs(c["y"] - y)) <= 2),
                      key=lambda c: max(abs(c["x"] - x), abs(c["y"] - y)))
        if not near:
            return (f"Not fired: there is no creature at ({x},{y}) now, so the shot would be wasted. "
                    "Call fire() with no arguments to shoot the nearest hostile.\n" + _fmt_compact(before))
        note = f" (nothing was at ({x},{y}) any more; aimed at the {_clean(near[0].get('name', '?'))} instead)"
        x, y = near[0]["x"], near[0]["y"]
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
    return f"Fired at ({x},{y}) [{_clean(target)}]{note}.\n" + _fmt_state(state)


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
