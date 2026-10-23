"""Game phase management. The model reports the screen; the loop follows."""

from enum import Enum


class Phase(Enum):
    TITLE       = "title"
    MODE_SELECT = "mode_select"
    CHARGEN     = "chargen"
    PLAY        = "play"
    MENU        = "menu"
    DIALOGUE    = "dialogue"
    TRADE       = "trade"
    DEATH       = "death"
    UNKNOWN     = "unknown"


_current_phase: Phase = Phase.CHARGEN


def current_phase() -> Phase:
    return _current_phase


def transition_to(new_phase: Phase) -> None:
    global _current_phase
    if new_phase != _current_phase:
        print(f"[phase] {_current_phase.value} -> {new_phase.value}")
    _current_phase = new_phase


def phase_from_screen(screen: str) -> Phase:
    """Map a model-reported screen string to a Phase."""
    try:
        return Phase(screen)
    except ValueError:
        return Phase.UNKNOWN
