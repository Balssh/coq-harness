"""Replay viewer: serves recorded runs to a single-page viewer.

    python -m harness replay              # pick a run in the browser
    python -m harness replay <run dir>    # open one run directly
"""

import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

VIEWER = Path(__file__).parent / "viewer" / "index.html"
TYPES = {".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".md": "text/plain; charset=utf-8",
         ".mp4": "video/mp4"}

# MP4 exports running in this server, by run id: {"state", "done", "total", "error"}
_exports: dict[str, dict] = {}
_exports_lock = threading.Lock()


def _start_export(run_dir: Path, run: str, seconds_per_frame: float) -> dict:
    from harness.video import export

    with _exports_lock:
        job = _exports.get(run)
        if job and job["state"] == "running":
            return job
        job = _exports[run] = {"state": "running", "done": 0, "total": 0, "error": ""}

    def progress(done: int, total: int) -> None:
        job["done"], job["total"] = done, total

    def work() -> None:
        try:
            export(run_dir, seconds_per_frame=seconds_per_frame, progress=progress)
            job["state"] = "done"
        except Exception as e:  # shown in the viewer
            job["state"], job["error"] = "error", str(e)
    threading.Thread(target=work, daemon=True).start()
    return job


def list_runs(root: Path) -> list[dict]:
    runs = []
    for d in sorted(root.glob("*/meta.json"), reverse=True):
        try:
            meta = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({"id": d.parent.name, **{k: meta.get(k) for k in
                     ("model", "started", "ended", "outcome", "steps", "final", "label", "tokens", "duration_s")}})
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

    def _json(self, obj) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = unquote(url.path)
        if path in ("/", "/index.html"):
            return self._send(VIEWER.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/runs":
            return self._json(list_runs(self.root))
        if path == "/api/run":
            run = parse_qs(url.query).get("id", [""])[0]
            d = (self.root / run).resolve()
            if not run or self.root.resolve() not in d.parents or not (d / "meta.json").exists():
                return self._send(b"no such run", "text/plain", 404)
            events = []
            with (d / "events.jsonl").open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass  # a run still being written can end in a partial line
            return self._json({"meta": json.loads((d / "meta.json").read_text(encoding="utf-8")), "events": events})
        if path in ("/api/export", "/api/export_status"):
            q = parse_qs(url.query)
            run = q.get("id", [""])[0]
            d = (self.root / run).resolve()
            if not run or self.root.resolve() not in d.parents or not (d / "meta.json").exists():
                return self._send(b"no such run", "text/plain", 404)
            if path == "/api/export":
                job = _start_export(d, run, float(q.get("spf", ["1.0"])[0]))
            else:
                job = _exports.get(run) or {"state": "done" if (d / "replay.mp4").exists() else "idle"}
            return self._json({**job, "file": f"files/{quote(run)}/replay.mp4" if (d / "replay.mp4").exists() else ""})
        if path.startswith("/files/"):
            f = (self.root / path[len("/files/"):]).resolve()
            if self.root.resolve() in f.parents and f.is_file():
                return self._send(f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
        self._send(b"not found", "text/plain", 404)


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
