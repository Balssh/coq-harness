"""Cross-episode free-text journal. Persisted to disk as JSON."""

import json
import os


class Journal:
    def __init__(self) -> None:
        self._notes: list[str] = []

    def add(self, note: str) -> None:
        """Add a free-text note."""
        note = note.strip()
        if note:
            self._notes.append(note)

    def get(self) -> str:
        """Return all notes as a single string."""
        return "\n".join(self._notes)

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"notes": self._notes}, f, indent=2, ensure_ascii=False)

    def load(self, path: str) -> None:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._notes = list(data.get("notes", []))

    def clear(self) -> None:
        self._notes.clear()


# Singleton
_journal = Journal()


def get_journal() -> Journal:
    return _journal
