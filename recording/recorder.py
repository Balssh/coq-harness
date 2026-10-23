"""Episode recorder. Captures frames, decisions, tool results, timing to disk.

Storage layout:
  runs/YYYY-MM-DD_episode-N/
    frames/
      turn-NNNN-NN-label.png
    log.jsonl
    meta.json
"""

import json
import os
import time
from pathlib import Path

from client.bridge_client import get_client


class Recorder:
    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.frames_dir = self.run_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.run_dir / "log.jsonl"
        self._log_file = open(self._log_path, "a", encoding="utf-8")
        self._turn: int = 0
        self._frame_idx: int = 0
        self._episode_start: float = time.time()

    def _write_event(self, event: dict) -> None:
        event["timestamp"] = time.time()
        self._log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._log_file.flush()

    def _save_frame(self, label: str) -> str:
        """Grab a full screenshot and save it. Returns the filename."""
        png = get_client().grab()
        filename = f"turn-{self._turn:04d}-{self._frame_idx:02d}-{label}.png"
        path = self.frames_dir / filename
        path.write_bytes(png)
        self._frame_idx += 1
        return filename

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_turn(self, turn: int) -> None:
        self._turn = turn
        self._frame_idx = 0
        frame = self._save_frame("start")
        self._write_event({"type": "turn_start", "turn": turn, "frame": frame})

    def record_decision(self, decision) -> None:
        """Record a Decision object."""
        self._write_event({
            "type": "decision",
            "turn": self._turn,
            "reasoning": decision.reasoning,
            "tool": decision.tool,
            "key": decision.key,
            "args": decision.args,
            "screen": decision.screen,
            "goal": decision.goal,
            "hp": decision.hp,
            "max_hp": decision.max_hp,
            "hunger": decision.hunger,
            "location": decision.location,
            "journal_note": decision.journal_note,
        })

    def capture(self, label: str) -> str:
        """Capture an intermediate frame. Returns the frame filename."""
        frame = self._save_frame(label)
        self._write_event({
            "type": "frame",
            "turn": self._turn,
            "label": label,
            "frame": frame,
        })
        return frame

    def record_tool_result(self, result) -> None:
        """Record a ToolResult."""
        event = {
            "type": "tool_result",
            "turn": self._turn,
            "text": result.text,
            "error": result.error,
        }
        if result.image is not None:
            filename = f"turn-{self._turn:04d}-{self._frame_idx:02d}-tool-result.png"
            (self.frames_dir / filename).write_bytes(result.image)
            self._frame_idx += 1
            event["image"] = filename
        if result.images:
            event["images"] = {}
            for name, png in result.images.items():
                filename = f"turn-{self._turn:04d}-{self._frame_idx:02d}-tool-{name}.png"
                (self.frames_dir / filename).write_bytes(png)
                self._frame_idx += 1
                event["images"][name] = filename
        self._write_event(event)

    def end_turn(self, turn_changed: bool, wait_time: float) -> None:
        frame = self._save_frame("end")
        self._write_event({
            "type": "turn_end",
            "turn": self._turn,
            "frame": frame,
            "turn_changed": turn_changed,
            "wait_time": round(wait_time, 3),
        })

    def record_transcript(self, text: str) -> None:
        self._write_event({
            "type": "transcript",
            "turn": self._turn,
            "text": text,
        })

    def record_timing(self, decision_ms: float, turn_total_ms: float) -> None:
        self._write_event({
            "type": "timing",
            "turn": self._turn,
            "decision_ms": round(decision_ms, 1),
            "turn_total_ms": round(turn_total_ms, 1),
        })

    def save_meta(self, **kwargs) -> None:
        meta = {
            "episode_start": self._episode_start,
            "episode_end": time.time(),
            "duration_seconds": round(time.time() - self._episode_start, 1),
            **kwargs,
        }
        with open(self.run_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def close(self) -> None:
        self._log_file.close()


# Singleton
_recorder: Recorder | None = None


def get_recorder() -> Recorder:
    global _recorder
    if _recorder is None:
        raise RuntimeError("Recorder not started. Call start_recorder() first.")
    return _recorder


def start_recorder(run_dir: str) -> Recorder:
    global _recorder
    if _recorder is not None:
        _recorder.close()
    _recorder = Recorder(run_dir)
    return _recorder


def stop_recorder() -> None:
    global _recorder
    if _recorder is not None:
        _recorder.close()
        _recorder = None
