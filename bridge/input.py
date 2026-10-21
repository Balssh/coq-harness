"""Input injection for the Qud window.

PostMessage-first (zero focus steal), with a SendInput fallback that
temporarily attaches to the foreground thread.
"""

import ctypes
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui

# ---------------------------------------------------------------------------
# Keymap: name -> (vk_code, is_extended)
# ---------------------------------------------------------------------------

VK = {
    # Directions (arrows)
    "up":         (win32con.VK_UP,    True),
    "down":       (win32con.VK_DOWN,  True),
    "left":       (win32con.VK_LEFT,  True),
    "right":      (win32con.VK_RIGHT, True),
    # Diagonals map to numpad keys (NumLock-independent when sent as VK)
    "up_left":    (win32con.VK_NUMPAD7, False),
    "up_right":   (win32con.VK_NUMPAD9, False),
    "down_left":  (win32con.VK_NUMPAD1, False),
    "down_right": (win32con.VK_NUMPAD3, False),
    # Modifiers
    "shift":      (win32con.VK_SHIFT,   False),
    "ctrl":       (win32con.VK_CONTROL, False),
    "alt":        (win32con.VK_MENU,    False),
    # Actions
    "enter":      (win32con.VK_RETURN,  False),
    "escape":     (win32con.VK_ESCAPE,  False),
    "tab":        (win32con.VK_TAB,     False),
    "space":      (win32con.VK_SPACE,   False),
    "backspace":  (win32con.VK_BACK,    False),
    # Numpad
    "num_0":      (win32con.VK_NUMPAD0, False),
    "num_1":      (win32con.VK_NUMPAD1, False),
    "num_2":      (win32con.VK_NUMPAD2, False),
    "num_3":      (win32con.VK_NUMPAD3, False),
    "num_4":      (win32con.VK_NUMPAD4, False),
    "num_5":      (win32con.VK_NUMPAD5, False),
    "num_6":      (win32con.VK_NUMPAD6, False),
    "num_7":      (win32con.VK_NUMPAD7, False),
    "num_8":      (win32con.VK_NUMPAD8, False),
    "num_9":      (win32con.VK_NUMPAD9, False),
    "num_add":    (win32con.VK_ADD,     False),
    "num_sub":    (win32con.VK_SUBTRACT, False),
    "num_mul":    (win32con.VK_MULTIPLY, False),
    "num_div":    (win32con.VK_DIVIDE,  False),
    "num_enter":  (win32con.VK_RETURN,  True),
}

# Letters a-z
for _c in range(ord("a"), ord("z") + 1):
    VK[chr(_c)] = (_c, False)

# Digits 0-9
for _d in range(10):
    VK[str(_d)] = (ord(str(_d)), False)

# Function keys f1-f12
for _i in range(1, 13):
    VK[f"f{_i}"] = (win32con.VK_F1 + _i - 1, False)


def _vk(name: str) -> tuple[int, bool]:
    if name not in VK:
        raise ValueError(f"Unknown key: {name!r}")
    return VK[name]


# ---------------------------------------------------------------------------
# PostMessage path
# ---------------------------------------------------------------------------

def _post_key(hwnd: int, vk: int, extended: bool, down: bool) -> None:
    msg = win32con.WM_KEYDOWN if down else win32con.WM_KEYUP
    scan_code = win32api.MapVirtualKey(vk, 0)
    lparam = (1 << 0) | (scan_code << 16)
    if not down:
        lparam |= (1 << 30) | (1 << 31)  # previous state + transition
    if extended:
        lparam |= (1 << 24)
    win32gui.PostMessage(hwnd, msg, vk, lparam)


# ---------------------------------------------------------------------------
# SendInput fallback path
# ---------------------------------------------------------------------------

# Structures for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]

_INPUT_KEYBOARD = 1
_KEYEVENTF_SCANCODE = 0x0008
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_EXTENDEDKEY = 0x0001


def _send_input_key(vk: int, extended: bool, down: bool) -> None:
    flags = _KEYEVENTF_SCANCODE
    if extended:
        flags |= _KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= _KEYEVENTF_KEYUP
    scan = win32api.MapVirtualKey(vk, 0)
    ki = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    inp = INPUT(type=_INPUT_KEYBOARD, union=_INPUT_UNION(ki=ki))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


# ---------------------------------------------------------------------------
# Focus management for SendInput fallback
# ---------------------------------------------------------------------------

def _force_foreground(hwnd: int) -> int:
    """Force the target window to the foreground. Returns previous foreground HWND."""
    prev = win32gui.GetForegroundWindow()
    if prev == hwnd:
        return prev
    # AttachThreadInput trick
    cur_thread = win32api.GetCurrentThreadId()
    tgt_thread = win32gui.GetWindowThreadProcessId(hwnd, None)[0]
    win32gui.AttachThreadInput(cur_thread, tgt_thread, True)
    win32gui.BringWindowToTop(hwnd)
    win32gui.SetForegroundWindow(hwnd)
    win32gui.AttachThreadInput(cur_thread, tgt_thread, False)
    return prev


def _restore_foreground(prev_hwnd: int) -> None:
    if prev_hwnd:
        win32gui.SetForegroundWindow(prev_hwnd)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class InputInjector:
    """Sends keys to a specific window by HWND."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self._postmessage_ok = True  # optimistic; set False if PostMessage fails

    def send_chord(self, keys: list[str]) -> None:
        """Press all keys in order, release in reverse. ~30ms hold time."""
        vks = [_vk(k) for k in keys]
        if self._postmessage_ok:
            try:
                for vk, ext in vks:
                    _post_key(self.hwnd, vk, ext, down=True)
                time.sleep(0.03)
                for vk, ext in reversed(vks):
                    _post_key(self.hwnd, vk, ext, down=False)
                return
            except Exception:
                self._postmessage_ok = False
        # Fallback: SendInput with focus management
        prev = _force_foreground(self.hwnd)
        try:
            for vk, ext in vks:
                _send_input_key(vk, ext, down=True)
            time.sleep(0.03)
            for vk, ext in reversed(vks):
                _send_input_key(vk, ext, down=False)
        finally:
            _restore_foreground(prev)

    def key_down(self, key: str) -> None:
        vk, ext = _vk(key)
        if self._postmessage_ok:
            try:
                _post_key(self.hwnd, vk, ext, down=True)
                return
            except Exception:
                self._postmessage_ok = False
        prev = _force_foreground(self.hwnd)
        _send_input_key(vk, ext, down=True)
        _restore_foreground(prev)

    def key_up(self, key: str) -> None:
        vk, ext = _vk(key)
        if self._postmessage_ok:
            try:
                _post_key(self.hwnd, vk, ext, down=False)
                return
            except Exception:
                self._postmessage_ok = False
        prev = _force_foreground(self.hwnd)
        _send_input_key(vk, ext, down=False)
        _restore_foreground(prev)
