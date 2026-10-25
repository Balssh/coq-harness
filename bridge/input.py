"""Input injection for the Qud window.

SendInput with temporary focus attach. PostMessage(WM_KEYDOWN) was tried
first but Unity/Qud ignores it (Raw Input / DirectInput backend), so input
goes through SendInput, which requires the window to be foreground for the
moment of the keystroke. The previous foreground window is restored after
every chord.
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
    # Movement: strictly numpad. Cardinal = 8/2/4/6, diagonals = 7/9/1/3.
    # Numpad VK codes are NumLock-independent when sent via SendInput.
    "up":         (win32con.VK_NUMPAD8, False),
    "down":       (win32con.VK_NUMPAD2, False),
    "left":       (win32con.VK_NUMPAD4, False),
    "right":      (win32con.VK_NUMPAD6, False),
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

# Punctuation / OEM keys (raw VK codes — win32con doesn't export these)
VK["."]  = (0xBE, False)   # . >   (VK_OEM_PERIOD)
VK[","]  = (0xBC, False)   # , <   (VK_OEM_COMMA)
VK[";"]  = (0xBA, False)   # ; :   (VK_OEM_1)
VK["/"]  = (0xBF, False)   # / ?   (VK_OEM_2)
VK["`"]  = (0xC0, False)   # ` ~   (VK_OEM_3)
VK["["]  = (0xDB, False)   # [ {   (VK_OEM_4)
VK["\\"] = (0xDC, False)   # \ |   (VK_OEM_5)
VK["]"]  = (0xDD, False)   # ] }   (VK_OEM_6)
VK["'"]  = (0xDE, False)   # ' "   (VK_OEM_7)
VK["-"]  = (0xBD, False)   # - _   (VK_OEM_MINUS)
VK["="]  = (0xBB, False)   # = +   (VK_OEM_PLUS)


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
    flags = 0
    if extended:
        flags |= _KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= _KEYEVENTF_KEYUP
    scan = win32api.MapVirtualKey(vk, 0)
    # Set both wVk and wScan — some engines check one or the other
    ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    inp = INPUT(type=_INPUT_KEYBOARD, union=_INPUT_UNION(ki=ki))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


# ---------------------------------------------------------------------------
# Focus management for SendInput fallback
# ---------------------------------------------------------------------------

_ASFW_ANY = 0xFFFFFFFF

# Functions missing from this pywin32 build — call via ctypes
_GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
_GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_GetWindowThreadProcessId.restype = wintypes.DWORD

_AttachThreadInput = ctypes.windll.user32.AttachThreadInput
_AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
_AttachThreadInput.restype = wintypes.BOOL

def _get_window_thread_id(hwnd: int) -> int:
    pid = wintypes.DWORD()
    return _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

def _force_foreground(hwnd: int) -> int:
    """Force the target window to the foreground. Returns previous foreground HWND.

    Raises RuntimeError if the window is gone or the focus switch fails —
    sending input to the wrong window is worse than failing loudly.
    """
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError(f"Window no longer exists (HWND={hwnd})")
    prev = win32gui.GetForegroundWindow()
    if prev == hwnd:
        return prev
    # Allow our process to steal foreground
    ctypes.windll.user32.AllowSetForegroundWindow(_ASFW_ANY)
    # AttachThreadInput trick
    cur_thread = win32api.GetCurrentThreadId()
    tgt_thread = _get_window_thread_id(hwnd)
    _AttachThreadInput(cur_thread, tgt_thread, True)
    win32gui.BringWindowToTop(hwnd)
    win32gui.SetForegroundWindow(hwnd)
    _AttachThreadInput(cur_thread, tgt_thread, False)
    time.sleep(0.05)  # let the focus settle
    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError(f"Failed to focus window (HWND={hwnd})")
    return prev


def _restore_foreground(prev_hwnd: int) -> None:
    if prev_hwnd and win32gui.IsWindow(prev_hwnd):
        try:
            win32gui.SetForegroundWindow(prev_hwnd)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class InputInjector:
    """Sends keys to a specific window by HWND.

    Uses SendInput with focus management. PostMessage was tried first
    but Unity/Qud ignores it (likely Raw Input / DirectInput backend).
    """

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def send_chord(self, keys: list[str]) -> None:
        """Press all keys in order, release in reverse. ~30ms hold time.

        Never leaves keys held: if anything fails mid-chord, all keys that
        are still down are released before the exception propagates.
        """
        vks = [_vk(k) for k in keys]
        prev = _force_foreground(self.hwnd)
        pressed: list[tuple[int, bool]] = []
        try:
            for vk, ext in vks:
                _send_input_key(vk, ext, down=True)
                pressed.append((vk, ext))
            time.sleep(0.03)
            for vk, ext in reversed(vks):
                _send_input_key(vk, ext, down=False)
                pressed.pop()
            time.sleep(0.05)  # let the game process
        finally:
            for vk, ext in reversed(pressed):
                try:
                    _send_input_key(vk, ext, down=False)
                except Exception:
                    pass
            _restore_foreground(prev)

    def key_down(self, key: str) -> None:
        vk, ext = _vk(key)
        prev = _force_foreground(self.hwnd)
        try:
            _send_input_key(vk, ext, down=True)
        finally:
            _restore_foreground(prev)

    def key_up(self, key: str) -> None:
        vk, ext = _vk(key)
        prev = _force_foreground(self.hwnd)
        try:
            _send_input_key(vk, ext, down=False)
        finally:
            _restore_foreground(prev)

    def send_sequence(self, keys: list[str], delay: float = 0.08) -> None:
        """Send key presses sequentially within a single focus session.

        Unlike calling send_chord multiple times (which does a full
        force-foreground/restore cycle per call), this forces foreground
        once, sends each key press-release with a small delay, then
        restores foreground. Prevents focus loss between sequential keys
        like Space + direction (talk/interact).
        """
        vks = [_vk(k) for k in keys]
        prev = _force_foreground(self.hwnd)
        pressed: list[tuple[int, bool]] = []
        try:
            for vk, ext in vks:
                _send_input_key(vk, ext, down=True)
                pressed.append((vk, ext))
                time.sleep(0.03)
                _send_input_key(vk, ext, down=False)
                pressed.pop()
                time.sleep(delay)
            time.sleep(0.05)  # let the game process
        finally:
            for vk, ext in reversed(pressed):
                try:
                    _send_input_key(vk, ext, down=False)
                except Exception:
                    pass
            _restore_foreground(prev)
