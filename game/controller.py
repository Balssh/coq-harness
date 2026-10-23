"""Thin key-sender wrapper over the bridge client. No game knowledge."""

from client.bridge_client import get_client


def press(key: str) -> None:
    """Press and release a single key."""
    get_client().keys([key])


def press_seq(keys: list[str], delay: float = 0.08) -> None:
    """Press keys sequentially within one focus session.

    Unlike calling press() multiple times, this keeps the game window
    focused across all keys. Use for Space+direction (talk/interact).
    """
    get_client().keys_seq(keys, delay=delay)


def chord(keys: list[str]) -> None:
    """Press a key combination, e.g. ["shift", "up"]."""
    get_client().keys(keys)


def hold(key: str) -> None:
    """Press and hold a key (release later with release())."""
    get_client().key_down(key)


def release(key: str) -> None:
    """Release a held key."""
    get_client().key_up(key)
