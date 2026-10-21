"""Harness-tracked game state. Model-reported fields are cached here."""

from dataclasses import dataclass, field


@dataclass
class GameState:
    turn_count: int = 0
    phase: str = "chargen"
    goal: str = ""
    screen: str = "unknown"
    hp: int | None = None
    max_hp: int | None = None
    hunger: str = ""
    location: str = ""


_state: GameState = GameState()


def get_state() -> GameState:
    return _state


def update(**kwargs) -> None:
    global _state
    for key, value in kwargs.items():
        if hasattr(_state, key):
            setattr(_state, key, value)


def reset() -> None:
    global _state
    _state = GameState()
