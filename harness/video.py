"""Render a recorded run to MP4: one 1920x1080 frame per snapshot, with the game screenshot,
the map drawn from the recorded state, stats, the model's step (thinking, text, tool calls and
results), its memory, recent messages and an HP timeline.

    python -m harness export <run> [--seconds-per-frame 1.0] [--out file.mp4]

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
    return re.sub(r"&[a-zA-Z]", "", re.sub(r"\{\{[^|}]*\|([^}]*)\}\}", r"\1", str(s or "")))


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


def draw_map(d, state: dict, box) -> None:
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


class Renderer:
    def __init__(self, run_dir: Path):
        self.dir = run_dir
        self.meta, self.events = load_run(run_dir)
        self.frames = [e for e in self.events if e["type"] == "snapshot"]
        self.by_step: dict[int, list[dict]] = {}
        for e in self.events:
            self.by_step.setdefault(e["step"], []).append(e)

    def _state(self, snap: dict) -> dict:
        try:
            return json.loads((self.dir / "states" / f"{snap['index']:05d}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _memory_at(self, i: int) -> dict | None:
        target, mem = self.frames[i], None
        for e in self.events:
            if e["type"] == "memory":
                mem = e
            if e is target:
                break
        return mem

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
        draw_map(d, state, (28, 722, 1124, 996))

        # right: step, memory, messages
        evs = self.by_step.get(snap["step"], [])
        llm = next((e for e in evs if e["type"] == "llm"), None)
        tools = [e for e in evs if e["type"] == "tool"]
        _panel(d, (1152, 56, 1904, 640), f"Step {snap['step']}" + (" — start" if snap["step"] == 0 else ""))
        b = Block(d, 1168, 88, 720, 628)
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

        self._timeline(d, i)
        return img, state

    def _timeline(self, d, i: int) -> None:
        x0, y0, x1, y1 = 16, 1016, 1904, 1068
        d.rounded_rectangle((x0, y0, x1, y1), radius=8, fill=PANEL, outline=LINE)
        n = max(1, len(self.frames) - 1)
        xs = lambda k: x0 + 8 + (x1 - x0 - 16) * k / n
        pts = [(xs(k), y1 - 6 - (s["hp"] / s["hpMax"] if s.get("hpMax") else 0) * (y1 - y0 - 12))
               for k, s in enumerate(self.frames) if s.get("hp") is not None]
        if len(pts) > 1:
            d.line(pts, fill=HP, width=2)
        for k, s in enumerate(self.frames):
            if k and s.get("level") is not None and s.get("level") != self.frames[k - 1].get("level"):
                d.line((xs(k), y0, xs(k), y1), fill=ACCENT, width=1)
        cx = xs(i)
        d.line((cx, y0 + 2, cx, y1 - 2), fill=TEXT, width=2)


def export(run_dir: Path, out: Path | None = None, seconds_per_frame: float = 1.0, fps: int = 30,
           progress: Callable[[int, int], None] | None = None) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    r = Renderer(run_dir)
    if not r.frames:
        raise RuntimeError("the run has no snapshots")
    out = out or run_dir / "replay.mp4"
    tmp = out.with_suffix(".part.mp4")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-framerate", f"{1 / seconds_per_frame:.6f}", "-i", "-", "-r", str(fps), "-c:v", "libx264",
           "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    prev = None
    try:
        for i in range(len(r.frames)):
            img, prev = r.render(i, prev)
            proc.stdin.write(img.tobytes())
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
