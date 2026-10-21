"""Running text transcript of the message log, transcribed by the model.

Kept raw — no summarization, no truncation (for the demo).
"""


class Transcript:
    def __init__(self) -> None:
        self._entries: list[str] = []

    def append(self, text: str) -> None:
        """Append model-transcribed log text for this turn."""
        text = text.strip()
        if text:
            self._entries.append(text)

    def get(self, max_turns: int | None = None) -> str:
        """Return the full transcript, or the last N entries."""
        entries = self._entries[-max_turns:] if max_turns else self._entries
        return "\n".join(entries)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


# Singleton
_transcript = Transcript()


def get_transcript() -> Transcript:
    return _transcript
