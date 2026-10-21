"""Replay viewer server. Serves a recorded episode as a single-page HTML app.

Usage:
    python -m recording.replay runs/2026-10-20_episode-3/
"""

import argparse
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse


class ReplayHandler(SimpleHTTPRequestHandler):
    run_dir: Path = Path(".")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            html_path = Path(__file__).parent / "viewer" / "index.html"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_path.read_bytes())
            return

        if parsed.path == "/api/events":
            log_path = self.run_dir / "log.jsonl"
            events = []
            if log_path.exists():
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            events.append(json.loads(line))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(events).encode("utf-8"))
            return

        if parsed.path.startswith("/frames/"):
            frame_path = self.run_dir / "frames" / parsed.path[len("/frames/"):]
            if frame_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(frame_path.read_bytes())
                return
            self.send_error(404)
            return

        if parsed.path == "/api/meta":
            meta_path = self.run_dir / "meta.json"
            if meta_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(meta_path.read_bytes())
                return
            self.send_error(404)
            return

        self.send_error(404)

    def log_message(self, format, *args) -> None:
        pass  # suppress request logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay viewer for CoQ harness recordings")
    parser.add_argument("run_dir", help="Path to the run directory (contains log.jsonl and frames/)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        print(f"Run directory not found: {run_dir}")
        return
    if not (run_dir / "log.jsonl").exists():
        print(f"No log.jsonl found in: {run_dir}")
        return

    ReplayHandler.run_dir = run_dir

    server = HTTPServer(("0.0.0.0", args.port), ReplayHandler)
    print(f"Replay viewer serving {run_dir}")
    print(f"Open http://localhost:{args.port}/ in your browser")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
