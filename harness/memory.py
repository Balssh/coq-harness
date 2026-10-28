"""What the model remembers beyond its recent context.

- Run memory: a goal and numbered notes the model writes itself (note /
  forget_note / set_goal tools), plus "the story so far", a summary the
  harness has the model write when old steps are dropped from the context.
  All of it is shown in the system prompt every step.
- Journal: lessons the model writes at the end of each run, appended to
  runs/journal.md and shown to the next runs.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

MAX_NOTES = 40
MAX_NOTE_CHARS = 300

MEMORY_TOOLS = [
    {"type": "function", "function": {
        "name": "note",
        "description": "Save a short note to your memory. Notes stay visible for the whole run (unlike old "
                       "turns, which get dropped). Use them for plans, quest info, where things/NPCs are, "
                       "dangers, what worked and what didn't.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "forget_note",
        "description": "Delete a note that is done or no longer true, by its number.",
        "parameters": {"type": "object", "properties": {"number": {"type": "integer"}}, "required": ["number"]}}},
    {"type": "function", "function": {
        "name": "set_goal",
        "description": "Set your current goal (one sentence). Shown to you every turn until you change it.",
        "parameters": {"type": "object", "properties": {"goal": {"type": "string"}}, "required": ["goal"]}}},
]
MEMORY_TOOL_NAMES = {t["function"]["name"] for t in MEMORY_TOOLS}


@dataclass
class Memory:
    goal: str = ""
    notes: list[str] = field(default_factory=list)
    summary: str = ""

    def handle(self, name: str, args: dict) -> str:
        if name == "note":
            text = str(args.get("text", "")).strip()[:MAX_NOTE_CHARS]
            if not text:
                return "Empty note ignored."
            self.notes.append(text)
            dropped = ""
            if len(self.notes) > MAX_NOTES:
                dropped = f" (memory full: dropped oldest note: {self.notes.pop(0)!r})"
            return f"Saved as note {len(self.notes)}.{dropped}"
        if name == "forget_note":
            try:
                n = int(args.get("number"))
                removed = self.notes.pop(n - 1)
                return f"Forgot note {n}: {removed!r}. Remaining notes were renumbered."
            except (TypeError, ValueError, IndexError):
                return f"No note {args.get('number')!r}; you have {len(self.notes)} notes."
        if name == "set_goal":
            self.goal = str(args.get("goal", "")).strip()[:MAX_NOTE_CHARS]
            return f"Goal set: {self.goal}"
        return f"Unknown memory tool {name}"

    def block(self) -> str:
        lines = ["# Your memory", f"Current goal: {self.goal or '(none - set one with set_goal)'}"]
        if self.notes:
            lines.append("Notes:")
            lines += [f"{i}. {n}" for i, n in enumerate(self.notes, 1)]
        else:
            lines.append("Notes: (none yet - save important things with note)")
        if self.summary:
            lines += ["", "The story so far (summary of turns no longer in your context):", self.summary]
        return "\n".join(lines)

    def snapshot(self) -> dict:
        return {"goal": self.goal, "notes": list(self.notes), "summary": self.summary}


class Journal:
    """Lessons across runs, kept as a markdown file people can read and edit."""

    def __init__(self, path: Path):
        self.path = path

    def recent(self, max_chars: int = 4000) -> str:
        try:
            text = self.path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        if len(text) <= max_chars:
            return text
        cut = text[-max_chars:]
        return "…" + cut[cut.find("\n## ") if "\n## " in cut else 0:]

    def append(self, run_id: str, header: str, lessons: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"\n## {time.strftime('%Y-%m-%d %H:%M')} — {run_id}\n{header}\n\n{lessons.strip()}\n")
