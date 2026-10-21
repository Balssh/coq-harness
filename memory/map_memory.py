"""Map memory helpers — location-tagged notes stored in the journal."""

from memory.journal import get_journal


def add_location_note(location: str, note: str) -> None:
    """Add a note about a specific location. Stored with a [location] prefix."""
    get_journal().add(f"[{location}] {note}")


def get_location_notes(location: str) -> str:
    """Return all journal notes for a specific location (prefix match)."""
    prefix = f"[{location}]"
    notes = [
        n for n in get_journal()._notes if n.startswith(prefix)
    ]
    return "\n".join(notes)
