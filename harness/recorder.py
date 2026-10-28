"""Run recording for the replay viewer.

runs/harness/<run id>/
  meta.json      config, model, tools, start/end, outcome
  events.jsonl   one JSON object per line, each with "type", "t" (seconds) and "step"
  states/N.json  full game state (get_state_raw) at snapshot N
  frames/N.jpg   window screenshot at snapshot N (when capture works)

Event types: run_start, snapshot, llm, tool, memory, summary, nudge, autosave,
lessons, error, run_end.
"""

import json
import time
from pathlib import Path


class Recorder:
    def __init__(self, root: Path, run_id: str, meta: dict):
        self.dir = root / run_id
        (self.dir / "states").mkdir(parents=True, exist_ok=True)
        (self.dir / "frames").mkdir(exist_ok=True)
        self.run_id = run_id
        self.meta = {"run_id": run_id, "started": time.strftime("%Y-%m-%d %H:%M:%S"), **meta}
        self._t0 = time.monotonic()
        self._events = (self.dir / "events.jsonl").open("a", encoding="utf-8")
        self._write_meta()

    def _write_meta(self) -> None:
        (self.dir / "meta.json").write_text(json.dumps(self.meta, indent=1, ensure_ascii=False), encoding="utf-8")

    def event(self, type: str, step: int, **data) -> None:
        rec = {"type": type, "t": round(time.monotonic() - self._t0, 3), "step": step, **data}
        self._events.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self._events.flush()

    def save_state(self, index: int, state: dict) -> str:
        name = f"states/{index:05d}.json"
        (self.dir / name).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return name

    def save_frame(self, index: int, jpeg: bytes) -> str:
        name = f"frames/{index:05d}.jpg"
        (self.dir / name).write_bytes(jpeg)
        return name

    def finish(self, **meta) -> None:
        self.meta.update(meta, ended=time.strftime("%Y-%m-%d %H:%M:%S"),
                         duration_s=round(time.monotonic() - self._t0, 1))
        self._write_meta()
        self._events.close()
