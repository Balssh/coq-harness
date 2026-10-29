"""Replay viewer: serves recorded runs to a single-page viewer.

    python -m harness replay              # pick a run in the browser
    python -m harness replay <run dir>    # open one run directly

Besides the recorded files, the server keeps reviewer annotations (`<run>/annotations.json`) and
runs MP4 exports in the background.
"""

import json
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

VIEWER = Path(__file__).parent / "viewer" / "index.html"
TYPES = {".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".md": "text/plain; charset=utf-8",
         ".mp4": "video/mp4"}

# MP4 exports running in this server, by (run id, file name): {"state", "done", "total", "error", "name"}
_exports: dict[tuple[str, str], dict] = {}
_exports_lock = threading.Lock()
_annotations_lock = threading.Lock()
# run summaries for the run list, by run id: (events.jsonl mtime and size, summary)
_summaries: dict[str, tuple[tuple, dict]] = {}


def _start_export(run_dir: Path, run: str, opts: dict) -> dict:
    from harness.video import export, export_name

    name = export_name(opts["speed"], opts["smart"], opts["annotations"])
    with _exports_lock:
        job = _exports.get((run, name))
        if job and job["state"] == "running":
            return job
        job = _exports[(run, name)] = {"state": "running", "done": 0, "total": 0, "error": "", "name": name}

    def progress(done: int, total: int) -> None:
        job["done"], job["total"] = done, total

    def work() -> None:
        try:
            export(run_dir, run_dir / name, speed=opts["speed"], smart=opts["smart"],
                   annotations=opts["annotations"], progress=progress)
            job["state"] = "done"
        except Exception as e:  # shown in the viewer
            job["state"], job["error"] = "error", str(e)
    threading.Thread(target=work, daemon=True).start()
    return job


def _export_files(run_dir: Path, run: str) -> list[dict]:
    files = []
    for f in sorted(run_dir.glob("replay*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.name.endswith(".part.mp4"):
            continue
        st = f.stat()
        files.append({"name": f.name, "url": f"files/{quote(run)}/{quote(f.name)}", "bytes": st.st_size,
                      "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
    return files


def read_annotations(run_dir: Path) -> dict[str, dict]:
    try:
        data = json.loads((run_dir / "annotations.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_annotation(run_dir: Path, step: int, text: str) -> dict:
    with _annotations_lock:
        notes = read_annotations(run_dir)
        text = text.strip()[:4000]
        if text:
            notes[str(step)] = {"text": text, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
        else:
            notes.pop(str(step), None)
        tmp = run_dir / "annotations.json.tmp"
        tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(run_dir / "annotations.json")
        return notes


def _read_events(run_dir: Path) -> list[dict]:
    events = []
    with (run_dir / "events.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # a run still being written can end in a partial line
    return events


def _summarize(run_dir: Path) -> dict:
    """Numbers for the run cards and the compare view, read from events.jsonl (cached by its mtime)."""
    ev_path = run_dir / "events.jsonl"
    try:
        st = ev_path.stat()
    except OSError:
        return {}
    key = (st.st_mtime, st.st_size)
    hit = _summaries.get(run_dir.name)
    if hit and hit[0] == key:
        return hit[1]
    snaps, zones, tools = [], [], {}
    counts = {"nudges": 0, "errors": 0, "summaries": 0, "tool_errors": 0}
    for e in _read_events(run_dir):
        t = e.get("type")
        if t == "snapshot":
            snaps.append(e)
            z = e.get("zone")
            if z and (not zones or zones[-1] != z) and z not in zones:
                zones.append(z)
        elif t == "tool":
            tools[e.get("name")] = tools.get(e.get("name"), 0) + 1
            counts["tool_errors"] += bool(e.get("is_error"))
        elif t == "nudge":
            counts["nudges"] += 1
        elif t == "error":
            counts["errors"] += 1
        elif t == "summary":
            counts["summaries"] += 1
    stride = max(1, len(snaps) // 120)
    hp = [[s.get("step", 0), round(s.get("t") or 0, 1), s.get("hp"), s.get("hpMax")]
          for s in snaps[::stride] if s.get("hp") is not None]
    if snaps and snaps[-1].get("hp") is not None and (not hp or hp[-1][0] != snaps[-1].get("step")):
        s = snaps[-1]
        hp.append([s.get("step", 0), round(s.get("t") or 0, 1), s.get("hp"), s.get("hpMax")])
    framed = [s for s in snaps if s.get("frame")]
    summary = {
        "frames": len(snaps),
        "max_level": max((s.get("level") or 0 for s in snaps), default=None),
        "max_xp": max((s.get("xp") or 0 for s in snaps), default=None),
        "zones": zones,
        "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
        "thumb_first": framed[0]["frame"] if framed else None,
        "thumb_last": framed[-1]["frame"] if framed else None,
        "hp": hp,
        "annotations": len(read_annotations(run_dir)),
        **counts,
    }
    _summaries[run_dir.name] = (key, summary)
    return summary


def list_runs(root: Path) -> list[dict]:
    runs = []
    for d in sorted(root.glob("*/meta.json"), reverse=True):
        try:
            meta = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        try:  # a run without an end that hasn't written anything for a while was killed, not still running
            idle_s = time.time() - (d.parent / "events.jsonl").stat().st_mtime
        except OSError:
            idle_s = None
        runs.append({"id": d.parent.name, **{k: meta.get(k) for k in
                     ("model", "started", "ended", "outcome", "steps", "final", "label", "tokens", "duration_s")},
                     "idle_s": idle_s, "summary": _summarize(d.parent)})
    return runs


class Handler(SimpleHTTPRequestHandler):
    root: Path = Path("runs/harness")

    def log_message(self, *args) -> None:
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json", status)

    def _run_dir(self, run: str) -> Path | None:
        """The run's directory, or None if `run` isn't a run directly under the root."""
        if not run:
            return None
        d = (self.root / run).resolve()
        if d.parent != self.root.resolve() or not (d / "meta.json").exists():
            return None
        return d

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = unquote(url.path)
        q = parse_qs(url.query)
        run = q.get("id", [""])[0]
        if path in ("/", "/index.html"):
            return self._send(VIEWER.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/runs":
            return self._json(list_runs(self.root))
        if path.startswith("/api/") and path != "/api/runs":
            d = self._run_dir(run)
            if not d:
                return self._send(b"no such run", "text/plain", 404)
            if path == "/api/run":
                return self._json({"meta": json.loads((d / "meta.json").read_text(encoding="utf-8")),
                                   "events": _read_events(d), "annotations": read_annotations(d)})
            if path == "/api/annotations":
                return self._json(read_annotations(d))
            if path in ("/api/export", "/api/export_status"):
                if path == "/api/export":
                    try:
                        speed = float(q.get("speed", ["1"])[0])
                    except ValueError:
                        speed = 1.0
                    _start_export(d, run, {"speed": min(16.0, max(0.05, speed)),
                                           "smart": q.get("smart", ["0"])[0] == "1",
                                           "annotations": q.get("ann", ["0"])[0] == "1"})
                jobs = [dict(j) for (r, _), j in _exports.items() if r == run]
                return self._json({"jobs": jobs, "files": _export_files(d, run)})
        if path.startswith("/files/"):
            f = (self.root / path[len("/files/"):]).resolve()
            if self.root.resolve() in f.parents and f.is_file():
                return self._send(f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
        self._send(b"not found", "text/plain", 404)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        if unquote(url.path) != "/api/annotate":
            return self._send(b"not found", "text/plain", 404)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 64_000)) or b"{}")
            step = int(body["step"])
            text = str(body.get("text") or "")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return self._send(b"bad request", "text/plain", 400)
        d = self._run_dir(str(body.get("id") or ""))
        if not d:
            return self._send(b"no such run", "text/plain", 404)
        self._json(_write_annotation(d, step, text))


def serve(root: Path, run: str | None = None, port: int = 8765, open_browser: bool = True) -> None:
    Handler.root = root
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/" + (f"?run={quote(run)}" if run else "")
    print(f"Replay viewer for {root} at {url}  (Ctrl-C to stop)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
