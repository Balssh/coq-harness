"""Render a recorded run to MP4: one 1920x1080 frame per snapshot, with the game screenshot,
the map drawn from the recorded state, stats, what changed since the previous frame, the model's
step (thinking, text, tool calls and results), its memory, recent messages and an event timeline.

    python -m harness export <run> [--speed 2] [--smart] [--annotations] [--out file.mp4]

`--speed` scales the base pace of one second per frame; `--smart` lingers on fights, damage and
other events and skips quickly over idle stretches (the same rule as the viewer's smart playback);
`--annotations` burns the reviewer's notes from the viewer into the frames.

Frames are drawn with Pillow and piped to ffmpeg (libx264), which must be on PATH.
"""

import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG, PANEL, LINE = (15, 20, 24), (23, 32, 38), (43, 58, 68)
TEXT, MUTED, ACCENT = (215, 226, 232), (138, 160, 173), (79, 195, 161)
HP, HPBG, WARN, BAD, INFO = (63, 191, 95), (58, 31, 34), (224, 160, 64), (224, 90, 90), (90, 168, 224)
GLYPH = {"hostile": (255, 95, 86), "friendly": (95, 211, 106), "neutral": (232, 195, 90),
         "creature": (201, 184, 255), "wall": (107, 122, 132), "item": (90, 209, 232), "door": (201, 138, 75),
         "container": (208, 160, 96), "stairs": (255, 224, 102), "feature": (61, 75, 84)}

_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF", "/Library/Fonts",
              "/mnt/c/Windows/Fonts", "C:/Windows/Fonts"]
_FONT_FILES = {"sans": ["DejaVuSans.ttf", "segoeui.ttf", "Arial.ttf"],
               "bold": ["DejaVuSans-Bold.ttf", "segoeuib.ttf", "Arial Bold.ttf"],
               "mono": ["DejaVuSansMono.ttf", "consola.ttf", "Menlo.ttc"],
               "monob": ["DejaVuSansMono-Bold.ttf", "consolab.ttf", "Menlo.ttc"]}
_fonts: dict = {}


def font(kind: str, size: int):
    key = (kind, size)
    if key not in _fonts:
        for d in _FONT_DIRS:
            for name in _FONT_FILES[kind]:
                p = Path(d) / name
                if p.exists():
                    _fonts[key] = ImageFont.truetype(str(p), size)
                    break
            if key in _fonts:
                break
        else:
            _fonts[key] = ImageFont.load_default(size)
    return _fonts[key]


def strip(s) -> str:
    """Remove Qud colour markup ({{B|text}}, possibly nested, and &X codes)."""
    s, prev = str(s or ""), None
    while s != prev:
        s, prev = re.sub(r"\{\{[^|{}]*\|([^{}]*)\}\}", r"\1", s), s
    return re.sub(r"&[a-zA-Z]", "", s)


def _base_name(name: str) -> str:
    """An item or effect name without the details that change as it's used (charges, drams, stack size)."""
    return re.sub(r"\s*(\[[^\]]*\]|\([^)]*\)|x\d+)", "", strip(name)).strip()


def wrap(text: str, f, width: int) -> list[str]:
    lines = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if f.getlength(cand) <= width:
                line = cand
                continue
            if line:
                lines.append(line)
            while f.getlength(word) > width:  # break very long words
                cut = len(word)
                while cut > 1 and f.getlength(word[:cut]) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


class Block:
    """Draws wrapped text top-down inside a box and stops (with an ellipsis) when full."""

    def __init__(self, d: ImageDraw.ImageDraw, x: int, y: int, w: int, bottom: int):
        self.d, self.x, self.y, self.w, self.bottom = d, x, y, w, bottom

    def text(self, text: str, f, fill, max_lines: int = 99, indent: int = 0, gap: int = 4) -> bool:
        lh = f.size + 5
        lines = wrap(text, f, self.w - indent)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip() + " …"
        for line in lines:
            if self.y + lh > self.bottom:
                return False
            self.d.text((self.x + indent, self.y), line, font=f, fill=fill)
            self.y += lh
        self.y += gap
        return True

    def heading(self, text: str) -> None:
        if self.y + 22 <= self.bottom:
            self.d.text((self.x, self.y), text.upper(), font=font("bold", 14), fill=MUTED)
            self.y += 24


def _panel(d, box, title: str | None = None):
    d.rounded_rectangle(box, radius=8, fill=PANEL, outline=LINE)
    if title:
        d.text((box[0] + 14, box[1] + 10), title.upper(), font=font("bold", 14), fill=MUTED)


def _glyph(cs: list[dict]) -> tuple[str, tuple]:
    cr = next((c for c in cs if c.get("isCreature")), None)
    if cr:
        name = re.sub(r"^(a|an|the)\s+", "", strip(cr.get("name")), flags=re.I)
        col = (GLYPH["hostile"] if cr.get("isHostile") else GLYPH["friendly"] if cr.get("isFriendly")
               else GLYPH["neutral"] if cr.get("isNeutral") else GLYPH["creature"])
        return (name[:1] or "c"), col
    st = next((c for c in cs if "stair" in (c.get("name", "") + c.get("blueprint", "")).lower()), None)
    if st:
        return ("<" if "up" in st.get("name", "").lower() else ">"), GLYPH["stairs"]
    for key, g, col in (("isDoor", "+", "door"), ("isContainer", "=", "container"), ("isItem", "*", "item"),
                        ("blocksMovement", "#", "wall")):
        if any(c.get(key) for c in cs):
            return g, GLYPH[col]
    return "·", GLYPH["feature"]


def draw_map(d, state: dict, box, trail: list[tuple[int, int]] | None = None) -> None:
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=(19, 32, 38))
    z = (state or {}).get("zone") or {}
    zw, zh = z.get("width", 80), z.get("height", 25)
    cw, ch = (x1 - x0) / zw, (y1 - y0) / zh
    if not (state or {}).get("player"):
        d.text((x0 + 10, y0 + 10), "not in game", font=font("sans", 16), fill=MUTED)
        return
    explored = z.get("explored") or []
    grid: dict = {}
    for c in state.get("cells") or []:
        grid.setdefault((c["x"], c["y"]), []).append(c)
    f = font("mono", max(8, int(min(ch, cw * 1.7))))
    for y in range(zh):
        for x in range(zw):
            known = explored[y][x] == "1" if y < len(explored) and x < len(explored[y]) else True
            cx, cy = x0 + x * cw, y0 + y * ch
            if not known:
                d.rectangle((cx, cy, cx + cw, cy + ch), fill=(7, 10, 12))
                continue
            if (x, y) in grid:
                g, col = _glyph(grid[(x, y)])
                d.text((cx + cw / 2, cy + ch / 2), g, font=f, fill=col, anchor="mm")
    if trail and len(trail) > 1:  # recent path in this zone, oldest first
        pts = [(x0 + tx * cw + cw / 2, y0 + ty * ch + ch / 2) for tx, ty in trail]
        for n in range(1, len(pts)):
            shade = int(60 + 140 * n / len(pts))
            jump = max(abs(trail[n][0] - trail[n - 1][0]), abs(trail[n][1] - trail[n - 1][1])) > 2
            d.line((pts[n - 1], pts[n]), fill=(shade // 3, shade // 2, shade // 2) if jump else
                   (shade // 2, shade, int(shade * 0.85)), width=1 if jump else 2)
    p = state["player"]
    px, py = x0 + p["x"] * cw, y0 + p["y"] * ch
    d.rectangle((px, py, px + cw, py + ch), fill=(40, 90, 78))
    d.text((px + cw / 2, py + ch / 2), "@", font=font("monob", f.size), fill=(255, 255, 255), anchor="mm")


def load_run(run_dir: Path) -> tuple[dict, list[dict]]:
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    events = []
    for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return meta, events


# Tools that only look at things or touch the model's own memory; a frame from one of these with no
# change in position, HP, zone or popup counts as idle for smart pacing.
PASSIVE_TOOLS = {"get_state", "get_map", "note", "forget_note", "set_goal", "list_skills", "trade_list", "look"}
FIGHT_TOOLS = {"attack", "fire", "use_ability"}
# Seconds-per-frame multipliers for smart pacing, strongest kind wins (see frame_kinds).
PACE = {"death": 3.0, "damage": 2.0, "fight": 2.0, "level": 1.75, "annotation": 2.0, "zone": 1.4, "popup": 1.25,
        "nudge": 1.25, "error": 1.25, "idle": 0.3}
# Timeline lanes, top to bottom: (kind, label, colour)
LANES = [("damage", "damage", (224, 90, 90)), ("fight", "fight", (240, 130, 80)), ("popup", "popup", (190, 150, 230)),
         ("zone", "zone", (90, 168, 224)), ("nudge", "nudge", (224, 160, 64)), ("summary", "summary", (120, 150, 170)),
         ("error", "error", (255, 70, 70)), ("level", "level", (79, 195, 161)), ("annotation", "note", (240, 220, 90))]


def frame_kinds(frames: list[dict], events: list[dict], annotations: dict | None = None) -> list[set[str]]:
    """What happened at each snapshot: damage, heal, fight, popup, zone, nudge, summary, error, level, death,
    annotation, idle. Mirrors frameKinds() in viewer/index.html."""
    kinds: list[set[str]] = [set() for _ in frames]
    if not frames:
        return kinds
    by_index = {s["index"]: k for k, s in enumerate(frames)}
    last_for_step: dict[int, int] = {}
    for k, s in enumerate(frames):
        last_for_step[s["step"]] = k

    def frame_of_step(step: int) -> int:
        best = 0
        for st, k in last_for_step.items():
            if st <= step and k > best:
                best = k
        return best
    tool_at: dict[int, dict] = {}
    for e in events:
        t = e.get("type")
        if t == "tool" and e.get("snapshot") in by_index:
            k = by_index[e["snapshot"]]
            tool_at[k] = e
            if e.get("name") in FIGHT_TOOLS:
                kinds[k].add("fight")
            if e.get("is_error"):
                kinds[k].add("error")
        elif t in ("nudge", "summary", "error"):
            kinds[frame_of_step(e.get("step", 0))].add(t)
        elif t == "run_end" and e.get("outcome") == "died":
            kinds[-1].add("death")
    for step in (annotations or {}):
        try:
            st = int(step)
        except ValueError:
            continue
        for k, s in enumerate(frames):
            if s["step"] == st:
                kinds[k].add("annotation")
    for k, s in enumerate(frames):
        p = frames[k - 1] if k else None
        if s.get("dead"):
            kinds[k].add("death")
        if p is None:
            continue
        if s.get("hp") is not None and p.get("hp") is not None:
            if s["hp"] < p["hp"]:
                kinds[k].add("damage")
            elif s["hp"] > p["hp"]:
                kinds[k].add("heal")
        if s.get("zoneId") and p.get("zoneId") and s["zoneId"] != p["zoneId"]:
            kinds[k].add("zone")
        if s.get("popup") and s.get("popup") != p.get("popup"):
            kinds[k].add("popup")
        if s.get("level") is not None and p.get("level") is not None and s["level"] > p["level"]:
            kinds[k].add("level")
        tool = tool_at.get(k)
        still = (s.get("x"), s.get("y"), s.get("hp"), s.get("zoneId"), s.get("popup")) == \
                (p.get("x"), p.get("y"), p.get("hp"), p.get("zoneId"), p.get("popup"))
        if still and not kinds[k] and (tool is None or tool.get("name") in PASSIVE_TOOLS or tool.get("name") == "wait"):
            kinds[k].add("idle")
    return kinds


def pace(kinds: set[str]) -> float:
    """Smart-pacing multiplier for one frame."""
    if "idle" in kinds:
        return PACE["idle"]
    return max([PACE[k] for k in kinds if k in PACE] or [1.0])


def changes(snap: dict, prev_snap: dict | None, state: dict, prev_state: dict | None,
            mem: dict | None, prev_mem: dict | None) -> list[tuple[str, str]]:
    """What changed since the previous frame, as (text, kind) badges. Mirrors frameDiff() in the viewer."""
    out: list[tuple[str, str]] = []
    if not prev_snap:
        return out
    if snap.get("hp") is not None and prev_snap.get("hp") is not None and snap["hp"] != prev_snap["hp"]:
        dh = snap["hp"] - prev_snap["hp"]
        out.append((f"{dh:+d} HP", "bad" if dh < 0 else "good"))
    if snap.get("level") is not None and prev_snap.get("level") is not None and snap["level"] > prev_snap["level"]:
        out.append((f"level {snap['level']}!", "good"))
    if (snap.get("xp") or 0) > (prev_snap.get("xp") or 0):
        out.append((f"+{snap['xp'] - (prev_snap.get('xp') or 0)} XP", "good"))
    if snap.get("zoneId") != prev_snap.get("zoneId") and snap.get("zone"):
        out.append((f"→ {strip(snap['zone'])}", "info"))
    elif snap.get("x") is not None and prev_snap.get("x") is not None and \
            (snap["x"], snap["y"]) != (prev_snap["x"], prev_snap["y"]):
        dist = max(abs(snap["x"] - prev_snap["x"]), abs(snap["y"] - prev_snap["y"]))
        out.append((f"moved {dist} to ({snap['x']},{snap['y']})", "muted"))
    if prev_state is not None and state:
        def names(st, key):
            return [_base_name(x.get("name") if isinstance(x, dict) else x) for x in (st.get(key) or [])]
        for key in ("inventory", "effects"):
            a, b = names(prev_state, key), names(state, key)
            gained = [n for n in b if n not in a]
            lost = [n for n in a if n not in b]
            for n in gained[:3]:
                out.append((f"+ {n}", "good" if key == "inventory" else "info"))
            for n in lost[:3]:
                out.append((f"− {n}", "muted"))
    if mem is not None and prev_mem is not None and mem is not prev_mem:
        if (mem.get("goal") or "") != (prev_mem.get("goal") or ""):
            out.append(("goal changed", "info"))
        a, b = prev_mem.get("notes") or [], mem.get("notes") or []
        added, removed = len([n for n in b if n not in a]), len([n for n in a if n not in b])
        if added:
            out.append((f"+{added} note" + ("s" if added > 1 else ""), "info"))
        if removed:
            out.append((f"−{removed} note" + ("s" if removed > 1 else ""), "muted"))
        if (mem.get("summary") or "") != (prev_mem.get("summary") or ""):
            out.append(("context summarized", "info"))
    return out


def export_name(speed: float = 1.0, smart: bool = False, annotations: bool = False) -> str:
    """Default file name for an export, so exports with different settings sit side by side."""
    sp = f"{speed:g}".replace(".", "_")
    return f"replay_{sp}x" + ("_smart" if smart else "") + ("_notes" if annotations else "") + ".mp4"


class Renderer:
    def __init__(self, run_dir: Path, annotations: bool = False):
        self.dir = run_dir
        self.meta, self.events = load_run(run_dir)
        self.frames = [e for e in self.events if e["type"] == "snapshot"]
        self.by_step: dict[int, list[dict]] = {}
        for e in self.events:
            self.by_step.setdefault(e["step"], []).append(e)
        self.notes: dict[str, dict] = {}
        if annotations:
            try:
                self.notes = json.loads((run_dir / "annotations.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        self.kinds = frame_kinds(self.frames, self.events, self.notes)
        # memory event in force at each frame
        self.mem: list[dict | None] = []
        mem = None
        for e in self.events:
            if e["type"] == "memory":
                mem = e
            elif e["type"] == "snapshot":
                self.mem.append(mem)

    def _state(self, snap: dict) -> dict:
        try:
            return json.loads((self.dir / "states" / f"{snap['index']:05d}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _memory_at(self, i: int) -> dict | None:
        return self.mem[i]

    def render(self, i: int, prev_state: dict | None = None) -> tuple[Image.Image, dict]:
        snap = self.frames[i]
        state = self._state(snap)
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        m = self.meta

        # header
        title = f"Caves of Qud · {m.get('label') or m.get('run_id')} · {m.get('model')}"
        d.text((20, 16), title, font=font("bold", 22), fill=TEXT)
        t = int(snap.get("t") or 0)
        right = f"step {snap['step']}/{m.get('steps', '?')} · frame {i + 1}/{len(self.frames)} · {t // 60}:{t % 60:02d}"
        d.text((W - 20, 18), right, font=font("mono", 18), fill=MUTED, anchor="ra")

        # left: screenshot, stats, map
        _panel(d, (16, 56, 1136, 664))
        shot = self.dir / snap["frame"] if snap.get("frame") else None
        if shot and shot.exists():
            pic = Image.open(shot).convert("RGB")
            pic.thumbnail((1104, 592))
            img.paste(pic, (24 + (1104 - pic.width) // 2, 64 + (592 - pic.height) // 2))
        else:
            d.text((576, 360), "no screenshot", font=font("sans", 18), fill=MUTED, anchor="mm")
        _panel(d, (16, 672, 1136, 1006))
        p = state.get("player") or {}
        hp, mx = p.get("hp", snap.get("hp")), p.get("hpMax", snap.get("hpMax"))
        d.rectangle((28, 682, 1124, 690), fill=HPBG)
        if mx:
            d.rectangle((28, 682, 28 + int(1096 * max(0, min(1, (hp or 0) / mx))), 690), fill=HP)
        stats = [("HP", f"{hp}/{mx}"), ("Lvl", p.get("level")), ("XP", f"{p.get('xp')}/{p.get('xpNext')}"),
                 ("AV", p.get("av")), ("DV", p.get("dv")), ("Zone", strip((state.get("zone") or {}).get("name"))),
                 ("Pos", f"{p.get('x')},{p.get('y')}"), ("Screen", state.get("screen"))]
        x = 28
        for k, v in stats:
            if v in (None, "", "None/None"):
                continue
            d.text((x, 698), k, font=font("sans", 15), fill=MUTED)
            x += int(font("sans", 15).getlength(k)) + 6
            d.text((x, 698), str(v), font=font("bold", 15), fill=TEXT)
            x += int(font("bold", 15).getlength(str(v))) + 18
        trail = []
        for s in self.frames[max(0, i - 40):i + 1]:
            if s.get("zoneId") == snap.get("zoneId") and s.get("x") is not None:
                trail.append((s["x"], s["y"]))
            else:
                trail = []
        draw_map(d, state, (28, 722, 1124, 996), trail)

        # right: step, memory, messages
        evs = self.by_step.get(snap["step"], [])
        llm = next((e for e in evs if e["type"] == "llm"), None)
        tools = [e for e in evs if e["type"] == "tool"]
        _panel(d, (1152, 56, 1904, 640), f"Step {snap['step']}" + (" — start" if snap["step"] == 0 else ""))
        y = 84
        badges = changes(snap, self.frames[i - 1] if i else None, state, prev_state,
                         self.mem[i], self.mem[i - 1] if i else None)
        x = 1168
        for text, kind in badges:
            f = font("bold", 14)
            w = int(f.getlength(text)) + 16
            if x + w > 1888:
                x, y = 1168, y + 26
                if y > 160:
                    break
            col = {"bad": BAD, "good": HP, "info": INFO}.get(kind, MUTED)
            d.rounded_rectangle((x, y, x + w, y + 22), radius=11, outline=col, width=1)
            d.text((x + 8, y + 3), text, font=f, fill=col)
            x += w + 6
        b = Block(d, 1168, y + (30 if badges else 4), 720, 628)
        if llm:
            if llm.get("reasoning"):
                b.text("Thinking: " + llm["reasoning"].replace("\n", " "), font("sans", 15), MUTED, max_lines=7)
            if llm.get("text"):
                b.text(llm["text"], font("sans", 17), TEXT, max_lines=5)
        for e in tools:
            cur = e.get("snapshot") == snap["index"]
            args = json.dumps(e.get("args") or {})[1:-1]
            b.text(("▶ " if cur else "  ") + f"{e['name']}({args})", font("monob", 15),
                   ACCENT if cur else (BAD if e.get("is_error") else TEXT), max_lines=2)
            if cur:
                b.text(e.get("result", ""), font("mono", 13), TEXT, max_lines=9, indent=18)
        for e in evs:
            if e["type"] == "nudge":
                b.text(f"Harness ({e.get('kind')}): {e.get('text')}", font("sans", 14), WARN, max_lines=2)
            elif e["type"] == "run_end":
                b.text(f"Run ended: {e.get('outcome')}", font("bold", 18), BAD if e.get("outcome") == "died" else INFO)
        _panel(d, (1152, 648, 1904, 846), "Memory")
        mem = self._memory_at(i) or {}
        b = Block(d, 1168, 680, 720, 836)
        b.text("Goal: " + (mem.get("goal") or "—"), font("bold", 15), TEXT, max_lines=2)
        for n, note in enumerate(mem.get("notes") or [], 1):
            if not b.text(f"{n}. {note}", font("sans", 13), MUTED, max_lines=2, gap=1):
                break
        _panel(d, (1152, 854, 1904, 1006), "Messages")
        msgs = [strip(x) for x in state.get("messages") or []]
        before = {strip(x) for x in (prev_state or {}).get("messages") or []}
        b = Block(d, 1168, 884, 720, 1000)
        for msg in msgs[-6:]:
            b.text(msg, font("mono", 13), TEXT if msg not in before else MUTED, max_lines=1, gap=0)

        note = self.notes.get(str(snap["step"]))
        if note and note.get("text"):
            f = font("bold", 18)
            lines = wrap("Reviewer: " + note["text"], f, 1060)[:3]
            top = 656 - 12 - len(lines) * 24
            overlay = Image.new("RGBA", (1104, len(lines) * 24 + 12), (40, 34, 10, 225))
            img.paste(overlay, (24, top), overlay)
            d.rectangle((24, top, 28, top + len(lines) * 24 + 12), fill=(240, 220, 90))
            for n, line in enumerate(lines):
                d.text((38, top + 6 + n * 24), line, font=f, fill=(250, 235, 150))

        self._timeline(d, i)
        return img, state

    def _timeline(self, d, i: int) -> None:
        x0, y0, x1, y1 = 16, 1016, 1904, 1072
        d.rounded_rectangle((x0, y0, x1, y1), radius=8, fill=PANEL, outline=LINE)
        n = max(1, len(self.frames) - 1)
        lx0 = x0 + 8
        xs = lambda k: lx0 + (x1 - 8 - lx0) * k / n
        # HP curve in the top half, event ticks in a strip below it
        hy0, hy1 = y0 + 4, y0 + 30
        pts = [(xs(k), hy1 - (s["hp"] / s["hpMax"] if s.get("hpMax") else 0) * (hy1 - hy0))
               for k, s in enumerate(self.frames) if s.get("hp") is not None]
        if len(pts) > 1:
            d.line(pts, fill=HP, width=2)
        lane_h = (y1 - 4 - (hy1 + 4)) / len(LANES)
        for li, (kind, _, col) in enumerate(LANES):
            ly = hy1 + 4 + li * lane_h
            for k, ks in enumerate(self.kinds):
                if kind in ks:
                    d.rectangle((xs(k) - 1, ly, xs(k) + 1, ly + max(1, lane_h - 0.5)), fill=col)
        for k, ks in enumerate(self.kinds):
            if "death" in ks:
                d.line((xs(k), y0 + 2, xs(k), y1 - 2), fill=BAD, width=3)
        cx = xs(i)
        d.line((cx, y0 + 2, cx, y1 - 2), fill=TEXT, width=2)


def export(run_dir: Path, out: Path | None = None, seconds_per_frame: float = 1.0, speed: float = 1.0,
           smart: bool = False, annotations: bool = False, fps: int | None = None,
           progress: Callable[[int, int], None] | None = None) -> Path:
    """Render the run to MP4. Each snapshot is shown for seconds_per_frame / speed seconds, scaled per frame
    by pace() when smart is set. Returns the output path (default: <run>/replay_<speed>x[_smart][_notes].mp4)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    if seconds_per_frame <= 0 or speed <= 0:
        raise ValueError("seconds_per_frame and speed must be positive")
    r = Renderer(run_dir, annotations=annotations)
    if not r.frames:
        raise RuntimeError("the run has no snapshots")
    out = out or run_dir / export_name(speed, smart, annotations)
    tmp = out.with_name(out.stem + ".part.mp4")
    base = seconds_per_frame / speed
    durations = [base * (pace(k) if smart else 1.0) for k in r.kinds]
    # Frames go in at a fixed rate and are repeated to make up each one's duration; 10 fps is fine-grained
    # enough for pacing and cheap to encode (the picture only changes once per snapshot).
    fps = fps or min(30, max(10, round(1 / min(durations))))
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-framerate", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
           "-tune", "stillimage", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    prev = None
    try:
        for i in range(len(r.frames)):
            img, prev = r.render(i, prev)
            data = img.tobytes()
            for _ in range(max(1, round(durations[i] * fps))):
                proc.stdin.write(data)
            if progress:
                progress(i + 1, len(r.frames))
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err[-500:]}")
    except BaseException:
        proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
    return out


def render_png(run_dir: Path, frame: int) -> bytes:
    r = Renderer(run_dir)
    img, _ = r.render(max(0, min(frame, len(r.frames) - 1)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
