"""Thin key-sender wrapper over the bridge client. No game knowledge."""

from client.bridge_client import get_client


def press(key: str) -> None:
    """Press and release a single key."""
    get_client().keys([key])


def chord(keys: list[str]) -> None:
    """Press a key combination, e.g. ["shift", "up"]."""
    get_client().keys(keys)


def hold(key: str) -> None:
    """Press and hold a key (release later with release())."""
    get_client().key_down(key)


def release(key: str) -> None:
    """Release a held key."""
    get_client().key_up(key)
